from decimal import Decimal
import math
import os
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import BaseDocTemplate, Frame, Image, PageBreak, PageTemplate, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

try:
    _reg_path = os.path.join(settings.BASE_DIR, 'static', 'core', 'fonts', 'NotoSansDevanagari-Regular.ttf')
    _bold_path = os.path.join(settings.BASE_DIR, 'static', 'core', 'fonts', 'NotoSansDevanagari-Bold.ttf')
    pdfmetrics.registerFont(TTFont('NotoSansDevanagari', _reg_path))
    pdfmetrics.registerFont(TTFont('NotoSansDevanagari-Bold', _bold_path))
    pdfmetrics.registerFontFamily('NotoSansDevanagari', normal='NotoSansDevanagari', bold='NotoSansDevanagari-Bold')
except Exception:
    pass

from reportlab.platypus.flowables import Flowable

class StringFlowable(Flowable):
    def __init__(self, text, font_name, font_size, fill_color=None):
        Flowable.__init__(self)
        self.text = text
        self.font_name = font_name
        self.font_size = font_size
        self.fill_color = fill_color
        self.width = pdfmetrics.stringWidth(text, font_name, font_size)
        self.height = font_size * 1.2
    def draw(self):
        self.canv.saveState()
        self.canv.setFont(self.font_name, self.font_size)
        if self.fill_color is not None:
            self.canv.setFillColor(self.fill_color)
        self.canv.drawString(0, self.font_size * 0.25, self.text)
        self.canv.restoreState()

class VerticalTextFlowable(Flowable):
    def __init__(self, text, font_name, font_size):
        Flowable.__init__(self)
        self.text = text
        self.font_name = font_name
        self.font_size = font_size
        self.width = font_size * 1.2
        self.height = pdfmetrics.stringWidth(text, font_name, font_size)
    def draw(self):
        self.canv.saveState()
        self.canv.setFont(self.font_name, self.font_size)
        self.canv.translate(self.width / 2.0 - self.font_size * 0.35, 0)
        self.canv.rotate(90)
        self.canv.drawString(0, 0, self.text)
        self.canv.restoreState()


# ReportLab draws each Devanagari character glyph in raw Unicode storage
# order and does not perform OpenType shaping (no matra reordering, no
# conjunct/ligature substitution). That makes real Hindi text - which relies
# on both of those - render incorrectly as vector PDF text (this is a
# long-documented ReportLab limitation for Indic/complex scripts, not a font
# or encoding bug).
#
# First fix attempted: render via Pillow's ImageFont with layout_engine=RAQM.
# Confirmed NOT viable - `PIL.features.check("raqm")` returned False on the
# owner's machine (the Windows PyPI Pillow wheel does not bundle libraqm),
# so that code silently fell back to Pillow's own unshaped BASIC layout,
# which has the exact same matra-ordering bug as ReportLab's own rendering.
#
# Actual fix: a proper shaping pipeline built from two independent,
# pip-installable-on-Windows libraries - `uharfbuzz` (HarfBuzz bindings) does
# the SHAPING (turns the logical-order Unicode string into a sequence of
# glyph IDs with correct positions/reordering/ligatures), and `freetype-py`
# (FreeType bindings) RASTERIZES each of those specific glyph IDs from the
# same font file into a bitmap. This shaping-engine + rasterizer split is
# the standard architecture for correct complex-script text rendering and
# does not depend on any particular Pillow build. Results are cached, since
# the Scholar Register's Hindi labels are a small, fixed set reused on every
# student page of a Full Register Book print.
_devanagari_image_cache = {}


def _render_devanagari_png(text, font_size_pt, bold=False, color=(23, 32, 42, 255)):
    """Returns (png_bytes, width_pt, height_pt) for `text` shaped and
    rendered via HarfBuzz + FreeType, or None if it failed for any reason
    (libraries not installed, corrupt font, etc.) - callers must fall back
    to the old vector-text rendering in that case rather than crashing PDF
    generation."""
    cache_key = (text, round(font_size_pt, 2), bold, color)
    if cache_key in _devanagari_image_cache:
        return _devanagari_image_cache[cache_key]

    result = None
    try:
        import freetype
        import uharfbuzz as hb

        font_path = _bold_path if bold else _reg_path
        scale = 3  # oversample for print-crisp output, then scale back down via the Image flowable's size
        px_size = max(1.0, font_size_pt * scale)

        with open(font_path, "rb") as fh:
            font_bytes = fh.read()
        hb_face = hb.Face(font_bytes)
        hb_font = hb.Font(hb_face)
        upem = hb_face.upem or 1000
        hb_font.scale = (upem, upem)
        try:
            hb.ot_font_set_funcs(hb_font)
        except Exception:
            pass

        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(hb_font, buf)

        unit_to_px = px_size / upem
        ft_face = freetype.Face(font_path)
        ft_face.set_pixel_sizes(0, max(1, int(round(px_size))))

        pen_x = pen_y = 0.0
        placements = []
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            x_off = pos.x_offset * unit_to_px
            y_off = pos.y_offset * unit_to_px
            x_adv = pos.x_advance * unit_to_px
            y_adv = pos.y_advance * unit_to_px

            ft_face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
            bitmap = ft_face.glyph.bitmap
            if bitmap.width and bitmap.rows:
                raw = bytes(bitmap.buffer)
                if bitmap.pitch == bitmap.width:
                    glyph_alpha = PILImage.frombytes("L", (bitmap.width, bitmap.rows), raw)
                else:
                    rows_data = bytearray()
                    for r in range(bitmap.rows):
                        start = r * bitmap.pitch
                        rows_data.extend(raw[start:start + bitmap.width])
                    glyph_alpha = PILImage.frombytes("L", (bitmap.width, bitmap.rows), bytes(rows_data))

                gx = pen_x + x_off + ft_face.glyph.bitmap_left
                gy = pen_y - y_off - ft_face.glyph.bitmap_top
                placements.append((glyph_alpha, gx, gy))
                min_x = min(min_x, gx)
                min_y = min(min_y, gy)
                max_x = max(max_x, gx + bitmap.width)
                max_y = max(max_y, gy + bitmap.rows)

            pen_x += x_adv
            pen_y += y_adv

        # A trailing space at the end of a Devanagari run (common at a
        # Hindi->English transition, e.g. "...का कार्य " before "Work...")
        # has no visible glyph, so the bounding box above - built only from
        # glyphs that actually painted pixels - silently discards it. That
        # trimmed the image's width and made the following Latin run's cell
        # sit flush against it with no gap ("कार्यWork"). Extend the right
        # edge to the final pen position so trailing whitespace still
        # reserves its advance width in the rendered image.
        if placements:
            max_x = max(max_x, pen_x)

        if placements:
            pad = max(2, int(px_size // 6))
            canvas_w = int(math.ceil(max_x - min_x)) + 2 * pad
            canvas_h = int(math.ceil(max_y - min_y)) + 2 * pad
            canvas = PILImage.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            for glyph_alpha, gx, gy in placements:
                px = int(round(gx - min_x)) + pad
                py = int(round(gy - min_y)) + pad
                color_tile = PILImage.new("RGBA", glyph_alpha.size, color)
                canvas.paste(color_tile, (px, py), mask=glyph_alpha)

            buf_out = BytesIO()
            canvas.save(buf_out, format="PNG")
            result = (buf_out.getvalue(), canvas_w / scale, canvas_h / scale)
    except Exception:
        result = None

    _devanagari_image_cache[cache_key] = result
    return result


def _text_script_runs(text):
    """Splits text into (is_devanagari, run_text) tuples, grouping
    consecutive characters of the same class. A space attaches to whichever
    run is already open rather than forcing a script switch, so a phrase
    like "पूर्व विद्यालय" (Hindi with an internal space) or "VI to VIII"
    (English with internal spaces) stays as ONE run. This is needed because
    NotoSansDevanagari does not include Latin glyphs - ANY non-Devanagari
    character (English letters, but also plain ASCII punctuation like "-"
    or ":" that shows up inside labels such as "धर्म-जाती" or the mixed
    English/Hindi note text) must be rendered with a normal Latin font or
    it shows up as a missing-glyph box."""
    runs = []
    for ch in text:
        if ch.isspace() and runs:
            runs[-1][1] += ch
            continue
        is_deva = (not ch.isspace()) and (0x0900 <= ord(ch) <= 0x097F)
        if runs and runs[-1][0] == is_deva:
            runs[-1][1] += ch
        else:
            runs.append([is_deva, ch])
    return [(is_deva, run_text) for is_deva, run_text in runs]


def _devanagari_flowable(text, font_size_pt, bold=False, align=0, color=(23, 32, 42, 255)):
    """Flowable for text that may contain Devanagari, Latin, or both mixed
    together. Devanagari runs are shaped/rasterized via HarfBuzz + FreeType
    (_render_devanagari_png); everything else (English words, digits,
    hyphens, colons, etc.) is rendered as a normal Helvetica Paragraph,
    since the Devanagari font has no Latin glyphs to fall back on. Multiple
    runs are laid out left-to-right in a borderless single-row Table so they
    read as one continuous line. align: 0=left, 1=center, 2=right. color is
    an (r,g,b,a) 0-255 tuple applied to BOTH the rasterized Devanagari runs
    and the plain-text Latin runs, so mixed-script text stays one consistent
    colour (e.g. white text on a coloured title band)."""
    latin_style = ParagraphStyle(
        "DevanagariLatinRun", fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=font_size_pt, leading=font_size_pt * 1.25,
    )
    fallback_style = ParagraphStyle(
        "DevanagariFallback", fontName="NotoSansDevanagari-Bold" if bold else "NotoSansDevanagari",
        fontSize=font_size_pt, leading=font_size_pt * 1.25,
    )
    latin_fill = colors.Color(color[0] / 255.0, color[1] / 255.0, color[2] / 255.0, alpha=color[3] / 255.0)

    pieces = []
    widths = []
    for is_deva, run_text in _text_script_runs(text):
        if not run_text.strip():
            continue
        if not is_deva:
            sf = StringFlowable(run_text, latin_style.fontName, font_size_pt, fill_color=latin_fill)
            pieces.append(sf)
            widths.append(sf.width + 2) # small buffer
            continue
        rendered = _render_devanagari_png(run_text, font_size_pt, bold=bold, color=color)
        if rendered is None:
            sf = StringFlowable(run_text, fallback_style.fontName, font_size_pt, fill_color=latin_fill)
            pieces.append(sf)
            widths.append(sf.width + 2)
        else:
            png_bytes, w_pt, h_pt = rendered
            pieces.append(Image(BytesIO(png_bytes), width=w_pt, height=h_pt))
            widths.append(w_pt)

    h_align = {0: "LEFT", 1: "CENTER", 2: "RIGHT"}.get(align, "LEFT")
    if not pieces:
        return Paragraph("", latin_style)
    if len(pieces) == 1:
        single = pieces[0]
        if isinstance(single, Image):
            single.hAlign = h_align
        return single

    row_t = Table([pieces], colWidths=widths)
    row_t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ]))
    row_t.hAlign = h_align
    return row_t


import os
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _money(val):
    if val is None:
        return "0.00"
    return f"{Decimal(str(val)):,.2f}"


def _build_fee_receipt_story(receipt, school_profile=None):
    styles = getSampleStyleSheet()
    
    brand_color = colors.HexColor("#0f766e")       # Deep Teal
    brand_gold = colors.HexColor("#d97706")        # Amber Gold
    text_color = colors.HexColor("#0f172a")        # Slate 900
    muted_color = colors.HexColor("#475569")       # Slate 600
    border_color = colors.HexColor("#cbd5e1")      # Slate 300
    light_bg = colors.HexColor("#f8fafc")          # Slate 50
    header_bg = colors.HexColor("#0f766e")         # Primary Teal
    
    title_style = ParagraphStyle(
        "ReceiptSchoolTitle",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=12,
        alignment=1,  # Center
        textColor=brand_color,
        fontName="Helvetica-Bold",
    )
    school_sub_style = ParagraphStyle(
        "ReceiptSchoolSub",
        parent=styles["Normal"],
        fontSize=5.8,
        leading=7.2,
        alignment=1,  # Center
        textColor=muted_color,
    )
    badge_style = ParagraphStyle(
        "ReceiptBadge",
        parent=styles["Normal"],
        fontSize=6.5,
        leading=7.5,
        fontName="Helvetica-Bold",
        textColor=brand_color,
        alignment=1,
        spaceBefore=1 * mm,
    )
    rno_style = ParagraphStyle(
        "ReceiptNoStyle",
        parent=styles["Normal"],
        fontSize=6,
        leading=7.5,
        alignment=2,  # Right
        textColor=muted_color,
    )
    rno_val_style = ParagraphStyle(
        "ReceiptNoValStyle",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=11,
        fontName="Helvetica-Bold",
        alignment=2,
        textColor=text_color,
    )

    school_name = school_profile.name if school_profile and school_profile.name else "THAKUR HARIKESH PRATAP SINGH INTERMEDIATE COLLEGE"
    school_address = school_profile.address if school_profile and school_profile.address else "Uday, Dudahi, Kushinagar, U.P."
    
    contact_parts = []
    if school_profile:
        if school_profile.phone:
            contact_parts.append(f"Phone: {school_profile.phone}")
        if school_profile.email:
            contact_parts.append(f"Email: {school_profile.email}")
    school_contact = " | ".join(contact_parts) if contact_parts else "Affiliated to U.P. Board, Prayagraj"

    story = []

    # 1. School Logo
    logo_path = os.path.join(settings.BASE_DIR, "static", "core", "school_logo.png")
    logo_flowable = ""
    if os.path.exists(logo_path):
        try:
            logo_flowable = Image(logo_path, width=17 * mm, height=17 * mm)
        except Exception:
            logo_flowable = ""

    # Status Badge
    if receipt.is_cancelled:
        status_badge = Paragraph(
            "<b>CANCELLED</b>",
            ParagraphStyle("StCancel", alignment=2, fontName="Helvetica-Bold", fontSize=7.5,
                           textColor=colors.white, backColor=colors.HexColor("#dc2626"), spaceBefore=1.5 * mm),
        )
    elif receipt.legacy_due_amount > 0:
        status_badge = Paragraph(
            f"<b>DUE: Rs. {_money(receipt.legacy_due_amount)}</b>",
            ParagraphStyle("StDue", alignment=2, fontName="Helvetica-Bold", fontSize=7.5,
                           textColor=colors.white, backColor=colors.HexColor("#dc2626"), spaceBefore=1.5 * mm),
        )
    else:
        status_badge = Paragraph(
            "<b>FULLY PAID</b>",
            ParagraphStyle("StPaid", alignment=2, fontName="Helvetica-Bold", fontSize=7.5,
                           textColor=colors.white, backColor=colors.HexColor("#15803d"), spaceBefore=1.5 * mm),
        )

    # Right cell (Receipt No + Status Badge)
    rno_cell = [
        Paragraph("RECEIPT NO", rno_style),
        Paragraph(escape(receipt.receipt_no), rno_val_style),
        status_badge,
    ]

    # Center cell (School Info)
    center_cell = [
        Paragraph(f"<b>{escape(school_name.upper())}</b>", title_style),
        Paragraph(escape(school_address), school_sub_style),
        Paragraph(escape(school_contact), school_sub_style),
        _devanagari_flowable(
            "FEE RECEIPT (फीस रसीद)",
            7.5,
            bold=True,
            align=1,
            color=(15, 118, 110, 255),
        ),
    ]

    # Top Header Table (3 Columns: Logo, School Info, Receipt Info)
    header_table = Table([[logo_flowable, center_cell, rno_cell]], colWidths=[20 * mm, 114 * mm, 48 * mm])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 1 * mm))

    # 2. Dual-Tone Accent Line (Teal + Gold)
    accent_data = [[""], [""]]
    accent_table = Table(accent_data, colWidths=[182 * mm], rowHeights=[1.2 * mm, 0.6 * mm])
    accent_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), brand_color),
                ("BACKGROUND", (0, 1), (0, 1), brand_gold),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(accent_table)
    story.append(Spacer(1, 1.5 * mm))

    # 3. Structured Metadata Card (4 Columns)
    student = receipt.student
    class_label = receipt.display_class_section
    month_label = receipt.from_month
    if receipt.to_month and receipt.to_month != receipt.from_month:
        month_label = f"{receipt.from_month} to {receipt.to_month}"

    session_name = receipt.session.name if receipt.session else "2026-27"
    father_name = student.father_name if student and student.father_name else "-"
    sid_adm = f"{student.legacy_sid or ''} / {student.admission_no or ''}" if student else "-"

    meta_lbl_style = ParagraphStyle(
        "MLbl",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=5.8,
        leading=6.8,
        textColor=colors.HexColor("#475569"),
    )
    meta_val_style = ParagraphStyle(
        "MVal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.2,
        leading=7.2,
        textColor=text_color,
    )

    def m_cell(txt, is_val=False, is_bold=False):
        style = meta_val_style if is_val else meta_lbl_style
        font_tag = f"<b>{escape(str(txt))}</b>" if (is_bold or not is_val) else escape(str(txt))
        return Paragraph(font_tag, style)

    meta_grid = [
        [m_cell("Student Name"), m_cell(receipt.display_student_name, True, True), m_cell("Receipt Date"), m_cell(receipt.receipt_date.strftime("%d-%m-%Y"), True)],
        [m_cell("Father's Name"), m_cell(father_name, True), m_cell("Class & Sec"), m_cell(class_label, True, True)],
        [m_cell("SID / Adm No"), m_cell(sid_adm, True), m_cell("Fee Month"), m_cell(month_label, True, True)],
        [m_cell("Payment Mode"), m_cell(receipt.get_payment_mode_display(), True), m_cell("Academic Session"), m_cell(session_name, True)],
    ]
    meta_table = Table(meta_grid, colWidths=[24 * mm, 67 * mm, 24 * mm, 67 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, border_color),
                ("BACKGROUND", (0, 0), (0, -1), light_bg),
                ("BACKGROUND", (2, 0), (2, -1), light_bg),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 1.5 * mm))

    # 4. Itemized Fee Table
    line_rows = [["Fee Head Description", "Amount (Rs.)"]]
    for line in receipt.lines.select_related("fee_head").all():
        line_rows.append([line.fee_head.name, _money(line.amount)])

    body_last_idx = len(line_rows) - 1
    total_start_idx = len(line_rows)
    line_rows.append(["Fee Total", _money(receipt.legacy_fee_total)])

    previous_due_idx = None
    if receipt.previous_due_amount > 0:
        previous_due_idx = len(line_rows)
        line_rows.append(["Previous Due (carried forward)", f"+ {_money(receipt.previous_due_amount)}"])

    concession_idx = None
    if receipt.concession_amount > 0:
        concession_idx = len(line_rows)
        line_rows.append(["Concession / Discount", f"- {_money(receipt.concession_amount)}"])

    late_fee_idx = None
    if receipt.late_fee_amount > 0:
        late_fee_idx = len(line_rows)
        line_rows.append(["Late Fee Fine", f"+ {_money(receipt.late_fee_amount)}"])

    net_idx = len(line_rows)
    line_rows.append(["Net Payable", f"Rs. {_money(receipt.legacy_net_total)}"])
    paid_idx = len(line_rows)
    line_rows.append(["Amount Paid", f"Rs. {_money(receipt.received_amount)}"])

    due_idx = None
    if receipt.legacy_due_amount > 0:
        due_idx = len(line_rows)
        line_rows.append(["Balance Due", f"Rs. {_money(receipt.legacy_due_amount)}"])

    fee_table = Table(line_rows, colWidths=[136 * mm, 46 * mm], repeatRows=1)

    ts = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 6.5),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        # Body Lines
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 1), (-1, -1), 6.2),
        ("TEXTCOLOR", (0, 1), (-1, body_last_idx), text_color),
        ("TOPPADDING", (0, 0), (-1, -1), 1.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        # Totals Section
        ("FONTNAME", (0, total_start_idx), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, total_start_idx), (-1, -1), colors.HexColor("#475569")),
        ("LINEABOVE", (0, total_start_idx), (-1, total_start_idx), 0.8, border_color),
        # Net Payable Row
        ("BACKGROUND", (0, net_idx), (-1, net_idx), light_bg),
        ("TEXTCOLOR", (0, net_idx), (-1, net_idx), text_color),
        ("FONTSIZE", (0, net_idx), (-1, net_idx), 7.0),
        ("LINEABOVE", (0, net_idx), (-1, net_idx), 0.8, border_color),
        ("LINEBELOW", (0, net_idx), (-1, net_idx), 0.8, border_color),
        # Amount Paid Row
        ("TEXTCOLOR", (0, paid_idx), (-1, paid_idx), colors.HexColor("#15803d")),
        ("FONTSIZE", (0, paid_idx), (-1, paid_idx), 7.2),
    ]

    if body_last_idx >= 1:
        ts.append(("LINEBELOW", (0, 1), (-1, body_last_idx), 0.4, colors.HexColor("#f1f5f9")))

    if previous_due_idx is not None:
        ts.append(("TEXTCOLOR", (0, previous_due_idx), (-1, previous_due_idx), colors.HexColor("#7c3aed")))

    if concession_idx is not None:
        ts.append(("TEXTCOLOR", (0, concession_idx), (-1, concession_idx), colors.HexColor("#15803d")))

    if late_fee_idx is not None:
        ts.append(("TEXTCOLOR", (0, late_fee_idx), (-1, late_fee_idx), colors.HexColor("#d97706")))

    if due_idx is not None:
        ts.append(("TEXTCOLOR", (0, due_idx), (-1, due_idx), colors.HexColor("#dc2626")))
        ts.append(("FONTSIZE", (0, due_idx), (-1, due_idx), 7.2))

    fee_table.setStyle(TableStyle(ts))
    story.append(fee_table)

    if receipt.remarks:
        story.extend([Spacer(1, 1 * mm), Paragraph(f"<i>Remarks: {escape(receipt.remarks)}</i>", meta_lbl_style)])

    # 5. Signatures & Footer Note
    sig_data = [
        [
            Paragraph("Cashier's Signature<br/>___________________", meta_lbl_style),
            Paragraph("Parent / Guardian Signature<br/>___________________", meta_lbl_style),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[91 * mm, 91 * mm])
    sig_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.extend([Spacer(1, 2 * mm), sig_table])

    return story


def build_fee_receipt_pdf(receipt, school_profile=None):
    """Generate executive standard A5 Landscape Fee Receipt PDF."""
    buffer = BytesIO()
    page_size = landscape(A5)  # 210mm x 148mm
    page_width, page_height = page_size

    document = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=5 * mm,
        bottomMargin=5 * mm,
        title=f"Fee Receipt {receipt.receipt_no}",
    )

    story = _build_fee_receipt_story(receipt, school_profile)

    def add_watermark(canvas, doc):
        canvas.saveState()
        if receipt.is_cancelled:
            canvas.setFont("Helvetica-Bold", 55)
            canvas.setFillColor(colors.HexColor("#dc2626"), alpha=0.18)
            canvas.translate(page_width / 2, page_height / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "CANCELLED")
        elif receipt.is_edited:
            canvas.setFont("Helvetica-Bold", 55)
            canvas.setFillColor(colors.HexColor("#f59e0b"), alpha=0.18)
            canvas.translate(page_width / 2, page_height / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "EDITED")
            canvas.restoreState()
            canvas.saveState()
            canvas.setFont("Helvetica", 5.5)
            canvas.setFillColor(colors.HexColor("#b45309"))
            footer_text = f"Edited on {receipt.edited_at.strftime('%d-%m-%Y %H:%M')} by {receipt.edited_by.username if receipt.edited_by else 'System'}. Reason: {receipt.edit_reason}"
            canvas.drawCentredString(page_width / 2, 3 * mm, footer_text[:115])
        else:
            canvas.setFont("Helvetica-Bold", 60)
            canvas.setFillColor(colors.HexColor("#0f766e"), alpha=0.035)
            canvas.translate(page_width / 2, page_height / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "THPSIC")
        canvas.restoreState()

    document.build(story, onFirstPage=add_watermark, onLaterPages=add_watermark)
    buffer.seek(0)
    return buffer.getvalue()


