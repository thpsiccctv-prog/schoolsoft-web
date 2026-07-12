from decimal import Decimal
import math
import os
from io import BytesIO

from django.conf import settings
from django.utils import timezone
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
    def __init__(self, text, font_name, font_size):
        Flowable.__init__(self)
        self.text = text
        self.font_name = font_name
        self.font_size = font_size
        self.width = pdfmetrics.stringWidth(text, font_name, font_size)
        self.height = font_size * 1.2
    def draw(self):
        self.canv.saveState()
        self.canv.setFont(self.font_name, self.font_size)
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


def _devanagari_flowable(text, font_size_pt, bold=False, align=0):
    """Flowable for text that may contain Devanagari, Latin, or both mixed
    together. Devanagari runs are shaped/rasterized via HarfBuzz + FreeType
    (_render_devanagari_png); everything else (English words, digits,
    hyphens, colons, etc.) is rendered as a normal Helvetica Paragraph,
    since the Devanagari font has no Latin glyphs to fall back on. Multiple
    runs are laid out left-to-right in a borderless single-row Table so they
    read as one continuous line. align: 0=left, 1=center, 2=right."""
    latin_style = ParagraphStyle(
        "DevanagariLatinRun", fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=font_size_pt, leading=font_size_pt * 1.25,
    )
    fallback_style = ParagraphStyle(
        "DevanagariFallback", fontName="NotoSansDevanagari-Bold" if bold else "NotoSansDevanagari",
        fontSize=font_size_pt, leading=font_size_pt * 1.25,
    )

    pieces = []
    widths = []
    for is_deva, run_text in _text_script_runs(text):
        if not run_text.strip():
            continue
        if not is_deva:
            sf = StringFlowable(run_text, latin_style.fontName, font_size_pt)
            pieces.append(sf)
            widths.append(sf.width + 2) # small buffer
            continue
        rendered = _render_devanagari_png(run_text, font_size_pt, bold=bold)
        if rendered is None:
            sf = StringFlowable(run_text, fallback_style.fontName, font_size_pt)
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