def build_fee_receipt_pdf_2up(receipt, school_profile=None):
    """
    Generate A4 Portrait PDF with the receipt positioned strictly in the top half (A5 size).
    The bottom half remains completely blank, allowing the paper to be re-fed into a printer.
    """
    buffer = BytesIO()
    page_width, page_height = A4  # 210mm x 297mm

    top_frame = Frame(
        14 * mm,
        148.5 * mm + 4 * mm,
        182 * mm,
        138 * mm,
        id="top_half_frame",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        title=f"Fee Receipt {receipt.receipt_no} (Half A4)",
    )

    def draw_top_watermark_and_divider(canvas, document):
        canvas.saveState()
        center_x = page_width / 2
        center_y = 148.5 * mm + (148.5 * mm / 2)

        if receipt.is_cancelled:
            canvas.setFont("Helvetica-Bold", 55)
            canvas.setFillColor(colors.HexColor("#dc2626"), alpha=0.18)
            canvas.translate(center_x, center_y)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "CANCELLED")
        elif receipt.is_edited:
            canvas.setFont("Helvetica-Bold", 55)
            canvas.setFillColor(colors.HexColor("#f59e0b"), alpha=0.18)
            canvas.translate(center_x, center_y)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "EDITED")
            canvas.restoreState()
            canvas.saveState()
            canvas.setFont("Helvetica", 5.5)
            canvas.setFillColor(colors.HexColor("#b45309"))
            footer_text = f"Edited on {receipt.edited_at.strftime('%d-%m-%Y %H:%M')} by {receipt.edited_by.username if receipt.edited_by else 'System'}. Reason: {receipt.edit_reason}"
            canvas.drawCentredString(center_x, 148.5 * mm + 3 * mm, footer_text[:115])
        else:
            canvas.setFont("Helvetica-Bold", 60)
            canvas.setFillColor(colors.HexColor("#0f766e"), alpha=0.035)
            canvas.translate(center_x, center_y)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "THPSIC")
        canvas.restoreState()

        # Subtle cutting / fold guide line at mid-page
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
        canvas.setLineWidth(0.5)
        canvas.setDash([2, 4])
        canvas.line(10 * mm, 148.5 * mm, 200 * mm, 148.5 * mm)
        canvas.restoreState()

    template = PageTemplate(id="half_a4_top", frames=[top_frame], onPage=draw_top_watermark_and_divider)
    doc.addPageTemplates([template])

    story = _build_fee_receipt_story(receipt, school_profile)
    doc.build(story)

    buffer.seek(0)
    return buffer.getvalue()



def build_due_report_pdf(rows, totals, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="Due Report",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DueReportTitle",
        parent=styles["Title"],
        fontSize=15,
        leading=18,
        alignment=1,
        spaceAfter=1 * mm,
    )
    small_style = ParagraphStyle(
        "DueReportSmall",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=1,
    )

    school_name = school_profile.name if school_profile else "SchoolSoft Modernization"
    school_address = school_profile.address if school_profile else ""
    contact_parts = []
    if school_profile and school_profile.phone:
        contact_parts.append(f"Phone: {school_profile.phone}")
    if school_profile and school_profile.email:
        contact_parts.append(f"Email: {school_profile.email}")

    story = [Paragraph(school_name, title_style)]
    if school_address:
        story.append(Paragraph(school_address, small_style))
    if contact_parts:
        story.append(Paragraph(" | ".join(contact_parts), small_style))
    story.extend(
        [
            Paragraph("Due Report", small_style),
            Spacer(1, 4 * mm),
        ]
    )

    summary_rows = [
        ["Students", str(len(rows)), "Net", money(totals.get("net") or 0), "Paid", money(totals.get("paid") or 0), "Due", money(totals.get("due") or 0)]
    ]
    summary_table = Table(summary_rows, colWidths=[22 * mm, 18 * mm, 16 * mm, 28 * mm, 16 * mm, 28 * mm, 16 * mm, 28 * mm])
    summary_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("ALIGN", (3, 0), (3, 0), "RIGHT"),
                ("ALIGN", (5, 0), (5, 0), "RIGHT"),
                ("ALIGN", (7, 0), (7, 0), "RIGHT"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([summary_table, Spacer(1, 4 * mm)])

    table_rows = [["SID", "Student", "Father", "Class", "Mobile", "Net", "Paid", "Due"]]
    for row in rows:
        class_label = row.get("student__current_class__name") or ""
        section = row.get("student__current_section__name")
        if section:
            class_label = f"{class_label}-{section}" if class_label else section

        table_rows.append(
            [
                row.get("student__legacy_sid") or "",
                row.get("student__full_name") or "",
                row.get("student__father_name") or "",
                class_label,
                row.get("student__mobile_primary") or "",
                money(row.get("net_amount") or 0),
                money(row.get("paid_amount") or 0),
                money(row.get("due_amount") or 0),
            ]
        )

    due_table = Table(
        table_rows,
        colWidths=[17 * mm, 48 * mm, 48 * mm, 20 * mm, 30 * mm, 27 * mm, 27 * mm, 27 * mm],
        repeatRows=1,
    )
    due_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8d0dc")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
                ("FONTNAME", (7, 1), (7, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(due_table)

    document.build(story, onFirstPage=draw_page_footer, onLaterPages=draw_page_footer)
    buffer.seek(0)
    return buffer.getvalue()



def _due_pdf_text(value, style):
    return Paragraph(escape(str(value or "")), style)


def _due_pdf_school_address(school_profile):
    if not school_profile:
        return ""
    return getattr(school_profile, "address", "") or ""


def build_due_up_to_month_report_pdf(
    rows,
    totals,
    school_profile=None,
    session=None,
    through_month="",
    target_label="",
):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=8 * mm,
        leftMargin=8 * mm,
        topMargin=8 * mm,
        bottomMargin=10 * mm,
        title=f"Due up to {target_label or through_month}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DueMonthPdfTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        alignment=1,
        textColor=colors.HexColor("#155e4b"),
        spaceAfter=1 * mm,
    )
    subtitle_style = ParagraphStyle(
        "DueMonthPdfSubtitle",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
        alignment=1,
        textColor=colors.HexColor("#4b635b"),
    )
    header_style = ParagraphStyle(
        "DueMonthPdfHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.2,
        leading=7.2,
        alignment=1,
        textColor=colors.HexColor("#173a30"),
    )
    cell_style = ParagraphStyle(
        "DueMonthPdfCell",
        parent=styles["Normal"],
        fontSize=6.2,
        leading=7.4,
    )
    small_cell_style = ParagraphStyle(
        "DueMonthPdfSmallCell",
        parent=cell_style,
        fontSize=5.6,
        leading=6.8,
        textColor=colors.HexColor("#53665f"),
    )

    school_name = school_profile.name if school_profile else "SchoolSoft"
    session_name = session.name if session else "Session not selected"
    story = [
        _due_pdf_text(school_name.upper(), title_style),
        _due_pdf_text(_due_pdf_school_address(school_profile), subtitle_style),
        _due_pdf_text(
            f"DUE UP TO MONTH: {target_label or through_month} | Session {session_name}",
            subtitle_style,
        ),
        Spacer(1, 2.5 * mm),
    ]

    summary_data = [
        [
            "Students",
            str(totals.get("students", 0)),
            "Gross Demand",
            f"Rs. {money(totals.get('gross_demand') or 0)}",
            "Paid",
            f"Rs. {money(totals.get('received_amount') or 0)}",
            "Final Due",
            f"Rs. {money(totals.get('due_amount') or 0)}",
            "Credit",
            f"Rs. {money(totals.get('credit_amount') or 0)}",
        ]
    ]
    summary = Table(
        summary_data,
        colWidths=[18 * mm, 17 * mm, 23 * mm, 28 * mm, 14 * mm, 27 * mm, 18 * mm, 27 * mm, 15 * mm, 27 * mm],
    )
    summary.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#a9bbb4")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#edf5f2")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.8),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("ALIGN", (3, 0), (3, 0), "RIGHT"),
                ("ALIGN", (5, 0), (5, 0), "RIGHT"),
                ("ALIGN", (7, 0), (7, 0), "RIGHT"),
                ("ALIGN", (9, 0), (9, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([summary, Spacer(1, 2.5 * mm)])

    table_rows = [
        [
            _due_pdf_text("SID / Adm", header_style),
            _due_pdf_text("Student / Father", header_style),
            _due_pdf_text("Class", header_style),
            _due_pdf_text("Type", header_style),
            _due_pdf_text("Demand", header_style),
            "",
            "",
            "",
            "",
            _due_pdf_text("Credits Applied", header_style),
            "",
            _due_pdf_text("Final Due", header_style),
            _due_pdf_text("Final Credit", header_style),
        ],
        [
            "",
            "",
            "",
            "",
            _due_pdf_text("School", header_style),
            _due_pdf_text("Transport", header_style),
            _due_pdf_text("Opening", header_style),
            _due_pdf_text("Late", header_style),
            _due_pdf_text("Gross", header_style),
            _due_pdf_text("Paid", header_style),
            _due_pdf_text("Concession", header_style),
            "",
            "",
        ],
    ]

    for row in rows:
        student = row["student"]
        result = row["result"]
        sid = student.legacy_sid or "-"
        admission = student.admission_no or "-"
        student_text = escape(student.full_name or "")
        father_text = escape(student.father_name or "Father/guardian not set")
        table_rows.append(
            [
                Paragraph(f"<b>{escape(str(sid))}</b><br/><font size='5.4'>Adm: {escape(str(admission))}</font>", cell_style),
                Paragraph(f"<b>{student_text}</b><br/><font size='5.4'>Father: {father_text}</font>", cell_style),
                _due_pdf_text(row["class_label"], cell_style),
                _due_pdf_text(row["student_type"], small_cell_style),
                _due_pdf_text(money(result.scheduled_fee_demand), cell_style),
                _due_pdf_text(money(result.transport_demand), cell_style),
                _due_pdf_text(money(result.opening_balance_amount), cell_style),
                _due_pdf_text(money(result.late_fee_amount), cell_style),
                _due_pdf_text(money(result.gross_demand), cell_style),
                _due_pdf_text(money(result.received_amount), cell_style),
                _due_pdf_text(money(result.concession_amount), cell_style),
                _due_pdf_text(money(result.due_amount), cell_style),
                _due_pdf_text(money(result.credit_amount), cell_style),
            ]
        )

    if not rows:
        table_rows.append([_due_pdf_text("No student balances match the selected filters.", cell_style)] + [""] * 12)

    widths = [24, 45, 17, 14, 20, 19, 18, 14, 20, 20, 18, 21, 20]
    report_table = Table(
        table_rows,
        colWidths=[value * mm for value in widths],
        repeatRows=2,
    )
    style_commands = [
        ("SPAN", (0, 0), (0, 1)),
        ("SPAN", (1, 0), (1, 1)),
        ("SPAN", (2, 0), (2, 1)),
        ("SPAN", (3, 0), (3, 1)),
        ("SPAN", (4, 0), (8, 0)),
        ("SPAN", (9, 0), (10, 0)),
        ("SPAN", (11, 0), (11, 1)),
        ("SPAN", (12, 0), (12, 1)),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bdcac5")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcece6")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#edf5f2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (4, 2), (-1, -1), "RIGHT"),
        ("FONTNAME", (11, 2), (12, -1), "Helvetica-Bold"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if not rows:
        style_commands.append(("SPAN", (0, 2), (-1, 2)))
        style_commands.append(("ALIGN", (0, 2), (-1, 2), "CENTER"))
    report_table.setStyle(TableStyle(style_commands))
    story.append(report_table)

    document.build(story, onFirstPage=draw_page_footer, onLaterPages=draw_page_footer)
    buffer.seek(0)
    return buffer.getvalue()


def _draw_due_flowable(canvas, flowable, x, top, width, max_height=1000):
    _, height = flowable.wrap(width, max_height)
    flowable.drawOn(canvas, x, top - height)
    return top - height


def _draw_due_table(canvas, table, x, top, width):
    _, height = table.wrap(width, 1000)
    table.drawOn(canvas, x, top - height)
    return top - height



def _due_slip_public_fee_rows(result, target_label):
    """Return the guardian-safe financial summary for a Due Slip.

    Payment and concession details are deliberately office-only. Showing
    those values on slips distributed to a class could disclose one child's
    private concession to another family.
    """
    target = target_label or result.through_month
    return [
        (f"TOTAL FEE DEMAND (UP TO {target})", f"Rs. {money(result.gross_demand)}"),
        ("AMOUNT DUE NOW", f"Rs. {money(result.due_amount)}"),
    ]


_DUE_SLIP_GUARDIAN_MESSAGE_LINES = (
    "आपके बच्चे का उज्ज्वल भविष्य ही हमारा लक्ष्य है।",
    "समय पर शुल्क जमा कर उनकी शिक्षा-यात्रा को निरंतर और सशक्त बनाएँ।",
    "आपके विश्वास और सहयोग के लिए THPS परिवार हृदय से आभारी है।",
)
_DUE_SLIP_GUARDIAN_ENGLISH_NOTE = (
    "Please deposit the amount due at the school office and collect the official receipt."
)


def _draw_due_slip_card(canvas, x, y, width, height, row, school_profile, session, target_label):
    student = row["student"]
    result = row["result"]
    green = colors.HexColor("#176b57")
    pale_green = colors.HexColor("#edf7f3")
    pale_gold = colors.HexColor("#fff7dd")
    grid = colors.HexColor("#b8c7c1")
    gold = colors.HexColor("#c89316")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DueSlipTitleCompact",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8,
        textColor=green,
    )
    header_name_style = ParagraphStyle(
        "DueSlipSchoolCompact",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=8.8,
        alignment=1,
        textColor=colors.white,
    )
    header_detail_style = ParagraphStyle(
        "DueSlipSchoolDetailCompact",
        parent=styles["Normal"],
        fontSize=4.8,
        leading=5.5,
        alignment=1,
        textColor=colors.white,
    )
    text_style = ParagraphStyle(
        "DueSlipTextCompact",
        parent=styles["Normal"],
        fontSize=5.7,
        leading=6.7,
    )
    label_style = ParagraphStyle(
        "DueSlipLabelCompact",
        parent=text_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#2d4940"),
    )
    right_style = ParagraphStyle(
        "DueSlipRightCompact",
        parent=text_style,
        alignment=2,
    )
    due_style = ParagraphStyle(
        "DueSlipDueCompact",
        parent=text_style,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=9,
        textColor=colors.HexColor("#9f1d1d"),
    )
    due_right_style = ParagraphStyle(
        "DueSlipDueRightCompact",
        parent=due_style,
        alignment=2,
    )
    note_style = ParagraphStyle(
        "DueSlipNoteCompact",
        parent=text_style,
        fontSize=5.1,
        leading=6,
        alignment=1,
        textColor=colors.HexColor("#4c5f58"),
    )

    canvas.saveState()
    canvas.setStrokeColor(green)
    canvas.setLineWidth(0.75)
    canvas.roundRect(x, y, width, height, 1.8 * mm, stroke=1, fill=0)

    header_height = 10.5 * mm
    canvas.setFillColor(green)
    canvas.roundRect(x, y + height - header_height, width, header_height, 1.8 * mm, stroke=0, fill=1)
    canvas.rect(x, y + height - header_height, width, 1.8 * mm, stroke=0, fill=1)
    inner_x = x + 3 * mm
    inner_width = width - 6 * mm
    header_top = y + height - 1.8 * mm
    school_name = school_profile.name if school_profile else "SchoolSoft"
    header_top = _draw_due_flowable(
        canvas,
        _due_pdf_text(school_name.upper(), header_name_style),
        inner_x,
        header_top,
        inner_width,
    )
    details = _due_pdf_school_address(school_profile)
    if school_profile and school_profile.phone:
        details = f"{details} | Ph: {school_profile.phone}" if details else f"Ph: {school_profile.phone}"
    _draw_due_flowable(
        canvas,
        _due_pdf_text(details, header_detail_style),
        inner_x,
        header_top - 0.1 * mm,
        inner_width,
    )

    notice_sid = student.legacy_sid or student.pk
    cursor = y + height - header_height - 1.2 * mm
    title_row = Table(
        [[
            _due_pdf_text(f"FEE DUE NOTICE - UP TO {target_label or result.through_month}", title_style),
            _due_pdf_text(f"DUE/{result.through_month}/{notice_sid}", right_style),
        ]],
        colWidths=[inner_width * 0.72, inner_width * 0.28],
    )
    title_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    cursor = _draw_due_table(canvas, title_row, inner_x, cursor, inner_width) - 0.5 * mm

    session_name = session.name if session else "-"
    student_info = Table(
        [
            [_due_pdf_text("Student", label_style), _due_pdf_text(student.full_name, text_style), _due_pdf_text("SID", label_style), _due_pdf_text(notice_sid, text_style)],
            [_due_pdf_text("Father", label_style), _due_pdf_text(student.father_name or "-", text_style), _due_pdf_text("Class", label_style), _due_pdf_text(row["class_label"], text_style)],
            [_due_pdf_text("Adm. No.", label_style), _due_pdf_text(student.admission_no or "-", text_style), _due_pdf_text("Session", label_style), _due_pdf_text(session_name, text_style)],
        ],
        colWidths=[12 * mm, inner_width - 12 * mm - 13 * mm - 23 * mm, 13 * mm, 23 * mm],
    )
    student_info.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, grid),
        ("BACKGROUND", (0, 0), (0, -1), pale_green),
        ("BACKGROUND", (2, 0), (2, -1), pale_green),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ]))
    cursor = _draw_due_table(canvas, student_info, inner_x, cursor, inner_width) - 0.8 * mm

    public_rows = _due_slip_public_fee_rows(result, target_label)
    fee_rows = [
        [_due_pdf_text(public_rows[0][0], label_style), _due_pdf_text(public_rows[0][1], right_style)],
        [_due_pdf_text(public_rows[1][0], due_style), _due_pdf_text(public_rows[1][1], due_right_style)],
    ]
    fee_table = Table(fee_rows, colWidths=[inner_width - 28 * mm, 28 * mm])
    fee_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), pale_green),
        ("BACKGROUND", (0, 1), (-1, 1), pale_gold),
        ("BOX", (0, 0), (-1, -1), 0.65, gold),
        ("LINEABOVE", (0, 1), (-1, 1), 0.65, gold),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, 0), 1.8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1.8),
        ("TOPPADDING", (0, 1), (-1, 1), 2.2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 2.2),
    ]))
    cursor = _draw_due_table(canvas, fee_table, inner_x, cursor, inner_width) - 0.7 * mm

    guardian_message = Table(
        [
            [
                _devanagari_flowable(
                    line,
                    6.4,
                    bold=True,
                    align=1,
                    color=(23, 107, 87, 255),
                )
            ]
            for line in _DUE_SLIP_GUARDIAN_MESSAGE_LINES
        ],
        colWidths=[inner_width],
    )
    guardian_message.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale_green),
        ("BOX", (0, 0), (-1, -1), 0.45, gold),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0.45),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.45),
        ("TOPPADDING", (0, 0), (0, 0), 1.2),
        ("BOTTOMPADDING", (0, -1), (0, -1), 1.2),
    ]))
    cursor = _draw_due_table(canvas, guardian_message, inner_x, cursor, inner_width) - 0.45 * mm
    _draw_due_flowable(
        canvas,
        _due_pdf_text(_DUE_SLIP_GUARDIAN_ENGLISH_NOTE, note_style),
        inner_x,
        cursor,
        inner_width,
    )

    signature_y = y + 2.5 * mm
    line_width = 20 * mm
    canvas.setStrokeColor(grid)
    canvas.setLineWidth(0.35)
    canvas.line(inner_x, signature_y + 3.3 * mm, inner_x + line_width, signature_y + 3.3 * mm)
    canvas.line(x + width - 3 * mm - line_width, signature_y + 3.3 * mm, x + width - 3 * mm, signature_y + 3.3 * mm)
    canvas.setFont("Helvetica", 5)
    canvas.setFillColor(colors.HexColor("#50635c"))
    canvas.drawCentredString(inner_x + line_width / 2, signature_y + 1.2 * mm, "Accounts Clerk")
    canvas.drawCentredString(x + width - 3 * mm - line_width / 2, signature_y + 1.2 * mm, "Principal / Seal")
    canvas.restoreState()