def build_fee_receipt_pdf(receipt, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=8 * mm,
        bottomMargin=8 * mm,
        title=f"Fee Receipt {receipt.receipt_no}",
    )

    styles = getSampleStyleSheet()
    
    # Premium Styles
    brand_color = colors.HexColor("#0f766e")
    text_color = colors.HexColor("#1e293b")
    light_bg = colors.HexColor("#f8fafc")
    border_color = colors.HexColor("#cbd5e1")
    
    title_style = ParagraphStyle(
        "ReceiptTitle",
        parent=styles["Title"],
        fontSize=16,
        leading=18,
        alignment=0, # Left align
        textColor=brand_color,
        fontName="Helvetica-Bold",
        spaceAfter=1 * mm,
    )
    small_style = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=7,
        leading=8,
        textColor=colors.HexColor("#64748b"),
    )
    badge_style = ParagraphStyle(
        "Badge",
        parent=styles["Normal"],
        fontSize=8,
        leading=9,
        fontName="Helvetica-Bold",
        textColor=brand_color,
        backColor=colors.HexColor("#ecfdf5"),
        alignment=0,
        spaceBefore=2 * mm,
    )

    school_name = school_profile.name if school_profile else "SchoolSoft Fee Receipt"
    school_address = school_profile.address if school_profile else "Premium Migration Prototype"
    school_contact = ""
    if school_profile:
        contact_parts = []
        if school_profile.phone:
            contact_parts.append(f"Phone: {school_profile.phone}")
        if school_profile.email:
            contact_parts.append(f"Email: {school_profile.email}")
        school_contact = " | ".join(contact_parts)

    story = []
    
    # Header Table (School Info Left, Receipt No Right)
    header_data = [
        [
            [Paragraph(school_name.upper(), title_style), 
             Paragraph(school_address, small_style), 
             Paragraph(school_contact, small_style),
             Paragraph(" FEE RECEIPT ", badge_style)],
            [Paragraph(f"<b>Receipt No.</b><br/><font size=13>{receipt.receipt_no}</font>",
                      ParagraphStyle("RNo", alignment=2, leading=15, textColor=text_color))]
        ]
    ]
    header_table = Table(header_data, colWidths=[112 * mm, 62 * mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('LINEBELOW', (0,0), (-1,-1), 1.5, border_color),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
    ]))
    
    story.extend([header_table, Spacer(1, 5 * mm)])

    student = receipt.student
    class_label = receipt.display_class_section

    month_label = receipt.from_month
    if receipt.to_month and receipt.to_month != receipt.from_month:
        month_label = f"{receipt.from_month} to {receipt.to_month}"

    meta = [
        ["Student Name", receipt.display_student_name, "Date", receipt.receipt_date.strftime("%d-%m-%Y")],
        ["SID / Admn", f"{student.legacy_sid or ''} / {student.admission_no or ''}", "Class", class_label],
        ["Fee Month", month_label, "Mode", receipt.get_payment_mode_display()],
    ]
    meta_table = Table(meta, colWidths=[34 * mm, 58 * mm, 30 * mm, 52 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, border_color),
                ("BACKGROUND", (0, 0), (0, -1), light_bg),
                ("BACKGROUND", (2, 0), (2, -1), light_bg),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#475569")),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#475569")),
                ("TEXTCOLOR", (1, 0), (1, -1), text_color),
                ("TEXTCOLOR", (3, 0), (3, -1), text_color),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([meta_table, Spacer(1, 5 * mm)])

    line_rows = [["Fee Head Description", "Amount (Rs.)"]]
    for line in receipt.lines.select_related("fee_head").all():
        line_rows.append([line.fee_head.name, money(line.amount)])

    body_last_idx = len(line_rows) - 1
    total_start_idx = len(line_rows)
    line_rows.append(["Fee Total", money(receipt.legacy_fee_total)])
    
    if receipt.concession_amount > 0:
        line_rows.append(["Concession / Discount", f"- {money(receipt.concession_amount)}"])
    if receipt.late_fee_amount > 0:
        line_rows.append(["Late Fee Fine", f"+ {money(receipt.late_fee_amount)}"])
        
    net_idx = len(line_rows)
    line_rows.append(["Net Payable", f"Rs. {money(receipt.legacy_net_total)}"])
    line_rows.append(["Amount Paid", f"Rs. {money(receipt.received_amount)}"])
    
    due_idx = None
    if receipt.legacy_due_amount > 0:
        due_idx = len(line_rows)
        line_rows.append(["Balance Due", f"Rs. {money(receipt.legacy_due_amount)}"])

    fee_table = Table(line_rows, colWidths=[124 * mm, 50 * mm], repeatRows=1)
    
    ts = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, border_color),
        
        # Body Lines
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, body_last_idx), text_color),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        
        # Totals Section
        ("FONTNAME", (0, total_start_idx), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, total_start_idx), (-1, -1), colors.HexColor("#475569")),
        ("LINEABOVE", (0, total_start_idx), (-1, total_start_idx), 1, border_color),
        
        # Net Payable Row
        ("BACKGROUND", (0, net_idx), (-1, net_idx), light_bg),
        ("TEXTCOLOR", (0, net_idx), (-1, net_idx), text_color),
        ("LINEABOVE", (0, net_idx), (-1, net_idx), 1, border_color),
        ("LINEBELOW", (0, net_idx), (-1, net_idx), 1, border_color),
        ("FONTSIZE", (0, net_idx), (-1, net_idx), 9),
    ]

    if body_last_idx >= 1:
        ts.append(("LINEBELOW", (0, 1), (-1, body_last_idx), 0.5, colors.HexColor("#e2e8f0")))
    
    if due_idx:
        ts.append(("TEXTCOLOR", (0, due_idx), (-1, due_idx), colors.HexColor("#dc2626")))
        
    fee_table.setStyle(TableStyle(ts))
    story.append(fee_table)

    if receipt.remarks:
        story.extend([Spacer(1, 3 * mm), Paragraph(f"<i>Remarks: {receipt.remarks}</i>", small_style)])

    story.extend(
        [
            Spacer(1, 8 * mm),
            Table(
                [["Cashier's Signature", "Parent / Guardian"]],
                colWidths=[70 * mm, 70 * mm],
                style=TableStyle(
                    [
                        ("LINEABOVE", (0, 0), (0, 0), 1, border_color),
                        ("LINEABOVE", (1, 0), (1, 0), 1, border_color),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTSIZE", (0, 0), (-1, -1), 7),
                        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#64748b")),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ]
                ),
            ),
        ]
    )

    # Add Watermark callback
    def add_watermark(canvas, doc):
        canvas.saveState()
        if receipt.is_cancelled:
            canvas.setFont('Helvetica-Bold', 90)
            canvas.setFillColor(colors.HexColor("#dc2626"), alpha=0.2)
            canvas.translate(105*mm, 148*mm)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "CANCELLED")
        elif receipt.is_edited:
            canvas.setFont('Helvetica-Bold', 90)
            canvas.setFillColor(colors.HexColor("#f59e0b"), alpha=0.2) # Amber
            canvas.translate(105*mm, 148*mm)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "EDITED")
            # Also draw footer note
            canvas.restoreState()
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.HexColor("#b45309"))
            footer_text = f"Edited on {receipt.edited_at.strftime('%d-%m-%Y %H:%M')} by {receipt.edited_by.username if receipt.edited_by else 'System'}. Reason: {receipt.edit_reason}"
            canvas.drawString(12*mm, 12*mm, footer_text)
        else:
            canvas.setFont('Helvetica-Bold', 100)
            canvas.setFillColor(colors.HexColor("#0f766e"), alpha=0.04)
            canvas.translate(105*mm, 148*mm)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "SCHOOLSOFT")
        canvas.restoreState()

    document.build(story, onFirstPage=add_watermark, onLaterPages=add_watermark)
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
    name_st = ParagraphStyle("PhName", fontSize=18, leading=21, alignment=1,
                             textColor=_C_BRAND_DK, fontName="Helvetica-Bold", spaceAfter=1)
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
        t_hi = ParagraphStyle("PhTiHi", fontName="NotoSansDevanagari-Bold", fontSize=12.5,
                              leading=15, alignment=1, textColor=colors.white)
        t_en = ParagraphStyle("PhTiEn", fontName="Helvetica-Bold", fontSize=13,
                              leading=15, alignment=1, textColor=colors.white)
        band = Table([[Paragraph(title_hi, t_hi)], [Paragraph(title_en, t_en)]], colWidths=[180 * mm])
    else:
        t_en = ParagraphStyle("PhTiEn2", fontName="Helvetica-Bold", fontSize=13.5,
                              leading=16, alignment=1, textColor=colors.white)
        band = Table([[Paragraph(title_en, t_en)]], colWidths=[180 * mm])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _C_BRAND),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROUNDEDCORNERS", [3, 3, 3, 3]),
    ]))
    story.append(band)
    if subtitle:
        story.append(Paragraph(subtitle, ParagraphStyle("PhSub", fontSize=9.5, leading=12,
                                                        alignment=1, textColor=_C_MUTED, spaceBefore=3)))
    story.append(Spacer(1, 5 * mm))