def build_due_slip_pdf(
    rows,
    school_profile=None,
    session=None,
    through_month="",
    target_label="",
):
    notices = [row for row in rows if row["result"].due_amount > Decimal("0.00")]
    buffer = BytesIO()
    page_width, page_height = A4
    margin = 5 * mm
    horizontal_gap = 2 * mm
    vertical_gap = 2 * mm
    columns = 2
    rows_per_page = 4
    slips_per_page = columns * rows_per_page
    card_width = (page_width - (2 * margin) - horizontal_gap) / columns
    card_height = (page_height - (2 * margin) - ((rows_per_page - 1) * vertical_gap)) / rows_per_page
    pdf = pdf_canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    pdf.setTitle(f"Due slips up to {target_label or through_month}")
    pdf.setAuthor(school_profile.name if school_profile else "SchoolSoft")

    if not notices:
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawCentredString(page_width / 2, page_height / 2 + 8, "No positive due balances match these filters.")
        pdf.setFont("Helvetica", 9)
        pdf.drawCentredString(page_width / 2, page_height / 2 - 10, f"Target: {target_label or through_month}")
        pdf.showPage()
    else:
        for page_start in range(0, len(notices), slips_per_page):
            for slot, row in enumerate(notices[page_start:page_start + slips_per_page]):
                column = slot % columns
                row_index = slot // columns
                card_x = margin + column * (card_width + horizontal_gap)
                card_y = margin + (rows_per_page - 1 - row_index) * (card_height + vertical_gap)
                _draw_due_slip_card(
                    pdf,
                    card_x,
                    card_y,
                    card_width,
                    card_height,
                    row,
                    school_profile,
                    session,
                    target_label,
                )

            pdf.setStrokeColor(colors.HexColor("#8c948f"))
            pdf.setDash(2, 2)
            pdf.line(page_width / 2, margin, page_width / 2, page_height - margin)
            for boundary in range(1, rows_per_page):
                cut_y = margin + boundary * card_height + (boundary - 0.5) * vertical_gap
                pdf.line(margin, cut_y, page_width - margin, cut_y)
            pdf.setDash()
            pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def draw_page_footer(canvas, document):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(287 * mm, 7 * mm, f"Page {document.page}")
    canvas.restoreState()


def money(value):
    return f"{value:,.2f}"


def _school_header(story, school_profile, title_text, styles):
    brand_color = colors.HexColor("#0f766e")
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Title"],
        fontSize=18,
        leading=22,
        alignment=1,
        textColor=brand_color,
        fontName="Helvetica-Bold",
        spaceAfter=1 * mm,
    )
    small_style = ParagraphStyle(
        "DocSmall",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        alignment=1,
    )
    heading_style = ParagraphStyle(
        "DocHeading",
        parent=styles["Normal"],
        fontSize=14,
        leading=16,
        alignment=1,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=5 * mm,
        spaceAfter=6 * mm,
    )

    school_name = school_profile.name if school_profile else "SchoolSoft"
    story.append(Paragraph(school_name.upper(), title_style))
    
    if school_profile and getattr(school_profile, 'address_line1', ''):
        addr = f"{school_profile.address_line1}, {school_profile.address_line2}".strip(", ")
        story.append(Paragraph(addr, small_style))
    elif school_profile and getattr(school_profile, 'address', ''):
        story.append(Paragraph(school_profile.address, small_style))

    contact_parts = []
    if school_profile and school_profile.phone:
        contact_parts.append(f"Phone: {school_profile.phone}")
    if school_profile and school_profile.email:
        contact_parts.append(f"Email: {school_profile.email}")
    if contact_parts:
        story.append(Paragraph(" | ".join(contact_parts), small_style))
        
    story.append(Spacer(1, 4 * mm))
    line = Table([[""]], colWidths=[180*mm])
    line.setStyle(TableStyle([("LINEABOVE", (0,0), (-1,-1), 1.5, brand_color)]))
    story.append(line)
    
    story.append(Paragraph(title_text, heading_style))


def build_admission_form_pdf(student, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Admission Form - {student.full_name}",
    )
    styles = getSampleStyleSheet()
    story = []
    _school_header(story, school_profile, "ADMISSION FORM", styles)

    class_label = student.current_class.name if student.current_class else ""
    if student.current_section:
        class_label = f"{class_label}-{student.current_section.name}" if class_label else student.current_section.name

    rows = [
        ["Admission No.", student.admission_no or "", "Registration No.", student.registration_no or ""],
        ["SID", student.legacy_sid or "", "Admission Date", student.admission_date.strftime("%d-%m-%Y") if student.admission_date else ""],
        ["Student Name", student.full_name, "Gender", student.get_gender_display()],
        ["Father's Name", student.father_name or "", "Mother's Name", student.mother_name or ""],
        ["Date of Birth", student.date_of_birth.strftime("%d-%m-%Y") if student.date_of_birth else "", "Roll No.", student.roll_no or ""],
        ["Class", class_label, "Category", student.category or ""],
        [
            "Exam Medium",
            student.get_exam_medium_display() if getattr(student, "exam_medium", "") else "",
            "Subject Group",
            student.get_subject_group_display() if getattr(student, "subject_group", "") else "",
        ],
        [
            "Candidate Type 1",
            student.get_board_candidate_type_1_code_display() if getattr(student, "board_candidate_type_1_code", "") else "",
            "Candidate Type 2",
            student.get_board_candidate_type_2_code_display() if getattr(student, "board_candidate_type_2_code", "") else "",
        ],
        [
            "Board Caste Code",
            student.get_board_caste_code_display() if getattr(student, "board_caste_code", "") else "",
            "Sr Number",
            getattr(student, "board_sr_number", "") or "",
        ],
        ["Religion", student.religion or "", "Aadhaar No.", student.aadhaar_no or ""],
        ["Mobile (Primary)", student.mobile_primary or "", "Mobile (Alternate)", student.mobile_secondary or ""],
    ]
    table = Table(rows, colWidths=[38 * mm, 52 * mm, 38 * mm, 52 * mm])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f1f5f9")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([table, Spacer(1, 6 * mm)])

    address_rows = [
        ["Street / Mohalla / Area", getattr(student, "address_street_area", "") or ""],
        ["Village / Town / City", student.village_locality or ""],
        ["Post Office", student.post or ""],
        ["Tehsil / Block", student.block or ""],
        ["District / State / PIN", " / ".join(part for part in [student.district, getattr(student, "state", ""), student.pin_code] if part)],
        ["Nationality", " / ".join(part for part in [getattr(student, "nationality", ""), getattr(student, "nationality_other", "")] if part)],
        ["Permanent Address", student.address_permanent or ""],
        ["Local Address", student.address_local or ""],
    ]
    address_table = Table(address_rows, colWidths=[38 * mm, 142 * mm])
    address_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(address_table)

    subject_codes = [
        getattr(student, "subject_1_code", ""),
        getattr(student, "subject_2_code", ""),
        getattr(student, "subject_3_code", ""),
        getattr(student, "subject_4_code", ""),
        getattr(student, "subject_5_code", ""),
        getattr(student, "subject_6_code", ""),
        getattr(student, "subject_7_code", ""),
        getattr(student, "subject_voc_code", ""),
        getattr(student, "subject_rev_voc_code", ""),
    ]
    if any(subject_codes):
        story.extend([Spacer(1, 6 * mm), Paragraph("Board Subjects", styles["Heading3"])])
        subject_rows = [
            ["1st", subject_codes[0] or "", "2nd", subject_codes[1] or "", "3rd", subject_codes[2] or ""],
            ["4th", subject_codes[3] or "", "5th", subject_codes[4] or "", "6th", subject_codes[5] or ""],
            ["7th", subject_codes[6] or "", "VOC", subject_codes[7] or "", "RevVOC", subject_codes[8] or ""],
        ]
        subject_table = Table(subject_rows, colWidths=[18 * mm, 42 * mm, 18 * mm, 42 * mm, 18 * mm, 42 * mm])
        subject_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f1f5f9")),
                    ("BACKGROUND", (4, 0), (4, -1), colors.HexColor("#f1f5f9")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("FONTNAME", (4, 0), (4, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(subject_table)

    story.extend(
        [
            Spacer(1, 20 * mm),
            Table(
                [["Parent/Guardian Signature", "Class Teacher", "Principal"]],
                colWidths=[60 * mm, 60 * mm, 60 * mm],
                style=TableStyle(
                    [
                        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ]
                ),
            ),
        ]
    )

    document.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def date_to_words(d):
    if not d: return ""
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    
    def num2word(n):
        if n == 0: return "Zero"
        if n < 20: return ones[n]
        if n < 100: return (tens[n//10] + " " + ones[n%10]).strip()
        if n < 1000: return (ones[n//100] + " Hundred " + num2word(n%100)).strip()
        if n < 100000: return (num2word(n//1000) + " Thousand " + num2word(n%1000)).strip()
        return str(n)
        
    return f"{num2word(d.day)} {months[d.month - 1]} {num2word(d.year)}"

def build_transfer_certificate_pdf(tc, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=13 * mm,
        leftMargin=13 * mm,
        topMargin=11 * mm,
        bottomMargin=11 * mm,
        title=f"Transfer Certificate - {tc.tc_number}",
    )
    styles = getSampleStyleSheet()
    story = []

    # English-only student copy. Sizes stay comfortably above the original
    # compact layout while preserving a single-page A4 certificate.
    brand_color = colors.HexColor("#0f766e")
    title_style = ParagraphStyle(
        "TcTitle", parent=styles["Title"], fontSize=18, leading=21, alignment=1,
        textColor=brand_color, fontName="Helvetica-Bold", spaceAfter=2*mm,
    )
    school_name_style = ParagraphStyle(
        "TcSchoolName", parent=styles["Title"], fontSize=20, leading=23, alignment=1,
        textColor=brand_color, fontName="Times-Bold", spaceAfter=0.5*mm,
    )
    small_style = ParagraphStyle(
        "TcSmall", parent=styles["Normal"], fontSize=8.8, leading=10.5, alignment=1
    )
    field_style = ParagraphStyle(
        "TcField", parent=styles["Normal"], fontName="Helvetica", fontSize=9.2, leading=11
    )
    value_style = ParagraphStyle(
        "TcValue", parent=styles["Normal"], fontSize=9.2, leading=11, fontName="Helvetica-Bold"
    )
    meta_left_style = ParagraphStyle("TcMetaLeft", parent=styles["Normal"], fontSize=8.4, leading=10, alignment=0)
    meta_center_style = ParagraphStyle("TcMetaCenter", parent=meta_left_style, alignment=1)
    meta_right_style = ParagraphStyle("TcMetaRight", parent=meta_left_style, alignment=2)

    school_name = school_profile.name if school_profile else "SCHOOLSOFT"
    logo_path = os.path.join(settings.BASE_DIR, "static", "core", "school_logo.png")
    school_heading = [Paragraph(school_name.upper(), school_name_style)]
    if school_profile and school_profile.address_line1:
        addr = f"{school_profile.address_line1}, {school_profile.address_line2}".strip(", ")
        school_heading.append(Paragraph(addr, small_style))

    contact_parts = []
    if school_profile and school_profile.phone: contact_parts.append(f"Ph: {school_profile.phone}")
    if school_profile and school_profile.email: contact_parts.append(f"Email: {school_profile.email}")
    if school_profile and getattr(school_profile, 'udise_code', None): contact_parts.append(f"UDISE: {school_profile.udise_code}")
    if contact_parts:
        school_heading.append(Paragraph(" | ".join(contact_parts), small_style))
    logo = Image(logo_path, 24 * mm, 24 * mm) if os.path.exists(logo_path) else ""
    header = Table([[logo, school_heading, ""]], colWidths=[26 * mm, 132 * mm, 26 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "CENTER")]))
    story.append(header)
    story.append(Table([[""]], colWidths=[184 * mm], rowHeights=[1.2 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#b58a2a"))])))

    story.append(Spacer(1, 3.5 * mm))
    story.append(Paragraph("TRANSFER CERTIFICATE", title_style))

    student = tc.student

    top_meta_values = [
        [
            f"Book No.: {student.scholar_register_no or tc.book_no}",
            f"Withdrawal File No.: {tc.withdrawal_file_no or ''}",
            f"S.R. No.: {tc.sr_no or student.admission_no or student.legacy_sid or ''}",
            f"Admission No.: {student.admission_no}",
        ],
        [
            f"TC No.: {tc.tc_number}",
            f"PEN: {getattr(student, 'pen_number', '')}",
            f"Medium: {getattr(school_profile, 'medium', '') or 'English'}",
            f"UDISE Code: {getattr(school_profile, 'udise_code', '') or '____________'}",
        ],
        [
            f"Recognition Order No.: {getattr(school_profile, 'recognition_no', '') or '____________'}",
            "",
            "",
            f"Recognized up to: {getattr(school_profile, 'recognized_upto', '') or '____________'}",
        ],
    ]
    meta_styles = [meta_left_style, meta_center_style, meta_center_style, meta_right_style]
    top_meta = [[Paragraph(value, meta_styles[index]) for index, value in enumerate(row)] for row in top_meta_values]
    meta_t = Table(top_meta, colWidths=[46*mm, 46*mm, 46*mm, 46*mm])
    meta_t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 8.4),
        ("ALIGN", (0,0), (0,-1), "LEFT"),
        ("ALIGN", (1,0), (2,-1), "CENTER"),
        ("ALIGN", (3,0), (3,-1), "RIGHT"),
        ("SPAN", (0,2), (2,2)),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#9aa5b1")),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3.5), ("TOPPADDING", (0,0), (-1,-1), 3.5),
    ]))
    story.append(meta_t)
    story.append(Spacer(1, 2*mm))

    class_label = tc.last_class_studied.name if tc.last_class_studied else (student.current_class.name if student.current_class else "")
    if tc.last_section: class_label = f"{class_label}-{tc.last_section}" if class_label else tc.last_section

    promoted_class = (tc.promoted_to_class or "").strip()
    promotion_value = "No"
    if tc.qualified_for_promotion:
        promotion_value = f"Yes, promoted to Class {promoted_class}" if promoted_class else "Yes"

    category_bits = []
    for category_value in [student.category, student.caste]:
        if category_value and category_value.casefold() not in {item.casefold() for item in category_bits}:
            category_bits.append(category_value)

    fields = [
        ("1. Name of the Pupil", student.full_name),
        ("2. Mother's Name", student.mother_name or ""),
        ("3. Father's/Guardian's Name", student.father_name or ""),
        ("4. Nationality", getattr(student, 'nationality', 'Indian')),
        ("5. Category / Community", " / ".join(category_bits)),
        ("6. Date of first admission in the School", student.admission_date.strftime('%d-%m-%Y') if student.admission_date else ""),
        ("7. Date of Birth", student.date_of_birth.strftime('%d-%m-%Y') if student.date_of_birth else ""),
        ("   (in words)", date_to_words(student.date_of_birth)),
        ("8. Class in which the pupil last studied", class_label),
        ("9. School/Board Annual Exam last taken with result", tc.annual_exam_result or ""),
        ("10. Whether failed, if so once/twice", "Yes" if getattr(tc, 'whether_failed', False) else "No"),
        ("11. Subjects Studied", getattr(tc, 'subjects_offered', '')),
        ("12. Whether qualified for promotion", promotion_value),
        ("13. Month upto which school dues paid", tc.fees_paid_upto or ""),
        ("14. Any fee concession availed of", getattr(tc, 'fee_concession_nature', '') or "No"),
        ("15. Total No. of working days", str(tc.total_working_days or '')),
        ("16. Total working days present", str(tc.days_present or '')),
        ("17. Whether NCC Cadet/Scout", getattr(tc, 'ncc_scout', '') or "No"),
        ("18. Games played or extra-curricular activities", tc.extracurricular_activities or ""),
        ("19. General progress / Conduct", f"{tc.get_general_progress_display()} / {tc.get_conduct_display()}"),
        ("20. Date of application for certificate", tc.application_date.strftime('%d-%m-%Y') if tc.application_date else ""),
        ("21. Date of issue of certificate", tc.issue_date.strftime('%d-%m-%Y') if tc.issue_date else ""),
        ("22. Reasons for leaving the school", tc.reason_for_leaving or ""),
        ("23. Any other remarks", tc.remarks or "")
    ]

    table_data = []
    for label, val in fields:
        table_data.append([Paragraph(label, field_style), Paragraph(val, value_style)])
        
    t = Table(table_data, colWidths=[102*mm, 82*mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2.8),
        ("TOPPADDING", (0,0), (-1,-1), 2.8),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#9aa5b1")),
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#f7f8f8")),
    ]))
    story.append(t)

    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("CERTIFIED that the above entries have been verified with the Admission/Scholar Register and school records and are correct.", small_style))
    # Reserve real handwriting and seal space above the signature captions.
    story.append(Spacer(1, 12*mm))

    sig_data = [
        ["Prepared by\n(Name & Designation)", "Checked by\n(Name & Designation)", "Head Teacher / Principal\n(Signature with official seal)"]
    ]
    sig_t = Table(sig_data, colWidths=[61.3*mm, 61.3*mm, 61.4*mm])
    sig_t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9.2),
        ("ALIGN", (0,0), (0,0), "LEFT"),
        ("ALIGN", (1,0), (1,0), "CENTER"),
        ("ALIGN", (2,0), (2,0), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "BOTTOM"),
    ]))
    story.append(sig_t)
    story.append(Spacer(1, 6*mm))
    counter = Table([
        ["COUNTERSIGN / OFFICE VERIFICATION (only where required by the competent authority)"],
        ["Verified with original Scholar Register. Signature: ______________  Name/Designation: ______________  Date: ________  Office Seal"],
    ], colWidths=[184*mm])
    counter.setStyle(TableStyle([("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#17202a")), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f3f6f5")), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7.5), ("ALIGN", (0,0), (-1,-1), "CENTER"), ("TOPPADDING", (0,0), (-1,-1), 3.5), ("BOTTOMPADDING", (0,0), (-1,-1), 3.5)]))
    story.append(counter)

    # Thin outer border - same treatment as the Scholar Register - gives the
    # certificate an official bordered-document look instead of a plain print.
    document.build(story, onFirstPage=_draw_scholar_register_border, onLaterPages=_draw_scholar_register_border)
    buffer.seek(0)
    return buffer.getvalue()


# The physical office-only "Scholar's Register" ledger has one row per class
# (Nursery through VIII) with admission/promotion/removal dates for THAT
# class. The system only ever stored a student's CURRENT class - there is no
# year-by-year class history model - so only the row matching the student's
# current class (or, if they've left, the class on their Transfer
# Certificate) can be filled from real data. Every other row is left blank
# and ruled, exactly as office staff already fill it by hand. This was a
# deliberate scope decision, not an oversight - see CODEX-HANDOFF.md.
_SCHOLAR_REGISTER_CLASS_ROWS = ["NUR", "LKG", "UKG", "I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


def _scholar_register_page_flowables(student, school_profile=None, content_width_mm=189):
    """Builds the flowables for ONE student's Scholar Register page. Shared by
    the single-student PDF (build_scholar_register_pdf) and the full physical
    register book PDF (build_scholar_register_book_pdf) so the two documents
    always render identically."""
    styles = getSampleStyleSheet()
    story = []
    width_scale = content_width_mm / 189

    def scaled_widths(widths):
        return [width * width_scale * mm for width in widths]

    brand_color = colors.HexColor("#0f766e")
    title_style = ParagraphStyle(
        "SrTitle", parent=styles["Title"], fontSize=15, leading=18, alignment=1,
        textColor=brand_color, fontName="Helvetica-Bold", spaceAfter=1 * mm,
    )
    school_name_style = ParagraphStyle(
        "SrSchoolName", parent=styles["Title"], fontSize=17.5, leading=20, alignment=1,
        textColor=brand_color, fontName="Times-Bold", spaceAfter=0.2 * mm,
    )
    subtitle_style = ParagraphStyle("SrSubtitle", parent=styles["Normal"], fontSize=9, leading=11, alignment=1)
    small_style = ParagraphStyle("SrSmall", parent=styles["Normal"], fontSize=8.2, leading=10, alignment=1)
    field_style = ParagraphStyle("SrField", parent=styles["Normal"], fontName="Helvetica", fontSize=7.5, leading=9)
    value_style = ParagraphStyle("SrValue", parent=styles["Normal"], fontSize=8.7, leading=10, fontName="Helvetica-Bold")

    school_name = school_profile.name if school_profile else "SCHOOLSOFT"
    logo_path = os.path.join(settings.BASE_DIR, "static", "core", "school_logo.png")
    school_heading = [Paragraph(school_name.upper(), school_name_style)]
    if school_profile and school_profile.address_line1:
        addr = f"{school_profile.address_line1}, {school_profile.address_line2}".strip(", ")
        school_heading.append(Paragraph(addr, small_style))
    contact_parts = []
    if school_profile and school_profile.phone:
        contact_parts.append(f"Ph: {school_profile.phone}")
    if school_profile and school_profile.email:
        contact_parts.append(f"Email: {school_profile.email}")
    if contact_parts:
        school_heading.append(Paragraph(" | ".join(contact_parts), small_style))
    logo = Image(logo_path, 20 * mm, 20 * mm) if os.path.exists(logo_path) else ""
    header = Table([[logo, school_heading, ""]], colWidths=scaled_widths([25, 139, 25]))
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "CENTER")]))
    story.append(header)
    story.append(Table([[""]], colWidths=[content_width_mm * mm], rowHeights=[1.2 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#b58a2a"))])))
    story.append(Spacer(1, 2.5 * mm))
    story.append(Paragraph("SCHOLAR'S REGISTER &amp; TRANSFER CERTIFICATE FORM", title_style))
    story.append(_devanagari_flowable("छात्र पंजिका तथा स्थानान्तरण प्रमाण-पत्र - कार्यालय प्रति", 9, align=1))
    story.append(Spacer(1, 2.5 * mm))

    tc = getattr(student, "transfer_certificate", None)

    top_meta = [[
        f"Admission / S.R. No.: {student.admission_no or student.legacy_sid or ''}",
        f"Withdrawal File No.: {tc.withdrawal_file_no if tc else ''}",
        f"Transfer Certificate No.: {tc.tc_number if tc else ''}",
        f"Register Book No.: {student.scholar_register_no or ''}",
    ]]
    meta_t = Table(top_meta, colWidths=scaled_widths([47.25, 47.25, 47.25, 47.25]))
    meta_t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.6),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (2, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9aa5b1")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_t)
    story.append(Spacer(1, 2 * mm))

    caste_religion = " / ".join(part for part in [student.religion, student.caste] if part) or ""
    address = student.address_permanent or student.address_local or ""

    def bilingual_label(english, hindi):
        if not hindi:
            return Paragraph(english, field_style)
        hindi_flowable = _devanagari_flowable(hindi, field_style.fontSize - 0.5)
        return [Paragraph(english, field_style), Spacer(1, 0.4 * mm), hindi_flowable]

    info_rows = [
        [bilingual_label("Name of Scholar", "छात्र का नाम"), Paragraph(student.full_name, value_style),
         bilingual_label("Nationality", "राष्ट्रीयता"), Paragraph(student.nationality or "Indian", value_style)],
        [bilingual_label("Religion / Caste", "धर्म-जाती"), Paragraph(caste_religion, value_style),
         bilingual_label("Category", "श्रेणी"), Paragraph(student.category or "", value_style)],
        [bilingual_label("Father's Name", "पिता का नाम"), Paragraph(student.father_name or "", value_style),
         bilingual_label("Mother's Name", "माता का नाम"), Paragraph(student.mother_name or "", value_style)],
        [bilingual_label("Date of Birth", "जन्मतिथि"), Paragraph(student.date_of_birth.strftime("%d-%m-%Y") if student.date_of_birth else "", value_style),
         bilingual_label("DOB in words", "शब्दों में"), Paragraph(date_to_words(student.date_of_birth), value_style)],
        [bilingual_label("Admission Date", "प्रवेश तिथि"), Paragraph(student.admission_date.strftime("%d-%m-%Y") if student.admission_date else "", value_style),
         bilingual_label("Current Class", "वर्तमान कक्षा"), Paragraph(student.current_class.name if student.current_class else "", value_style)],
        [bilingual_label("Aadhaar Number", "आधार"), Paragraph(student.aadhaar_no or "", value_style),
         bilingual_label("Last Institution", "पूर्व विद्यालय"), Paragraph(student.previous_school_name or "", value_style)],
        [bilingual_label("Parent occupation", "व्यवसाय"), Paragraph("________________", value_style),
         bilingual_label("Address", "पता"), Paragraph(address, value_style)],
    ]
    info_t = Table(info_rows, colWidths=scaled_widths([32, 62, 32, 63]))
    info_t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9aa5b1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f7f8f8")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f7f8f8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(info_t)
    story.append(Spacer(1, 3 * mm))

    tc_class_name = None
    if tc:
        tc_class_name = tc.last_class_studied.name if tc.last_class_studied else (
            student.current_class.name if student.current_class else None
        )

    grid_head_style = ParagraphStyle("SrGridHead", parent=field_style, fontSize=6.4, leading=7.4, alignment=1, fontName="Helvetica-Bold")
    group_style = ParagraphStyle("SrGroup", parent=field_style, fontSize=5.9, leading=6.6, alignment=1, fontName="Helvetica-Bold")

    def grid_heading(english, hindi=""):
        if not hindi:
            return Paragraph(english, grid_head_style)
        hindi_flowable = _devanagari_flowable(hindi, grid_head_style.fontSize - 0.3, align=1)
        return [Paragraph(english, grid_head_style), Spacer(1, 0.3 * mm), hindi_flowable]

    grid_header = [
        grid_heading("School"), grid_heading("Class", "कक्षा"), grid_heading("Admission", "प्रवेश"),
        grid_heading("Promotion", "कक्षोन्नति"), grid_heading("Removal", "निष्कासन"),
        grid_heading("Cause of Removal", "निष्कासन का कारण"), grid_heading("Year", "वर्ष"),
        grid_heading("Conduct", "आचरण"), grid_heading("Work", "कार्य"), grid_heading("Sign.", "हस्ताक्षर"),
    ]
    grid_data = [grid_header]
    for cls in _SCHOLAR_REGISTER_CLASS_ROWS:
        group = ""
        if cls == "NUR":
            group = VerticalTextFlowable("Pre-Primary", group_style.fontName, group_style.fontSize)
        elif cls == "I":
            group = VerticalTextFlowable("Primary", group_style.fontName, group_style.fontSize)
        elif cls == "VI":
            group = VerticalTextFlowable("J.H. School", group_style.fontName, group_style.fontSize)
        row = [group, cls, "", "", "", "", "", "", "", ""]
        if tc_class_name and cls.upper() == tc_class_name.strip().upper():
            removal_date = tc.struck_off_date or tc.date_of_leaving
            row[4] = removal_date.strftime("%d-%m-%Y") if removal_date else ""
            row[5] = (tc.reason_for_leaving or "")[:28]
            row[6] = tc.issue_date.strftime("%Y") if tc.issue_date else ""
            row[7] = tc.get_conduct_display()
        grid_data.append(row)

    grid_t = Table(
        grid_data,
        colWidths=scaled_widths([14, 11, 20, 20, 20, 43, 12, 18, 17, 14]),
        repeatRows=1,
    )
    grid_t.setStyle(TableStyle([
        ("SPAN", (0, 1), (0, 3)),
        ("SPAN", (0, 4), (0, 8)),
        ("SPAN", (0, 9), (0, 11)),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17202a")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.7),
    ]))
    story.append(grid_t)
    story.append(Spacer(1, 2.5 * mm))

    # Rendered as three separate single-line images (heading, then 1., then 2.)
    # - not one wrapped Paragraph - so each mixed English/Hindi sentence gets
    # correct Devanagari shaping via _devanagari_flowable, and each line stays
    # comfortably under the page width. Matches the legacy form's layout:
    # "Note / टिप्पणी :" on its own line, then the numbered instructions below.
    story.append(_devanagari_flowable("Note / टिप्पणी :", 7.5, bold=True))
    story.append(Spacer(1, 0.8 * mm))
    story.append(_devanagari_flowable("1. Classes Nursery to VIII का कार्य Work column में अंकित करें।", 7.5))
    story.append(Spacer(1, 0.8 * mm))
    story.append(_devanagari_flowable("2. प्रत्येक entry को Admission Form एवं school record से सत्यापित करें।", 7.5))
    story.append(Spacer(1, 3 * mm))

    cert_style = ParagraphStyle("CertText", parent=field_style, fontSize=8.2, leading=10)
    cert_t = Table(
        [
            [Paragraph("I - Certified that the entries as records details of the student have been daily checked from the admission form and that they are complete.", cert_style)],
            ["Head of Institute: ______________________"],
            [Paragraph("II - Certified that the above student's Register has been posted up to the last of the student's leaving as required by the Department Rules & T.C. Issued.", cert_style)],
            ["Prepared by: ______________________          Date: ____________          Head of Institute: ______________________"],
        ],
        colWidths=[content_width_mm * mm],
    )
    cert_t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("ALIGN", (0, 1), (0, 1), "RIGHT"),
        ("ALIGN", (0, 3), (0, 3), "RIGHT"),
    ]))
    story.append(cert_t)

    return story