def build_character_certificate_pdf(student, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
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

    ref_no = f"CC-{timezone.localdate().year}-{student.admission_no or student.legacy_sid or student.pk}"
    meta = ParagraphStyle("CcMeta", fontSize=9.5, textColor=_C_MUTED)
    mrow = Table([[Paragraph(f"<b>Ref. No.:</b> {ref_no}", meta),
                   Paragraph(f"<b>Date:</b> {timezone_today()}",
                             ParagraphStyle("CcMetaR", parent=meta, alignment=2))]],
                 colWidths=[90 * mm, 90 * mm])
    story.append(mrow)
    story.append(Spacer(1, 6 * mm))

    body = ParagraphStyle("CcBody", parent=styles["Normal"], fontSize=11.5, leading=22,
                          alignment=4, textColor=_C_INK, firstLineIndent=10 * mm, spaceAfter=5 * mm)

    class_label = _class_section_label(student)
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

    story.append(Spacer(1, 26 * mm))
    sign = Table([["", "Principal / Headmaster"]], colWidths=[95 * mm, 75 * mm])
    sign.setStyle(TableStyle([
        ("LINEABOVE", (1, 0), (1, 0), 0.6, _C_INK),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 10), ("TEXTCOLOR", (0, 0), (-1, -1), _C_INK),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sign)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("(Office Seal)", ParagraphStyle("CcSeal", fontSize=8.5, textColor=_C_MUTED)))

    document.build(story)
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
_ID_CARD_WIDTH = 85.6 * mm  # standard CR80 card size
_ID_CARD_HEIGHT = 54 * mm


def _id_card_photo_flowable(student):
    photo_path = None
    if student.photo:
        try:
            candidate = student.photo.path
            if os.path.exists(candidate):
                photo_path = candidate
        except (ValueError, NotImplementedError, OSError):
            photo_path = None
    if photo_path:
        try:
            return Image(photo_path, width=20 * mm, height=24 * mm)
        except Exception:
            pass
    return Paragraph(
        "No<br/>Photo",
        ParagraphStyle("IdNoPhoto", fontSize=7, leading=9, alignment=1, textColor=_C_MUTED),
    )


def _id_card_flowable(student, school_profile):
    school_name = (school_profile.name if school_profile else "SCHOOLSOFT").upper()

    header_style = ParagraphStyle(
        "IdHeader", fontSize=8.5, leading=10, fontName="Helvetica-Bold",
        textColor=colors.white, alignment=1,
    )
    name_style = ParagraphStyle("IdName", fontSize=10, leading=12, fontName="Helvetica-Bold", textColor=_C_BRAND_DK)
    info_style = ParagraphStyle("IdInfo", fontSize=7.5, leading=9.5)
    footer_style = ParagraphStyle("IdFooter", fontSize=6.5, leading=8, alignment=1, textColor=colors.white)

    class_label = student.current_class.name if student.current_class else ""
    if student.current_section:
        class_label = f"{class_label}-{student.current_section.name}" if class_label else student.current_section.name

    info_cell = [
        Paragraph(student.full_name, name_style),
        Paragraph(f"Class: {class_label or '-'}  |  Roll: {student.roll_no or '-'}", info_style),
        Paragraph(f"House: {student.house.name if student.house else '-'}", info_style),
        Paragraph(f"DOB: {student.date_of_birth.strftime('%d-%m-%Y') if student.date_of_birth else '-'}", info_style),
        Paragraph(f"Father: {student.father_name or '-'}", info_style),
        Paragraph(f"Ph: {student.mobile_primary or '-'}", info_style),
    ]

    body = Table(
        [[_id_card_photo_flowable(student), info_cell]],
        colWidths=[22 * mm, _ID_CARD_WIDTH - 26 * mm],
    )
    body.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    session_label = getattr(school_profile, "current_year", "") if school_profile else ""
    footer_text = f"Adm No: {student.admission_no or '-'}" + (f"  |  Session {session_label}" if session_label else "")

    card = Table(
        [
            [Paragraph(school_name, header_style)],
            [body],
            [Paragraph(footer_text, footer_style)],
        ],
        colWidths=[_ID_CARD_WIDTH],
    )
    card.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, _C_BRAND),
        ("BACKGROUND", (0, 0), (0, 0), _C_BRAND),
        ("BACKGROUND", (0, 2), (0, 2), _C_BRAND),
        ("TOPPADDING", (0, 0), (0, 0), 3),
        ("BOTTOMPADDING", (0, 0), (0, 0), 3),
        ("TOPPADDING", (0, 2), (0, 2), 2),
        ("BOTTOMPADDING", (0, 2), (0, 2), 2),
    ]))
    return card


def build_id_card_pdf(student, school_profile=None):
    """Single ID card, one per A4 page (print + cut + laminate)."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"ID Card - {student.full_name}",
    )
    story = [Spacer(1, 100 * mm)]
    card = _id_card_flowable(student, school_profile)
    wrapper = Table([[card]], colWidths=[document.width])
    wrapper.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(wrapper)
    document.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def build_id_card_batch_pdf(students, school_profile=None):
    """Grid of ID cards (2 per row) across as many A4 pages as needed - for
    printing a whole class/section at once, then cutting apart."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="ID Cards",
    )
    story = []
    cards = [_id_card_flowable(s, school_profile) for s in students]

    if not cards:
        story.append(Paragraph("No students matched the current filter.", getSampleStyleSheet()["Normal"]))
    else:
        cols = 2
        rows_data = []
        for i in range(0, len(cards), cols):
            row = cards[i:i + cols]
            while len(row) < cols:
                row.append("")
            rows_data.append(row)
        grid = Table(
            rows_data,
            colWidths=[_ID_CARD_WIDTH] * cols,
        )
        grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(grid)

    document.build(story)
    buffer.seek(0)
    return buffer.getvalue()