def _draw_scholar_register_border(canvas, doc):
    """Thin outer black border, drawn just inside the page edge on every
    page of the document - matches the traditional bound-ledger look of the
    physical Scholar's Register (see the reference photos in
    CODEX-HANDOFF.md). Applied to the individual page, the full book, and
    the index so the whole document family looks consistent."""
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#17202a"))
    canvas.setLineWidth(0.9)
    margin = 5 * mm
    page_width, page_height = A4
    canvas.rect(margin, margin, page_width - 2 * margin, page_height - 2 * margin)
    canvas.restoreState()


def _draw_bound_register_border(canvas, doc):
    """Border for pages that will be sewn/stapled into a physical book.

    The left edge stays well clear of the binding gutter so neither the
    border nor printed fields disappear when a thick register is opened.
    """
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#17202a"))
    canvas.setLineWidth(0.9)
    left = 18 * mm
    right = 5 * mm
    vertical = 5 * mm
    page_width, page_height = A4
    canvas.rect(left, vertical, page_width - left - right, page_height - 2 * vertical)
    canvas.restoreState()


def build_scholar_register_pdf(student, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=9 * mm,
        bottomMargin=9 * mm,
        title=f"Scholar Register - {student.full_name}",
    )
    story = _scholar_register_page_flowables(student, school_profile)
    document.build(story, onFirstPage=_draw_scholar_register_border, onLaterPages=_draw_scholar_register_border)
    buffer.seek(0)
    return buffer.getvalue()


def _scholar_register_cover_flowables(book_no, from_no, to_no, entries, school_profile=None):
    """First page of the full physical register book print: school identity,
    book number, admission-number range, and a coverage summary line, plus
    signature lines for whoever prepares/verifies the book."""
    styles = getSampleStyleSheet()
    story = []
    brand_color = colors.HexColor("#0f766e")

    title_style = ParagraphStyle(
        "SrCoverTitle", parent=styles["Title"], fontSize=20, leading=24, alignment=1,
        textColor=brand_color, fontName="Helvetica-Bold", spaceAfter=2 * mm,
    )
    subtitle_style = ParagraphStyle("SrCoverSubtitle", parent=styles["Normal"], fontSize=12, leading=16, alignment=1, fontName="Helvetica-Bold")
    small_style = ParagraphStyle("SrCoverSmall", parent=styles["Normal"], fontSize=9.5, leading=13, alignment=1)
    cert_style = ParagraphStyle("SrCoverCert", parent=styles["Normal"], fontSize=10, leading=20)

    school_name = school_profile.name if school_profile else "SCHOOLSOFT"
    logo_path = os.path.join(settings.BASE_DIR, "static", "core", "school_logo.png")

    story.append(Spacer(1, 28 * mm))
    if os.path.exists(logo_path):
        logo = Image(logo_path, 28 * mm, 28 * mm)
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(school_name.upper(), title_style))
    if school_profile and school_profile.address_line1:
        addr = f"{school_profile.address_line1}, {school_profile.address_line2}".strip(", ")
        story.append(Paragraph(addr, small_style))
    identity_parts = []
    if school_profile and school_profile.udise_code:
        identity_parts.append(f"UDISE: {school_profile.udise_code}")
    if school_profile and school_profile.recognition_no:
        identity_parts.append(f"Recognition: {school_profile.recognition_no}")
    if identity_parts:
        story.append(Paragraph(" | ".join(identity_parts), small_style))

    story.append(Spacer(1, 14 * mm))
    story.append(Paragraph("SCHOLAR'S REGISTER", title_style))
    book_label = f"Book No. {book_no}" if book_no else "Custom Range"
    story.append(Paragraph(book_label, subtitle_style))
    story.append(Paragraph(f"Admission / Register Numbers {from_no} to {to_no}", small_style))

    story.append(Spacer(1, 8 * mm))
    present_count = sum(1 for _sid, student in entries if student is not None)
    story.append(Paragraph(
        f"{present_count} of {len(entries)} numbers in this range have student records on file. "
        f"Individual pages appear for those {present_count}; numbers with no record are listed as "
        f"'Not Allotted' in the index and have no page in this book.",
        small_style,
    ))

    story.append(Spacer(1, 24 * mm))
    story.append(Paragraph("Prepared by: ______________________          Date: ____________", cert_style))
    story.append(Paragraph("Verified by (Head of Institute): ______________________          Date: ____________", cert_style))

    return story


def _scholar_register_index_flowables(
    entries, book_no, from_no, to_no, school_profile=None, standalone=False, content_width_mm=189
):
    """Index table: one row per number in the range, whether or not a
    student record exists for it. standalone=True adds a school header on
    top (used by build_scholar_register_index_pdf, which has no cover page
    before it)."""
    styles = getSampleStyleSheet()
    story = []
    brand_color = colors.HexColor("#0f766e")
    width_scale = content_width_mm / 189

    title_style = ParagraphStyle(
        "SrIndexTitle", parent=styles["Title"], fontSize=13, leading=15, alignment=1,
        textColor=brand_color, fontName="Helvetica-Bold", spaceAfter=1 * mm,
    )
    subtitle_style = ParagraphStyle("SrIndexSubtitle", parent=styles["Normal"], fontSize=8, leading=9, alignment=1)
    small_style = ParagraphStyle("SrIndexSmall", parent=styles["Normal"], fontSize=8, leading=10, alignment=1)
    cell_style = ParagraphStyle("SrIndexCell", parent=styles["Normal"], fontSize=6.3, leading=6.9)
    address_style = ParagraphStyle("SrIndexAddress", parent=cell_style, fontSize=5.8, leading=6.4)

    if standalone:
        school_name = school_profile.name if school_profile else "SCHOOLSOFT"
        logo_path = os.path.join(settings.BASE_DIR, "static", "core", "school_logo.png")
        school_heading = [Paragraph(school_name.upper(), title_style)]
        if school_profile and school_profile.address_line1:
            addr = f"{school_profile.address_line1}, {school_profile.address_line2}".strip(", ")
            school_heading.append(Paragraph(addr, small_style))
        logo = Image(logo_path, 20 * mm, 20 * mm) if os.path.exists(logo_path) else ""
        header = Table(
            [[logo, school_heading, ""]],
            colWidths=[25 * width_scale * mm, 139 * width_scale * mm, 25 * width_scale * mm],
        )
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "CENTER")]))
        story.append(header)
        story.append(Table([[""]], colWidths=[content_width_mm * mm], rowHeights=[1 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#b58a2a"))])))
        story.append(Spacer(1, 3 * mm))

    book_label = f"Book No. {book_no}" if book_no else "Custom Range"
    story.append(Paragraph("SCHOLAR'S REGISTER - INDEX", title_style))
    story.append(Paragraph(f"{book_label}  |  Numbers {from_no} to {to_no}", subtitle_style))
    story.append(Spacer(1, 2.5 * mm))

    header_row = ["S.No", "SR. No.", "Student Name", "Father Name", "Address"]
    table_data = [header_row]
    for index, (sid, student) in enumerate(entries, start=1):
        if student is None:
            table_data.append([str(index), str(sid), "Not Allotted", "", ""])
            continue
        address = student.address_permanent or student.address_local or ""
        table_data.append([
            str(index),
            str(sid),
            Paragraph(student.full_name, cell_style),
            Paragraph(student.father_name or "", cell_style),
            Paragraph(address, address_style),
        ])

    index_t = Table(
        table_data,
        colWidths=[width * width_scale * mm for width in [12, 18, 52, 45, 53]],
        repeatRows=1,
    )
    index_t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9aa4b2")),
        ("BACKGROUND", (0, 0), (-1, 0), brand_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.3),
        ("ALIGN", (0, 0), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.6),
    ]))
    story.append(index_t)

    return story


def build_scholar_register_book_pdf(entries, book_no, from_no, to_no, school_profile=None):
    """Full physical register book: cover page, index (all numbers in range,
    including 'Not Allotted' ones), then one individual Scholar Register page
    per number that actually has a student record. Missing numbers get no
    page - only an index row - per the owner's explicit decision (see
    CODEX-HANDOFF.md, "Full Scholar Register Book" checkpoint)."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=8 * mm,
        leftMargin=22 * mm,
        topMargin=9 * mm,
        bottomMargin=9 * mm,
        title=f"Scholar Register Book {book_no or f'{from_no}-{to_no}'}",
    )
    story = []
    story.extend(_scholar_register_cover_flowables(book_no, from_no, to_no, entries, school_profile))
    story.append(PageBreak())
    story.extend(
        _scholar_register_index_flowables(
            entries, book_no, from_no, to_no, school_profile, standalone=False, content_width_mm=180
        )
    )

    for _sid, student in entries:
        if student is None:
            continue
        story.append(PageBreak())
        story.extend(_scholar_register_page_flowables(student, school_profile, content_width_mm=180))

    document.build(story, onFirstPage=_draw_bound_register_border, onLaterPages=_draw_bound_register_border)
    buffer.seek(0)
    return buffer.getvalue()


def build_scholar_register_index_pdf(entries, book_no, from_no, to_no, school_profile=None):
    """'Index Only' print action: just the index table (with the school
    header on top), no cover page and no individual student pages."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=8 * mm,
        leftMargin=22 * mm,
        topMargin=9 * mm,
        bottomMargin=9 * mm,
        title=f"Scholar Register Index {book_no or f'{from_no}-{to_no}'}",
    )
    story = _scholar_register_index_flowables(
        entries, book_no, from_no, to_no, school_profile, standalone=True, content_width_mm=180
    )
    document.build(story, onFirstPage=_draw_bound_register_border, onLaterPages=_draw_bound_register_border)
    buffer.seek(0)
    return buffer.getvalue()


def build_discipline_summary_pdf(student, records, school_profile=None):
    """Admin/Principal-only PTM handout: full discipline history for one student."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Discipline Record - {student.full_name}",
    )
    styles = getSampleStyleSheet()
    story = []
    _school_header(story, school_profile, "DISCIPLINE RECORD SUMMARY", styles)

    small_style = ParagraphStyle("DiscSmall", parent=styles["Normal"], fontSize=9, leading=13)
    cell_style = ParagraphStyle("DiscCell", parent=styles["Normal"], fontSize=8.5, leading=11)

    class_label = student.current_class.name if student.current_class else ""
    if student.current_section:
        class_label = f"{class_label}-{student.current_section.name}" if class_label else student.current_section.name

    info_rows = [
        ["Student Name", student.full_name, "Class", class_label],
        ["Father's Name", student.father_name or "", "Admission No.", student.admission_no or ""],
    ]
    info_table = Table(info_rows, colWidths=[32 * mm, 58 * mm, 32 * mm, 58 * mm])
    info_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f1f5f9")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 5 * mm))

    if not records:
        story.append(Paragraph("No discipline records on file for this student.", small_style))
    else:
        severity_counts = {"minor": 0, "major": 0, "severe": 0}
        for r in records:
            severity_counts[r.severity] = severity_counts.get(r.severity, 0) + 1
        summary = f"Total incidents: {len(records)}  |  Minor: {severity_counts.get('minor', 0)}  |  Major: {severity_counts.get('major', 0)}  |  Severe: {severity_counts.get('severe', 0)}"
        story.append(Paragraph(summary, small_style))
        story.append(Spacer(1, 3 * mm))

        header = ["Date", "Category", "Severity", "Description", "Action Taken", "Parent Notified"]
        table_data = [header]
        for r in records:
            table_data.append([
                Paragraph(r.incident_date.strftime("%d-%m-%Y"), cell_style),
                Paragraph(r.get_category_display(), cell_style),
                Paragraph(r.get_severity_display(), cell_style),
                Paragraph(r.description or "", cell_style),
                Paragraph(r.action_taken or "", cell_style),
                Paragraph("Yes" if r.parent_notified else "No", cell_style),
            ])
        records_table = Table(
            table_data,
            colWidths=[20 * mm, 26 * mm, 18 * mm, 50 * mm, 46 * mm, 22 * mm],
            repeatRows=1,
        )
        records_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(records_table)

    story.append(Spacer(1, 12 * mm))
    sig_data = [["Class Teacher", "Principal (Seal)"]]
    sig_t = Table(sig_data, colWidths=[90 * mm, 90 * mm])
    sig_t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(sig_t)

    document.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ---- premium palette (official certificates: report card + character cert) ----
_C_INK = colors.HexColor("#1e293b")
_C_BRAND = colors.HexColor("#0f766e")
_C_BRAND_DK = colors.HexColor("#0b4f4a")
_C_GOLD = colors.HexColor("#b45309")
_C_SOFT = colors.HexColor("#f1f5f9")
_C_SOFT2 = colors.HexColor("#f8fafc")
_C_LINE = colors.HexColor("#cbd5e1")
_C_MUTED = colors.HexColor("#64748b")

CBSE_GRADE_SCALE = [
    ("A1", "91-100"), ("A2", "81-90"), ("B1", "71-80"), ("B2", "61-70"),
    ("C1", "51-60"), ("C2", "41-50"), ("D", "33-40"), ("E", "Below 33"),
]


def _division(pct):
    pct = float(pct)
    if pct >= 60:
        return "First Division"
    if pct >= 45:
        return "Second Division"
    if pct >= 33:
        return "Third Division"
    return "—"


def _overall_grade(pct):
    pct = float(pct)
    for grade, low in (("A1", 91), ("A2", 81), ("B1", 71), ("B2", 61),
                       ("C1", 51), ("C2", 41), ("D", 33)):
        if pct >= low:
            return grade
    return "E"


def _class_section_label(student):
    label = student.current_class.name if student.current_class else ""
    if student.current_section:
        label = f"{label} - {student.current_section.name}" if label else student.current_section.name
    return label


def _has_devanagari():
    return "NotoSansDevanagari-Bold" in pdfmetrics.getRegisteredFontNames()


def _premium_header(story, school_profile, title_en, styles, title_hi=None, subtitle=None):
    """Shared official letterhead for report card + character certificate.

    Logo (if present) + school identity + double rule + coloured title band.
    Does NOT touch the older _school_header used by receipts/TC/etc.
    """
    school_name = (school_profile.name if school_profile else "SchoolSoft").upper()
    # Times-Bold (built-in Base-14, no external/internet font) matches the
    # official-serif treatment used on the Transfer Certificate and Scholar
    # Register headers, so the whole document family reads as one identity.
    name_st = ParagraphStyle("PhName", fontSize=19, leading=22, alignment=1,
                             textColor=_C_BRAND_DK, fontName="Times-Bold", spaceAfter=1)
    addr_st = ParagraphStyle("PhAddr", fontSize=8.5, leading=11, alignment=1, textColor=_C_INK)
    muted_st = ParagraphStyle("PhMuted", fontSize=8, leading=10, alignment=1, textColor=_C_MUTED)

    center = [Paragraph(school_name, name_st)]
    if school_profile:
        addr = getattr(school_profile, "address", "") or ""
        if addr:
            center.append(Paragraph(addr, addr_st))
        contact = []
        if school_profile.phone:
            contact.append(f"Phone: {school_profile.phone}")
        if school_profile.email:
            contact.append(f"Email: {school_profile.email}")
        if contact:
            center.append(Paragraph(" &nbsp;|&nbsp; ".join(contact), addr_st))
        if getattr(school_profile, "udise_code", ""):
            center.append(Paragraph(f"UDISE Code: {school_profile.udise_code}", muted_st))

    logo_path = os.path.join(settings.BASE_DIR, "static", "core", "school_logo.png")
    if os.path.exists(logo_path):
        head = Table([[Image(logo_path, width=20 * mm, height=20 * mm), center, ""]],
                     colWidths=[24 * mm, 132 * mm, 24 * mm])
        head.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
    else:
        head = Table([[center]], colWidths=[180 * mm])
        head.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(head)
    story.append(Spacer(1, 3 * mm))

    rule = Table([[""]], colWidths=[180 * mm], rowHeights=[2])
    rule.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 2.2, _C_BRAND),
                              ("LINEBELOW", (0, 0), (-1, 0), 0.8, _C_GOLD)]))
    story.append(rule)
    story.append(Spacer(1, 4 * mm))

    use_hi = title_hi and _has_devanagari()
    if use_hi:
        # ReportLab does not shape Devanagari (no matra reordering, no
        # conjunct ligatures) - a raw Paragraph in a Devanagari font renders
        # garbled text (e.g. "चरित्र" comes out as "चरत्रि"). Route through
        # the HarfBuzz+FreeType pipeline instead, in white to match the band.
        hi_flowable = _devanagari_flowable(title_hi, 13, bold=True, align=1, color=(255, 255, 255, 255))
        t_en = ParagraphStyle("PhTiEn", fontName="Helvetica-Bold", fontSize=13,
                              leading=15, alignment=1, textColor=colors.white)
        band = Table([[hi_flowable], [Paragraph(title_en, t_en)]], colWidths=[180 * mm])
    else:
        t_en = ParagraphStyle("PhTiEn2", fontName="Helvetica-Bold", fontSize=13.5,
                              leading=16, alignment=1, textColor=colors.white)
        band = Table([[Paragraph(title_en, t_en)]], colWidths=[180 * mm])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _C_BRAND),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROUNDEDCORNERS", [3, 3, 3, 3]),
    ]))
    story.append(band)
    if subtitle:
        story.append(Paragraph(subtitle, ParagraphStyle("PhSub", fontSize=9.5, leading=12,
                                                        alignment=1, textColor=_C_MUTED, spaceBefore=3)))
    story.append(Spacer(1, 5 * mm))


def build_character_certificate_pdf(student, school_profile=None):
    """World-class redesign (owner review, July 2026): the old VB SchoolSoft
    layout looked dated (cursive title, dev-tool watermark), and the first
    Django version - while cleaner - left ~40% of the page blank below the
    body text and buried the actual character rating inside a paragraph.
    This version fills the page with genuinely useful structure (bordered
    meta strip, a scannable Character & Conduct badge, a real seal box,
    a verification footer) instead of one big empty spacer, and adds the
    same thin outer border used on the TC/Scholar Register so the whole
    document family reads as one consistent official identity."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=13 * mm,
        bottomMargin=14 * mm,
        title=f"Character Certificate - {student.full_name}",
    )
    styles = getSampleStyleSheet()
    story = []
    _premium_header(story, school_profile, "CHARACTER CERTIFICATE", styles,
                    title_hi="चरित्र प्रमाण-पत्र")

    # gender-aware pronouns
    if getattr(student, "gender", "") == "F":
        subj, poss, obj, rel = "she", "her", "her", "daughter"
    else:
        subj, poss, obj, rel = "he", "his", "him", "son"

    # Character Certificate deliberately shows only the class, not the
    # section - section is an internal administrative grouping (which room/
    # group), irrelevant to what this certificate is attesting (bona fide
    # status and good conduct). _class_section_label (which includes the
    # section) stays reserved for documents like the Marksheet where the
    # exact section is administratively meaningful.
    class_label = student.current_class.name if student.current_class else ""
    parents = []
    if student.father_name:
        parents.append(f"{rel} of <b>Mr. {student.father_name}</b>")
    if student.mother_name:
        parents.append(f"and <b>Mrs. {student.mother_name}</b>" if parents else f"child of <b>Mrs. {student.mother_name}</b>")
    parent_bit = (" " + " ".join(parents)) if parents else ""
    session_bit = ""
    try:
        session_bit = student.fee_receipts.first().session.name  # best-effort; harmless if none
    except Exception:
        session_bit = ""

    ref_no = f"CC-{timezone.localdate().year}-{student.admission_no or student.legacy_sid or student.pk}"
    meta_cell = ParagraphStyle("CcMetaCell", fontSize=9, textColor=_C_INK)
    meta_cell_c = ParagraphStyle("CcMetaCellC", parent=meta_cell, alignment=1)
    meta_cell_r = ParagraphStyle("CcMetaCellR", parent=meta_cell, alignment=2)
    mrow = Table([[
        Paragraph(f"<b>Ref. No.:</b> {ref_no}", meta_cell),
        Paragraph(f"<b>Session:</b> {session_bit or '-'}", meta_cell_c),
        Paragraph(f"<b>Date:</b> {timezone_today()}", meta_cell_r),
    ]], colWidths=[58 * mm, 58 * mm, 58 * mm])
    mrow.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, _C_LINE),
        ("BACKGROUND", (0, 0), (-1, -1), _C_SOFT2),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(mrow)
    story.append(Spacer(1, 5 * mm))

    # A distinct, scannable rating badge - the single fact most readers of a
    # character certificate look for first, previously buried mid-paragraph.
    badge_label = ParagraphStyle("CcBadgeLabel", fontSize=8.5, textColor=_C_MUTED,
                                 fontName="Helvetica-Bold", leading=10)
    badge_value = ParagraphStyle("CcBadgeValue", fontSize=14, textColor=_C_BRAND_DK,
                                 fontName="Helvetica-Bold", alignment=2)
    badge = Table([[Paragraph("CHARACTER &amp; CONDUCT", badge_label), Paragraph("GOOD", badge_value)]],
                 colWidths=[110 * mm, 64 * mm])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _C_SOFT2),
        ("BOX", (0, 0), (-1, -1), 0.9, _C_GOLD),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(badge)
    story.append(Spacer(1, 7 * mm))

    body = ParagraphStyle("CcBody", parent=styles["Normal"], fontSize=11.5, leading=20,
                          alignment=4, textColor=_C_INK, firstLineIndent=10 * mm, spaceAfter=5.5 * mm)

    story.append(Paragraph(
        f"This is to certify that <b>{student.full_name}</b>{parent_bit}, bearing Admission No. "
        f"<b>{student.admission_no or '-'}</b>, has been a bona fide student of this institution"
        + (f", studying in Class <b>{class_label}</b>" if class_label else "") + ".", body))
    story.append(Paragraph(
        f"To the best of my knowledge, {poss} character and conduct throughout {poss} stay in this "
        f"school have been found to be <b>good</b>, and there is nothing adverse recorded against "
        f"{obj}. {subj.capitalize()} bears a good moral character.", body))
    story.append(Paragraph(
        f"I wish {obj} every success in all {poss} future endeavours.", body))

    story.append(Spacer(1, 15 * mm))

    seal_caption = ParagraphStyle("CcSealCaption", fontSize=7.8, alignment=1, textColor=_C_MUTED)
    seal_box = Table([[""]], colWidths=[30 * mm], rowHeights=[26 * mm])
    seal_box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, _C_LINE)]))

    sign_line = Table([["Principal / Headmaster"]], colWidths=[75 * mm])
    sign_line.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (0, 0), 0.6, _C_INK),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 10), ("TEXTCOLOR", (0, 0), (-1, -1), _C_INK),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))

    sign_row = Table(
        [[[seal_box, Spacer(1, 1.5 * mm), Paragraph("Office Seal", seal_caption)], "", sign_line]],
        colWidths=[40 * mm, 59 * mm, 75 * mm],
    )
    sign_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
    ]))
    story.append(sign_row)
    story.append(Spacer(1, 6 * mm))

    footer_school = (school_profile.name if school_profile else "the school").upper()
    story.append(Paragraph(
        f"This is a computer-generated certificate issued from the official Scholar's Register of "
        f"{footer_school}. For verification, please contact the school office.",
        ParagraphStyle("CcFooterNote", fontSize=7.5, leading=10, alignment=1, textColor=_C_MUTED)
    ))

    # Thin outer border - same treatment as the TC/Scholar Register - gives
    # the whole official-document family one consistent bordered identity.
    document.build(story, onFirstPage=_draw_scholar_register_border, onLaterPages=_draw_scholar_register_border)
    buffer.seek(0)
    return buffer.getvalue()


def timezone_today():
    return timezone.localdate().strftime("%d-%m-%Y")


def build_marksheet_pdf(student, term, exam_marks, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Marksheet - {student.full_name} - {term}",
    )
    styles = getSampleStyleSheet()
    story = []
    _premium_header(story, school_profile, "PROGRESS REPORT CARD", styles,
                    subtitle=f"{term.name} &nbsp;&bull;&nbsp; Session {term.session.name}")

    class_label = _class_section_label(student)
    dob = student.date_of_birth.strftime("%d-%m-%Y") if student.date_of_birth else "—"

    def _kv(label, value):
        safe = value if (value not in (None, "")) else "&nbsp;"
        return Paragraph(f'<font color="#64748b" size=8>{label}</font><br/><b>{safe}</b>',
                         ParagraphStyle("RcKv", fontSize=10, leading=13, textColor=_C_INK))

    info = [
        [_kv("STUDENT NAME", student.full_name), _kv("CLASS &amp; SECTION", class_label),
         _kv("ROLL NO.", student.roll_no)],
        [_kv("FATHER'S NAME", student.father_name), _kv("MOTHER'S NAME", student.mother_name),
         _kv("DATE OF BIRTH", dob)],
        [_kv("ADMISSION NO.", student.admission_no), _kv("SID", student.legacy_sid),
         _kv("SESSION", term.session.name)],
    ]
    info_table = Table(info, colWidths=[70 * mm, 55 * mm, 45 * mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _C_SOFT2),
        ("BOX", (0, 0), (-1, -1), 0.6, _C_LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.extend([info_table, Spacer(1, 5 * mm)])

    hdr = ParagraphStyle("RcHdr", fontName="Helvetica-Bold", fontSize=9.5,
                         textColor=colors.white, alignment=1)
    cell_l = ParagraphStyle("RcCellL", fontSize=9.5, textColor=_C_INK)
    cell_c = ParagraphStyle("RcCellC", fontSize=9.5, textColor=_C_INK, alignment=1)
    rows = [[Paragraph("SUBJECT", ParagraphStyle("RcHdrL", parent=hdr, alignment=0)),
             Paragraph("MAX", hdr), Paragraph("OBTAINED", hdr), Paragraph("GRADE", hdr)]]
    total_max = Decimal("0.00")
    total_obtained = Decimal("0.00")
    for mark in exam_marks:
        obtained_label = "AB" if mark.is_absent else money(mark.marks_obtained or Decimal("0.00"))
        rows.append([
            Paragraph(mark.exam_test.subject.name, cell_l),
            Paragraph(money(mark.exam_test.max_marks), cell_c),
            Paragraph(obtained_label, cell_c),
            Paragraph(mark.grade or "—", cell_c),
        ])
        total_max += mark.exam_test.max_marks
        if not mark.is_absent and mark.marks_obtained is not None:
            total_obtained += mark.marks_obtained

    overall_pct = (total_obtained / total_max * Decimal("100")) if total_max else Decimal("0.00")
    rows.append([
        Paragraph("TOTAL", ParagraphStyle("RcTotL", parent=cell_l, fontName="Helvetica-Bold")),
        Paragraph(money(total_max), ParagraphStyle("RcTotC1", parent=cell_c, fontName="Helvetica-Bold")),
        Paragraph(money(total_obtained), ParagraphStyle("RcTotC2", parent=cell_c, fontName="Helvetica-Bold")),
        Paragraph(f"{overall_pct:.1f}%", ParagraphStyle("RcTotC3", parent=cell_c, fontName="Helvetica-Bold")),
    ])
    marks_table = Table(rows, colWidths=[78 * mm, 30 * mm, 35 * mm, 27 * mm], repeatRows=1)
    n = len(rows)
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), _C_BRAND),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, -1), 9),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, _C_LINE),
        ("BACKGROUND", (0, n - 1), (-1, n - 1), colors.HexColor("#e7f5f3")),
        ("LINEABOVE", (0, n - 1), (-1, n - 1), 1.0, _C_BRAND),
        ("BOX", (0, 0), (-1, -1), 0.6, _C_LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for r in range(1, n - 1):
        if r % 2 == 0:
            ts.append(("BACKGROUND", (0, r), (-1, r), _C_SOFT2))
    marks_table.setStyle(TableStyle(ts))
    story.extend([marks_table, Spacer(1, 5 * mm)])

    # result strip (flat 2-row table: labels then values)
    is_pass = float(overall_pct) >= 33
    result_word = "PASS" if is_pass else "FAIL"
    result_color = colors.HexColor("#15803d") if is_pass else colors.HexColor("#b91c1c")
    strip = Table([
        ["PERCENTAGE", "GRADE", "DIVISION", "RESULT"],
        [f"{overall_pct:.1f}%", _overall_grade(overall_pct), _division(overall_pct), result_word],
    ], colWidths=[45 * mm] * 4)
    strip.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _C_SOFT),
        ("BOX", (0, 0), (-1, -1), 0.6, _C_LINE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, 0), 8), ("TEXTCOLOR", (0, 0), (-1, 0), _C_MUTED),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"), ("FONTSIZE", (0, 1), (-1, 1), 11.5),
        ("TEXTCOLOR", (0, 1), (-1, 1), _C_BRAND_DK),
        ("TEXTCOLOR", (3, 1), (3, 1), result_color),
        ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 1), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
    ]))
    story.extend([strip, Spacer(1, 5 * mm)])

    # grading scale legend
    legend_cells = [Paragraph(f"<b>{g}</b> &nbsp;{r}",
                              ParagraphStyle("RcLg", fontSize=8, textColor=_C_INK))
                    for g, r in CBSE_GRADE_SCALE]
    legend = Table([[Paragraph("<b>Grading Scale</b>",
                               ParagraphStyle("RcLt", fontSize=8.5, textColor=_C_BRAND_DK))] + legend_cells],
                   colWidths=[26 * mm] + [19.25 * mm] * 8)
    legend.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _C_SOFT2),
        ("BOX", (0, 0), (-1, -1), 0.5, _C_LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (0, 0), 7),
    ]))
    story.extend([legend, Spacer(1, 16 * mm)])

    sign = Table([["Class Teacher", "Examination Incharge", "Principal"]], colWidths=[60 * mm] * 3)
    sign.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, _C_INK),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (-1, -1), _C_INK),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sign)

    document.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def build_collection_report_pdf(rows, totals, date_from_str, date_to_str, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="Collection Report",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=15,
        leading=18,
        alignment=1,
        spaceAfter=1 * mm,
    )
    small_style = ParagraphStyle(
        "ReportSmall",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=1,
        spaceAfter=5 * mm,
    )

    story = []

    school_name = school_profile.name if school_profile else "SchoolSoft Collection Report"
    story.append(Paragraph(school_name, title_style))
    subtitle = f"Collection from {date_from_str} to {date_to_str}"
    story.append(Paragraph(subtitle, small_style))

    table_data = [
        ["Date", "Receipt", "SID", "Name", "Class", "Mode", "Net", "Received"]
    ]

    for row in rows:
        table_data.append([
            row.receipt_date.strftime("%d-%m-%Y"),
            row.receipt_no,
            str(row.student.legacy_sid),
            row.display_student_name[:20],
            row.display_class_section,
            row.get_payment_mode_display(),
            str(row.legacy_net_total),
            str(row.received_amount),
        ])

    table_data.append([
        "Total", "", "", "", "", "",
        str(totals.get('total_legacy_net') or 0),
        str(totals.get('total_received') or 0)
    ])

    col_widths = [20*mm, 25*mm, 15*mm, 45*mm, 18*mm, 15*mm, 22*mm, 22*mm]
    
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("ALIGN", (6, 0), (7, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e5e7eb")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
    ]))

    story.append(t)
    document.build(story)
    return buffer.getvalue()


def build_salary_payslip_pdf(payment, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Salary Slip - {payment.slip_no}",
    )
    styles = getSampleStyleSheet()
    story = []
    _school_header(story, school_profile, f"SALARY SLIP - {payment.pay_month.strftime('%B %Y').upper()}", styles)

    staff = payment.staff
    meta_rows = [
        ["Slip No.", payment.slip_no, "Payment Date", payment.payment_date.strftime("%d-%m-%Y")],
        ["Staff Name", staff.full_name, "Code", staff.legacy_emp_code or ""],
        ["Designation", staff.designation or "-", "Payment Mode", payment.get_payment_mode_display()],
    ]
    meta_table = Table(meta_rows, colWidths=[35 * mm, 60 * mm, 30 * mm, 55 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f1f5f9")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([meta_table, Spacer(1, 6 * mm)])

    earnings_rows = [
        ["Earnings", "Amount", "Deductions", "Amount"],
        ["Basic Pay", money(payment.basic_pay), "PF", money(payment.pf_deduction)],
        ["DA", money(payment.da), "ESI", money(payment.esi_deduction)],
        ["Other Allowances", money(payment.other_allowances), "Other Deduction", money(payment.other_deduction)],
        ["", "", "Advance Recovery", money(payment.advance_recovery)],
        ["Gross Pay", money(payment.gross_pay), "Total Deductions", money(payment.total_deductions + payment.advance_recovery)],
    ]
    pay_table = Table(earnings_rows, colWidths=[45 * mm, 35 * mm, 45 * mm, 35 * mm], repeatRows=1)
    last_row = len(earnings_rows) - 1
    pay_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8d0dc")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, last_row), (-1, last_row), "Helvetica-Bold"),
                ("BACKGROUND", (0, last_row), (-1, last_row), colors.HexColor("#f8fafc")),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([pay_table, Spacer(1, 6 * mm)])

    net_pay_table = Table(
        [["Net Pay", money(payment.net_pay)]],
        colWidths=[125 * mm, 35 * mm],
        style=TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        ),
    )
    story.append(net_pay_table)

    if payment.remarks:
        body_style = ParagraphStyle("SalaryRemarks", parent=styles["Normal"], fontSize=9, leading=13, spaceBefore=4 * mm)
        story.append(Paragraph(f"Remarks: {payment.remarks}", body_style))

    story.extend(
        [
            Spacer(1, 20 * mm),
            Table(
                [["Accountant", "Principal"]],
                colWidths=[80 * mm, 80 * mm],
                style=TableStyle(
                    [
                        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ]
                ),
            ),
        ]
    )

    def draw_watermark(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 60)
        canvas.translate(A4[0] / 2, A4[1] / 2)
        canvas.rotate(45)
        if payment.is_cancelled:
            canvas.setFillColorRGB(0.9, 0.2, 0.2, alpha=0.15)
            canvas.drawCentredString(0, 0, "CANCELLED")
        elif payment.is_edited:
            canvas.setFillColorRGB(0.9, 0.6, 0.1, alpha=0.15)
            canvas.drawCentredString(0, 0, "EDITED")
        canvas.restoreState()

        if payment.is_cancelled or payment.is_edited:
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColorRGB(0.4, 0.4, 0.4)
            if payment.is_cancelled:
                msg = f"Cancelled on {payment.cancelled_at.strftime('%d/%m/%Y')} | Reason: {payment.cancel_reason}"
            else:
                msg = f"Edited on {payment.edited_at.strftime('%d/%m/%Y')} | Reason: {payment.edit_reason}"
            canvas.drawString(18 * mm, 10 * mm, msg)
            canvas.restoreState()

    document.build(story, onFirstPage=draw_watermark, onLaterPages=draw_watermark)
    buffer.seek(0)
    return buffer.getvalue()


def build_voucher_pdf(voucher, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=f"Voucher {voucher.voucher_no}",
    )

    styles = getSampleStyleSheet()
    story = []

    _school_header(story, school_profile, "PAYMENT VOUCHER" if voucher.voucher_type == "CPMT" else "RECEIPT VOUCHER", styles)
    
    # Voucher Meta
    story.append(Spacer(1, 4 * mm))
    meta_data = [
        [f"Voucher No: {voucher.voucher_no}", f"Date: {voucher.voucher_date.strftime('%d/%m/%Y')}"],
        [f"Mode: {voucher.get_payment_mode_display()}", f"Type: {voucher.get_voucher_type_display()}"],
    ]
    if voucher.physical_slip_no:
        meta_data.append([f"Physical Slip: {voucher.physical_slip_no}", ""])

    story.append(
        Table(
            meta_data,
            colWidths=[90 * mm, 90 * mm],
            style=TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ]
            ),
        )
    )
    story.append(Spacer(1, 4 * mm))

    # Main details
    party_label = "Paid To" if voucher.voucher_type == "CPMT" else "Received From"
    party_name = voucher.staff.full_name if voucher.staff else voucher.paid_to_or_received_from
    
    details_data = [
        [f"{party_label}:", party_name or "-"],
        ["Debit Head:", voucher.debit_account.name],
        ["Credit Head:", voucher.credit_account.name],
        ["Amount:", f"Rs. {money(voucher.amount)}"],
        ["Narration:", voucher.narration or "-"],
    ]
    
    story.append(
        Table(
            details_data,
            colWidths=[40 * mm, 140 * mm],
            style=TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            ),
        )
    )
    
    story.append(Spacer(1, 20 * mm))

    # Signatures
    story.append(
        Table(
            [["Prepared By", "Approved By"]],
            colWidths=[90 * mm, 90 * mm],
            style=TableStyle(
                [
                    ("LINEABOVE", (0, 0), (0, 0), 0.5, colors.black),
                    ("LINEABOVE", (1, 0), (1, 0), 0.5, colors.black),
                    ("ALIGN", (0, 0), (0, 0), "CENTER"),
                    ("ALIGN", (1, 0), (1, 0), "CENTER"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                ]
            ),
        )
    )
    
    # Watermarks for Cancelled/Edited
    def draw_watermark(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 60)
        canvas.translate(A4[0] / 2, A4[1] / 2)
        canvas.rotate(45)
        if voucher.is_cancelled:
            canvas.setFillColorRGB(0.9, 0.2, 0.2, alpha=0.15)
            canvas.drawCentredString(0, 0, "CANCELLED")
        elif voucher.is_edited:
            canvas.setFillColorRGB(0.9, 0.6, 0.1, alpha=0.15)
            canvas.drawCentredString(0, 0, "EDITED")
        canvas.restoreState()

        # Add edit/cancel details at the bottom
        if voucher.is_cancelled or voucher.is_edited:
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColorRGB(0.4, 0.4, 0.4)
            if voucher.is_cancelled:
                msg = f"Cancelled on {voucher.cancelled_at.strftime('%d/%m/%Y')} | Reason: {voucher.cancel_reason}"
            else:
                msg = f"Edited on {voucher.edited_at.strftime('%d/%m/%Y')} | Reason: {voucher.edit_reason}"
            canvas.drawString(14 * mm, 10 * mm, msg)
            canvas.restoreState()

    document.build(story, onFirstPage=draw_watermark, onLaterPages=draw_watermark)
    buffer.seek(0)
    return buffer.getvalue()


# ---- ID Cards ----
_ID_CARD_WIDTH  = 85.6 * mm   # CR80 standard card width
_ID_CARD_HEIGHT = 54   * mm   # CR80 standard card height

# Premium design colour palette (Option A — deep teal + gold)
_C_ID_TEAL_LT   = colors.HexColor("#f0fdf9")   # lanyard zone / photo bg
_C_ID_TEAL_PALE = colors.HexColor("#ccfbf1")   # footer subtext
_C_ID_TEAL_DK2  = colors.HexColor("#134e4a")   # staff header (darker teal)
_C_ID_GOLD      = colors.HexColor("#d97706")   # gold rule + badge fill
_C_ID_SLATE     = colors.HexColor("#475569")   # info label colour
_C_ID_TEXT_DK   = colors.HexColor("#1e293b")   # info value colour
_C_ID_DIVIDER   = colors.HexColor("#e2e8f0")   # horizontal divider line
_C_ID_RED       = colors.HexColor("#dc2626")   # blood group text
_C_ID_RED_LT    = colors.HexColor("#fff1f2")   # blood badge background


def _make_qr_drawing(data, size_pt):
    """Return a ReportLab Drawing containing a QR code.
    Uses reportlab's built-in QrCodeWidget — no external library required.
    Returns None silently if QR generation fails for any reason."""
    try:
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics.barcode.qr import QrCodeWidget
        qr = QrCodeWidget(data)
        bounds = qr.getBounds()
        w = bounds[2] - bounds[0]
        h = bounds[3] - bounds[1]
        if w <= 0 or h <= 0:
            return None
        d = Drawing(size_pt, size_pt, transform=[size_pt / w, 0, 0, size_pt / h, 0, 0])
        d.add(qr)
        return d
    except Exception:
        return None


def _make_circular_photo(photo_path, size_px=80):
    """Crop a student photo to a circle and return a transparent-corner PNG BytesIO.
    Requires PIL/Pillow which is already a project dependency."""
    try:
        from PIL import ImageDraw as _PIDraw
        img  = PILImage.open(photo_path).convert("RGBA")
        side = min(img.width, img.height)
        left = (img.width  - side) // 2
        top  = (img.height - side) // 2
        img  = img.crop((left, top, left + side, top + side))
        img  = img.resize((size_px, size_px), PILImage.LANCZOS)
        mask = PILImage.new("L", (size_px, size_px), 0)
        _PIDraw.Draw(mask).ellipse((0, 0, size_px - 1, size_px - 1), fill=255)
        result = PILImage.new("RGBA", (size_px, size_px), (255, 255, 255, 0))
        result.paste(img, mask=mask)
        buf = BytesIO()
        result.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception:
        return None


class _IDCardBase(Flowable):
    """Shared canvas-drawing utilities for premium student and staff ID cards."""

    _W = _ID_CARD_WIDTH
    _H = _ID_CARD_HEIGHT

    # Fixed zone heights (points)
    _LANYARD_H = 7  * mm    # safe zone for hole punch
    _HEADER_H  = 14 * mm    # teal header band
    _GOLD_H    = 2.0         # gold accent rule
    _FOOTER_H  = 9  * mm    # teal footer band

    def __init__(self, school_profile):
        Flowable.__init__(self)
        self.school_profile = school_profile
        self.width  = self._W
        self.height = self._H

    def _zones(self):
        """Return y-positions and heights of every layout zone."""
        footer_y  = 0
        gold_y    = self._FOOTER_H
        body_y    = gold_y + self._GOLD_H
        body_h    = self._H - self._LANYARD_H - self._HEADER_H - body_y
        header_y  = body_y + body_h
        lanyard_y = header_y + self._HEADER_H
        return dict(
            footer_y=footer_y,   footer_h=self._FOOTER_H,
            gold_y=gold_y,       gold_h=self._GOLD_H,
            body_y=body_y,       body_h=body_h,
            header_y=header_y,   header_h=self._HEADER_H,
            lanyard_y=lanyard_y, lanyard_h=self._LANYARD_H,
        )

    @staticmethod
    def _fit_str(text, font, size, max_w):
        """Shrink font, then truncate, until text fits within max_w."""
        while size > 4.0 and pdfmetrics.stringWidth(text, font, size) > max_w:
            size -= 0.5
        while len(text) > 1 and pdfmetrics.stringWidth(text + "…", font, size) > max_w:
            text = text[:-1]
        return size, text

    def _draw_silhouette(self, c, cx, cy, r, col):
        """Simple head-and-body silhouette for photo placeholder."""
        c.setFillColor(col)
        c.circle(cx, cy + r * 0.18, r * 0.33, fill=1, stroke=0)
        c.ellipse(cx - r * 0.42, cy - r * 0.55, cx + r * 0.42, cy, fill=1, stroke=0)

    def _draw_lanyard_zone(self, c, z):
        c.saveState()
        c.setFillColor(_C_ID_TEAL_LT)
        c.rect(0, z['lanyard_y'], self._W, z['lanyard_h'], fill=1, stroke=0)
        c.setStrokeColor(_C_BRAND)
        c.setLineWidth(0.4)
        c.setDash([1.5, 1.5])
        c.circle(self._W / 2, z['lanyard_y'] + z['lanyard_h'] / 2, 2.8 * mm, fill=0, stroke=1)
        c.restoreState()

    def _draw_header(self, c, z, header_color, badge_label):
        c.saveState()
        c.setFillColor(header_color)
        c.rect(0, z['header_y'], self._W, z['header_h'], fill=1, stroke=0)

        # Circular school emblem
        emb_r  = 5.2 * mm
        emb_cx = 3.5 * mm + emb_r
        emb_cy = z['header_y'] + z['header_h'] / 2
        c.setFillColor(colors.white)
        c.circle(emb_cx, emb_cy, emb_r, fill=1, stroke=0)
        c.setStrokeColor(_C_ID_GOLD)
        c.setLineWidth(0.8)
        c.circle(emb_cx, emb_cy, emb_r, fill=0, stroke=1)
        c.setFillColor(header_color)
        emb_fs = emb_r * 0.72
        c.setFont("Helvetica-Bold", emb_fs)
        c.drawCentredString(emb_cx, emb_cy - emb_r * 0.30, "TH")

        # STUDENT / STAFF badge
        b_fs  = 5.0
        b_pad = 3.0
        b_w   = pdfmetrics.stringWidth(badge_label, "Helvetica-Bold", b_fs) + b_pad * 2
        b_h   = 9.5
        b_x   = self._W - b_w - 3 * mm
        b_y   = z['header_y'] + (z['header_h'] - b_h) / 2
        c.setFillColor(_C_ID_GOLD)
        c.roundRect(b_x, b_y, b_w, b_h, 2, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", b_fs)
        c.drawCentredString(b_x + b_w / 2, b_y + (b_h - b_fs) / 2 - 0.5, badge_label)

        # School name + location text
        name_x      = emb_cx + emb_r + 1.8 * mm
        avail_w     = b_x - name_x - 1.5 * mm
        school_name = (self.school_profile.name if self.school_profile else "THAKUR HARIKESH PRATAP SINGH INTERMEDIATE COLLEGE").upper()
        school_addr = ""
        if self.school_profile:
            raw_addr = getattr(self.school_profile, 'address', None) or ""
            school_addr = raw_addr.replace('\n', ', ').strip()
        if not school_addr:
            school_addr = "Uday, Kushinagar (U.P.)"
        if len(school_addr) > 45:
            school_addr = school_addr[:44].rstrip() + "…"

        c.setFillColor(colors.white)
        fs_n, name_fit = self._fit_str(school_name, "Helvetica-Bold", 7.5, avail_w)
        c.setFont("Helvetica-Bold", fs_n)
        c.drawString(name_x, z['header_y'] + z['header_h'] * 0.58, name_fit)

        c.setFillColor(_C_ID_TEAL_PALE)
        fs_a, addr_fit = self._fit_str(school_addr, "Helvetica", 5.5, avail_w)
        c.setFont("Helvetica", fs_a)
        c.drawString(name_x, z['header_y'] + z['header_h'] * 0.24, addr_fit)
        c.restoreState()

    def _draw_gold_rule(self, c, z):
        c.saveState()
        c.setFillColor(_C_ID_GOLD)
        c.rect(0, z['gold_y'], self._W, z['gold_h'], fill=1, stroke=0)
        c.restoreState()

    def _draw_footer(self, c, z, qr_data, footer_text, footer_color=None):
        c.saveState()
        c.setFillColor(footer_color or _C_BRAND)
        c.rect(0, z['footer_y'], self._W, z['footer_h'], fill=1, stroke=0)

        qr_size = 7.5 * mm
        qr_x    = 2.0 * mm
        qr_y    = (z['footer_h'] - qr_size) / 2
        qr_drw  = _make_qr_drawing(qr_data, qr_size)
        if qr_drw:
            from reportlab.graphics import renderPDF as _rpdf
            _rpdf.draw(qr_drw, c, qr_x, qr_y)

        c.setFillColor(_C_ID_TEAL_PALE)
        c.setFont("Helvetica", 5.5)
        c.drawString(qr_x + qr_size + 1.5 * mm,
                     z['footer_y'] + z['footer_h'] * 0.54, footer_text)

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 5.2)
        c.drawRightString(self._W - 2 * mm,
                          z['footer_y'] + z['footer_h'] * 0.32, "thpsic.com")
        c.restoreState()

    def _draw_card_border(self, c, border_color=None):
        c.saveState()
        c.setStrokeColor(border_color or _C_BRAND)
        c.setLineWidth(0.5)
        c.rect(0, 0, self._W, self._H, fill=0, stroke=1)
        c.restoreState()


class _StudentIDCardPremium(_IDCardBase):
    """World-class student ID card — deep teal + gold + circular photo."""

    def __init__(self, student, school_profile):
        super().__init__(school_profile)
        self.student = student

    def draw(self):
        c = self.canv
        s = self.student
        z = self._zones()

        # White base
        c.setFillColor(colors.white)
        c.rect(0, 0, self._W, self._H, fill=1, stroke=0)

        self._draw_lanyard_zone(c, z)
        self._draw_header(c, z, _C_BRAND, "STUDENT")
        self._draw_gold_rule(c, z)

        # ── Body ──────────────────────────────────────────────────────────────
        c.saveState()

        class_label = s.current_class.name if s.current_class else ""
        if s.current_section:
            sect = s.current_section.name
            class_label = f"{class_label}-{sect}" if class_label else sect
        adm    = s.admission_no or "-"
        blood  = s.blood_group or ""
        dob    = s.date_of_birth.strftime('%d-%m-%Y') if s.date_of_birth else "-"
        father = s.father_name or "-"
        phone  = s.mobile_primary or "-"

        # Circular photo
        ph_r   = 8 * mm
        ph_cx  = 3.5 * mm + ph_r
        b_gap  = (8 + 1.5 * mm) if blood else 0   # vertical space for blood badge
        ph_cy  = z['body_y'] + z['body_h'] / 2 + b_gap / 2 + 1

        c.setFillColor(_C_ID_TEAL_LT)
        c.circle(ph_cx, ph_cy, ph_r, fill=1, stroke=0)

        photo_drawn = False
        if s.photo:
            try:
                from reportlab.lib.utils import ImageReader as _IR
                path = s.photo.path
                if os.path.exists(path):
                    buf = _make_circular_photo(path, size_px=80)
                    if buf:
                        c.drawImage(_IR(buf), ph_cx - ph_r, ph_cy - ph_r,
                                    ph_r * 2, ph_r * 2, mask="auto")
                        photo_drawn = True
            except Exception:
                pass
        if not photo_drawn:
            self._draw_silhouette(c, ph_cx, ph_cy, ph_r, _C_BRAND)

        # Photo border ring
        c.setFillColor(colors.transparent)
        c.setStrokeColor(_C_BRAND)
        c.setLineWidth(1.2)
        c.circle(ph_cx, ph_cy, ph_r, fill=0, stroke=1)

        # Blood group badge
        if blood:
            bb_w = ph_r * 2
            bb_h = 8
            bb_x = ph_cx - ph_r
            bb_y = ph_cy - ph_r - 1.2 * mm - bb_h
            if bb_y >= z['body_y']:
                c.setFillColor(_C_ID_RED_LT)
                c.roundRect(bb_x, bb_y, bb_w, bb_h, 1.5, fill=1, stroke=0)
                c.setStrokeColor(_C_ID_RED)
                c.setLineWidth(0.4)
                c.roundRect(bb_x, bb_y, bb_w, bb_h, 1.5, fill=0, stroke=1)
                c.setFillColor(_C_ID_RED)
                c.setFont("Helvetica-Bold", 5.5)
                c.drawCentredString(bb_x + bb_w / 2, bb_y + (bb_h - 5.5) / 2 - 0.5, blood)

        # Info column
        info_x  = ph_cx + ph_r + 2.5 * mm
        info_w  = self._W - info_x - 2 * mm
        row_top = z['body_y'] + z['body_h'] - 3.5

        # Name
        c.setFillColor(_C_BRAND_DK)
        fs_n, n_fit = self._fit_str(s.full_name.upper(), "Helvetica-Bold", 9.0, info_w)
        c.setFont("Helvetica-Bold", fs_n)
        c.drawString(info_x, row_top - fs_n, n_fit)

        # Class + Adm
        cur_y = row_top - fs_n - 1.5
        c.setFillColor(_C_BRAND)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString(info_x, cur_y - 6.5, f"Class {class_label or '-'}  ·  Adm: {adm}")
        cur_y = cur_y - 6.5 - 3.5

        # Divider
        c.setStrokeColor(_C_ID_DIVIDER)
        c.setLineWidth(0.4)
        c.line(info_x, cur_y, info_x + info_w, cur_y)
        cur_y -= 2.0

        # Detail rows
        for label, value in [("DOB", dob), ("Father", father), ("Ph", phone)]:
            cur_y -= 7.5
            if cur_y < z['body_y'] + 1:
                break
            lbl_w = pdfmetrics.stringWidth(label, "Helvetica", 5.5)
            c.setFont("Helvetica", 5.5)
            c.setFillColor(_C_ID_SLATE)
            c.drawString(info_x, cur_y, label)
            c.setFillColor(_C_ID_TEXT_DK)
            val_fs, val_fit = self._fit_str(value, "Helvetica", 5.5, info_w - lbl_w - 2.5)
            c.setFont("Helvetica", val_fs)
            c.drawString(info_x + lbl_w + 2.5, cur_y, val_fit)

        c.restoreState()

        # Footer + outer border (drawn last so border is on top)
        sid     = s.legacy_sid or s.pk
        qr_data = f"THPS-STUDENT|SID={sid}|ADM={adm}|NAME={s.full_name}|CLS={class_label}"
        session = getattr(self.school_profile, "current_year", "") if self.school_profile else ""
        ft_text = f"Adm: {adm}" + (f"  ·  Session {session}" if session else "")
        self._draw_footer(c, z, qr_data, ft_text)
        self._draw_card_border(c)


class _StaffIDCardPremium(_IDCardBase):
    """World-class staff ID card — darker teal + gold + rounded-square placeholder."""

    def __init__(self, staff, school_profile):
        super().__init__(school_profile)
        self.staff = staff

    def draw(self):
        c  = self.canv
        st = self.staff
        z  = self._zones()

        # White base
        c.setFillColor(colors.white)
        c.rect(0, 0, self._W, self._H, fill=1, stroke=0)

        self._draw_lanyard_zone(c, z)
        self._draw_header(c, z, _C_ID_TEAL_DK2, "STAFF")
        self._draw_gold_rule(c, z)

        # ── Body ──────────────────────────────────────────────────────────────
        c.saveState()

        emp_code = st.legacy_emp_code or st.pk
        desig    = st.designation or st.get_staff_type_display()
        dob      = st.date_of_birth.strftime('%d-%m-%Y') if st.date_of_birth else "-"
        phone    = st.phone or "-"
        join_dt  = (st.date_of_joining.strftime('%d-%m-%Y')
                    if getattr(st, 'date_of_joining', None) else "-")

        # Rounded-square photo placeholder — centred vertically in body
        ph_size = 16 * mm
        ph_x    = 3.5 * mm
        ph_cy   = z['body_y'] + z['body_h'] / 2
        ph_y    = ph_cy - ph_size / 2

        c.setFillColor(_C_ID_TEAL_LT)
        c.roundRect(ph_x, ph_y, ph_size, ph_size, 2 * mm, fill=1, stroke=0)
        self._draw_silhouette(c, ph_x + ph_size / 2, ph_y + ph_size / 2,
                              ph_size / 2 * 0.88, _C_ID_TEAL_DK2)
        c.setFillColor(colors.transparent)
        c.setStrokeColor(_C_ID_TEAL_DK2)
        c.setLineWidth(1.2)
        c.roundRect(ph_x, ph_y, ph_size, ph_size, 2 * mm, fill=0, stroke=1)

        # Info column — emp code moved here as first detail row
        info_x  = ph_x + ph_size + 2.5 * mm
        info_w  = self._W - info_x - 2 * mm
        row_top = z['body_y'] + z['body_h'] - 3.5

        # Name
        c.setFillColor(_C_BRAND_DK)
        fs_n, n_fit = self._fit_str(st.full_name.upper(), "Helvetica-Bold", 9.0, info_w)
        c.setFont("Helvetica-Bold", fs_n)
        c.drawString(info_x, row_top - fs_n, n_fit)

        # Designation (gold — stands out as role)
        cur_y = row_top - fs_n - 1.5
        c.setFillColor(_C_ID_GOLD)
        fs_d, d_fit = self._fit_str(desig.upper(), "Helvetica-Bold", 7.0, info_w)
        c.setFont("Helvetica-Bold", fs_d)
        c.drawString(info_x, cur_y - fs_d, d_fit)
        cur_y = cur_y - fs_d - 3.5

        # Divider
        c.setStrokeColor(_C_ID_DIVIDER)
        c.setLineWidth(0.4)
        c.line(info_x, cur_y, info_x + info_w, cur_y)
        cur_y -= 2.0

        # Detail rows — Code / DOB / Joining / Ph
        for label, value in [("Code", str(emp_code)), ("DOB", dob), ("Joining", join_dt), ("Ph", phone)]:
            cur_y -= 7.5
            if cur_y < z['body_y'] + 1:
                break
            lbl_w = pdfmetrics.stringWidth(label, "Helvetica", 5.5)
            c.setFont("Helvetica", 5.5)
            c.setFillColor(_C_ID_SLATE)
            c.drawString(info_x, cur_y, label)
            c.setFillColor(_C_ID_TEXT_DK)
            val_fs, val_fit = self._fit_str(value, "Helvetica", 5.5, info_w - lbl_w - 2.5)
            c.setFont("Helvetica", val_fs)
            c.drawString(info_x + lbl_w + 2.5, cur_y, val_fit)

        c.restoreState()

        # Footer + border
        qr_data = f"THPS-STAFF|CODE={emp_code}|NAME={st.full_name}|DESIG={desig}"
        session = getattr(self.school_profile, "current_year", "") if self.school_profile else ""
        ft_text = f"Code: {emp_code}" + (f"  ·  Session {session}" if session else "")
        self._draw_footer(c, z, qr_data, ft_text, footer_color=_C_ID_TEAL_DK2)
        self._draw_card_border(c, border_color=_C_ID_TEAL_DK2)


# ── Public builder functions ───────────────────────────────────────────────────

def build_id_card_pdf(student, school_profile=None):
    """Single student ID card, centred on an A4 page."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=14 * mm, leftMargin=14 * mm,
        topMargin=14 * mm,   bottomMargin=14 * mm,
        title=f"ID Card - {student.full_name}",
    )
    card    = _StudentIDCardPremium(student, school_profile)
    wrapper = Table([[card]], colWidths=[doc.width])
    wrapper.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    doc.build([Spacer(1, 80 * mm), wrapper])
    buffer.seek(0)
    return buffer.getvalue()


def build_id_card_batch_pdf(students, school_profile=None):
    """Grid of student ID cards — 2 columns × 4 rows = 8 per A4 page.
    Lanyard safe zone is built into each card (no extra top-padding needed)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=8  * mm,   bottomMargin=8 * mm,
        title="Student ID Cards",
    )
    cards = [_StudentIDCardPremium(s, school_profile) for s in students]
    if not cards:
        doc.build([Paragraph("No students matched the current filter.",
                             getSampleStyleSheet()["Normal"])])
    else:
        cols      = 2
        rows_data = []
        for i in range(0, len(cards), cols):
            row = cards[i:i + cols]
            while len(row) < cols:
                row.append("")
            rows_data.append(row)
        grid = Table(rows_data, colWidths=[_ID_CARD_WIDTH] * cols)
        grid.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ]))
        doc.build([grid])
    buffer.seek(0)
    return buffer.getvalue()


def build_staff_id_card_pdf(staff, school_profile=None):
    """Single staff ID card, centred on an A4 page."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=14 * mm, leftMargin=14 * mm,
        topMargin=14 * mm,   bottomMargin=14 * mm,
        title=f"ID Card - {staff.full_name}",
    )
    card    = _StaffIDCardPremium(staff, school_profile)
    wrapper = Table([[card]], colWidths=[doc.width])
    wrapper.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    doc.build([Spacer(1, 80 * mm), wrapper])
    buffer.seek(0)
    return buffer.getvalue()


def build_staff_id_card_batch_pdf(staff_list, school_profile=None):
    """Grid of staff ID cards — 2 columns × 4 rows = 8 per A4 page.
    Lanyard safe zone is built into each card."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=8  * mm,   bottomMargin=8 * mm,
        title="Staff ID Cards",
    )
    cards = [_StaffIDCardPremium(s, school_profile) for s in staff_list]
    if not cards:
        doc.build([Paragraph("No staff found.", getSampleStyleSheet()["Normal"])])
    else:
        cols      = 2
        rows_data = []
        for i in range(0, len(cards), cols):
            row = cards[i:i + cols]
            while len(row) < cols:
                row.append("")
            rows_data.append(row)
        grid = Table(rows_data, colWidths=[_ID_CARD_WIDTH] * cols)
        grid.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ]))
        doc.build([grid])
    buffer.seek(0)
    return buffer.getvalue()


def build_feeder_school_statement_pdf(school, students, vouchers, school_profile=None):
    """Generate professional A4 PDF statement for an attached/feeder school."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Statement - {school.name}",
    )
    styles = getSampleStyleSheet()
    story = []

    school_name_text = school_profile.name if school_profile and school_profile.name else "THAKUR HARIKESH PRATAP SINGH INTERMEDIATE COLLEGE"
    school_address_text = school_profile.address if school_profile and school_profile.address else "Dudahi, Kushinagar, U.P."

    # Header
    header_data = [
        [Paragraph(f"<b><font size='13' color='#1E3A8A'>{school_name_text}</font></b>", styles["Normal"])],
        [Paragraph(f"<font size='9' color='#4B5563'>{school_address_text}</font>", styles["Normal"])],
        [Paragraph(f"<b><font size='11' color='#0F172A'>ATTACHED SCHOOL STATEMENT & STUDENT ROSTER (सत्र 2026-27)</font></b>", styles["Normal"])],
    ]
    header_table = Table(header_data, colWidths=[doc.width])
    header_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))

    # School & Financial Summary Box
    enrolled = school.total_enrolled_students
    demand = school.total_demand
    received = school.total_received
    balance = school.balance_due

    summary_data = [
        [
            Paragraph(f"<b>Attached School:</b> {school.name}", styles["Normal"]),
            Paragraph(f"<b>Code:</b> {school.code or '-'}", styles["Normal"]),
            Paragraph(f"<b>Date:</b> {timezone.localdate().strftime('%d/%m/%Y')}", styles["Normal"]),
        ],
        [
            Paragraph(f"<b>Director / Contact:</b> {school.contact_person or '-'}", styles["Normal"]),
            Paragraph(f"<b>Phone:</b> {school.phone or '-'}", styles["Normal"]),
            Paragraph(f"<b>Village / Post:</b> {school.village_address or '-'}", styles["Normal"]),
        ],
        [
            Paragraph(f"<b>Enrolled Students:</b> {enrolled}", styles["Normal"]),
            Paragraph(f"<b>Package Rate:</b> Rs. {school.package_rate_per_student:,.0f} / student", styles["Normal"]),
            Paragraph(f"<b>Total Demand:</b> Rs. {demand:,.2f}", styles["Normal"]),
        ],
        [
            Paragraph(f"<b>Total Paid:</b> Rs. {received:,.2f}", styles["Normal"]),
            Paragraph(f"<b>Balance Due:</b> <font color='#DC2626'><b>Rs. {balance:,.2f}</b></font>", styles["Normal"]),
            Paragraph(f"<b>Status:</b> {'Clear' if balance <= 0 else 'Pending'}", styles["Normal"]),
        ],
    ]
    summary_table = Table(summary_data, colWidths=[doc.width * 0.38, doc.width * 0.32, doc.width * 0.30])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 5 * mm))

    # Student Roster Table
    story.append(Paragraph("<b>1. ENROLLED STUDENTS ROSTER (नामांकित छात्र सूची)</b>", styles["Normal"]))
    story.append(Spacer(1, 2 * mm))

    student_rows = [
        [
            Paragraph("<b>#</b>", styles["Normal"]),
            Paragraph("<b>Adm No</b>", styles["Normal"]),
            Paragraph("<b>Student Name</b>", styles["Normal"]),
            Paragraph("<b>Father Name</b>", styles["Normal"]),
            Paragraph("<b>Class</b>", styles["Normal"]),
            Paragraph("<b>Section</b>", styles["Normal"]),
        ]
    ]
    for idx, s in enumerate(students, 1):
        student_rows.append([
            str(idx),
            str(s.admission_no or s.legacy_sid or ""),
            s.full_name or "",
            s.father_name or "",
            str(s.current_class or ""),
            str(s.current_section.name if s.current_section else ""),
        ])

    col_widths = [10 * mm, 25 * mm, 55 * mm, 55 * mm, 20 * mm, 15 * mm]
    stu_table = Table(student_rows, colWidths=col_widths, repeatRows=1)
    stu_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (1, -1), "CENTER"),
        ("ALIGN", (4, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(stu_table)
    story.append(Spacer(1, 5 * mm))

    # Payment History
    if vouchers:
        story.append(Paragraph("<b>2. PAYMENT HISTORY (जमा की गई किस्तों का विवरण)</b>", styles["Normal"]))
        story.append(Spacer(1, 2 * mm))
        pay_rows = [
            [
                Paragraph("<b>#</b>", styles["Normal"]),
                Paragraph("<b>Date</b>", styles["Normal"]),
                Paragraph("<b>Voucher No</b>", styles["Normal"]),
                Paragraph("<b>Mode</b>", styles["Normal"]),
                Paragraph("<b>Ref / Cheque No</b>", styles["Normal"]),
                Paragraph("<b>Amount</b>", styles["Normal"]),
            ]
        ]
        for idx, v in enumerate(vouchers, 1):
            pay_rows.append([
                str(idx),
                v.voucher_date.strftime("%d/%m/%Y"),
                v.voucher_no,
                v.get_payment_mode_display(),
                v.physical_slip_no or "-",
                f"Rs. {v.amount:,.2f}",
            ])
        p_widths = [10 * mm, 25 * mm, 35 * mm, 30 * mm, 40 * mm, 40 * mm]
        pay_table = Table(pay_rows, colWidths=p_widths, repeatRows=1)
        pay_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#065F46")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(pay_table)
        story.append(Spacer(1, 8 * mm))

    # Signatures block
    sig_data = [
        [
            Paragraph("Prepared By<br/><br/><br/>______________________", styles["Normal"]),
            Paragraph("School Representative<br/><br/><br/>______________________", styles["Normal"]),
            Paragraph("Principal / Manager<br/><br/><br/>______________________", styles["Normal"]),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[doc.width / 3] * 3)
    sig_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def build_attendance_register_pdf(
    students,
    school_class,
    section=None,
    month=8,
    year=2026,
    session=None,
    school_profile=None,
):
    """Generate professional A4 Landscape Monthly Attendance Register PDF for classroom pen marking."""
    import calendar
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=8 * mm,
        leftMargin=8 * mm,
        topMargin=7 * mm,
        bottomMargin=7 * mm,
        title=f"Attendance Register - {school_class.name} {section.name if section else ''} - {calendar.month_name[month]} {year}",
    )
    styles = getSampleStyleSheet()
    story = []

    school_name = (
        school_profile.name
        if school_profile and school_profile.name
        else "THAKUR HARIKESH PRATAP SINGH INTERMEDIATE COLLEGE"
    )
    school_address = (
        school_profile.address
        if school_profile and school_profile.address
        else "Uday, Dudahi, Kushinagar, U.P."
    )
    session_text = session.name if session else "2026-27"
    month_name = calendar.month_name[month]
    num_days = calendar.monthrange(year, month)[1]

    # Header section
    header_data = [
        [
            Paragraph(
                f"<b><font size='12' color='#1E3A8A'>{escape(school_name)}</font></b>",
                styles["Normal"],
            )
        ],
        [
            Paragraph(
                f"<font size='8' color='#4B5563'>{escape(school_address)}</font>",
                styles["Normal"],
            )
        ],
        [
            _devanagari_flowable(
                "STUDENT MONTHLY ATTENDANCE REGISTER (छात्र मासिक उपस्थिति पंजिका)",
                10,
                bold=True,
                align=1,
                color=(15, 23, 42, 255),
            )
        ],
    ]
    header_table = Table(header_data, colWidths=[doc.width])
    header_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 2 * mm))

    # Meta strip (Class, Section, Month, Year, Session, Total Students)
    sec_label = f"Section: <b>{section.name}</b>" if section else "Section: <b>All</b>"
    meta_data = [
        [
            Paragraph(f"Academic Session: <b>{session_text}</b>", styles["Normal"]),
            Paragraph(f"Class: <b>{school_class.name}</b>", styles["Normal"]),
            Paragraph(sec_label, styles["Normal"]),
            Paragraph(f"Month: <b>{month_name} {year}</b>", styles["Normal"]),
            Paragraph(f"Total Enrolled: <b>{len(students)}</b>", styles["Normal"]),
            Paragraph("Class Teacher: ________________", styles["Normal"]),
        ]
    ]
    meta_col_widths = [
        doc.width * 0.16,
        doc.width * 0.15,
        doc.width * 0.14,
        doc.width * 0.16,
        doc.width * 0.15,
        doc.width * 0.24,
    ]
    meta_table = Table(meta_data, colWidths=meta_col_widths)
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#94A3B8")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 2.5 * mm))

    # Days mapping (date -> weekday)
    day_abbrs = ["M", "Tu", "W", "Th", "F", "Sa", "Su"]
    sundays = []
    for d in range(1, num_days + 1):
        weekday = calendar.weekday(year, month, d)
        if weekday == 6:  # Sunday
            sundays.append(d)

    # Grid columns calculation
    # doc.width is 281 mm (297 - 16)
    fixed_widths = {
        "roll": 9 * mm,
        "adm": 13 * mm,
        "name": 44 * mm,
        "present": 13 * mm,
        "absent": 13 * mm,
        "remarks": 14 * mm,
    }
    fixed_sum = sum(fixed_widths.values())
    remaining_width = doc.width - fixed_sum
    day_col_width = remaining_width / num_days

    col_widths = [fixed_widths["roll"], fixed_widths["adm"], fixed_widths["name"]]
    for _ in range(num_days):
        col_widths.append(day_col_width)
    col_widths.extend([fixed_widths["present"], fixed_widths["absent"], fixed_widths["remarks"]])

    # Header Row 1: Numbers
    row1 = ["#", "Adm", "Student Name"]
    for d in range(1, num_days + 1):
        row1.append(str(d))
    row1.extend(["P", "A", "Remarks"])

    # Header Row 2: Day names
    row2 = ["", "", ""]
    for d in range(1, num_days + 1):
        weekday = calendar.weekday(year, month, d)
        row2.append(day_abbrs[weekday])
    row2.extend(["", "", ""])

    grid_data = [row1, row2]

    # Student rows
    for idx, s in enumerate(students, 1):
        roll_text = str(s.roll_no) if s.roll_no else str(idx)
        adm_text = str(s.admission_no or s.legacy_sid or "")
        name_text = s.full_name[:22] if s.full_name else ""
        row = [roll_text, adm_text, name_text]
        for _ in range(num_days):
            row.append("")  # Blank cell for teacher to mark P/A
        row.extend(["", "", ""])
        grid_data.append(row)

    # Styling the grid table
    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#1E3A8A")),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
        ("ALIGN", (0, 2), (1, -1), "CENTER"),  # Roll and Adm centered
        ("ALIGN", (2, 2), (2, -1), "LEFT"),    # Name left-aligned
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#475569")),
        ("FONTSIZE", (0, 0), (-1, 1), 6.5),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 2), (-1, -1), 6.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
    ]

    # Highlight Sunday columns in light grey/red tint
    for sun_day in sundays:
        col_idx = 2 + sun_day  # 0=roll, 1=adm, 2=name, 3=day 1
        table_styles.append(
            ("BACKGROUND", (col_idx, 2), (col_idx, -1), colors.HexColor("#F1F5F9"))
        )
        table_styles.append(
            ("TEXTCOLOR", (col_idx, 0), (col_idx, 1), colors.HexColor("#FCA5A5"))
        )

    grid_table = Table(grid_data, colWidths=col_widths, repeatRows=2)
    grid_table.setStyle(TableStyle(table_styles))
    story.append(grid_table)
    story.append(Spacer(1, 4 * mm))

    # Signatures block
    sig_data = [
        [
            Paragraph("Class Teacher Signature<br/><br/>______________________", styles["Normal"]),
            Paragraph("Attendance In-charge<br/><br/>______________________", styles["Normal"]),
            Paragraph("Principal Signature<br/><br/>______________________", styles["Normal"]),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[doc.width / 3] * 3)
    sig_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
