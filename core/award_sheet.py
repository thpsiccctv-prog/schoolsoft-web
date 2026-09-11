"""
Teacher Award Sheet (अंक प्रविष्टि पत्रक / Foil List) Generator for SchoolSoft.
Produces high-precision, printable A4 PDF award lists per Class/Section/Subject
designed specifically for handwritten marks entry by teachers, followed by
robust mobile phone scan / flatbed scan OCR ingestion.
"""

from decimal import Decimal
import io
import math
import os

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image
)
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

from core.models import ExamTest, SchoolClass, Section, Student, ExamTerm
from core.pdf import _devanagari_flowable, LOGO_PATH


# Page geometry (A4: 595.27 x 841.89 pt)
PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT_MARGIN = 8 * mm   # ~22.68 pt
RIGHT_MARGIN = 8 * mm
TOP_MARGIN = 6 * mm
BOTTOM_MARGIN = 6 * mm
USABLE_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN  # ~550 pt

STUDENTS_PER_PAGE = 22  # Generous row height (~24 pt) for handwriting without page overflow


def make_digit_boxes(n, box_w=13, box_h=15):
    """
    Renders discrete vector digit boxes for handwriting.
    Enforces one numeral per box to eliminate OCR ambiguity.
    """
    cols = [box_w] * n
    data = [[""] * n]
    t = Table(data, colWidths=cols, rowHeights=[box_h])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#334155")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#64748B")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFFFF")),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def make_qr_widget(token, size=46):
    """
    Creates a scannable vector QR code for machine sheet identification.
    """
    qr = QrCodeWidget(token)
    b = qr.getBounds()
    w = b[2] - b[0]
    h = b[3] - b[1]
    d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
    d.add(qr)
    return d


def _make_bilingual_cell(text_en, text_hi="", font_size=7.2, bold_en=True):
    """
    Renders a table cell with shaped Devanagari (if present) stacked cleanly
    with English text, or plain English if no Hindi translation exists.
    """
    text_en = (text_en or "").strip()
    text_hi = (text_hi or "").strip()

    if text_hi and text_hi != text_en:
        try:
            hi_flow = _devanagari_flowable(text_hi, font_size, bold=True, color=(15, 23, 42, 255))
            if hi_flow:
                en_para = Paragraph(f"<font size=5.5 color='#475569'>{text_en}</font>", ParagraphStyle("EnSub", fontName="Helvetica", leading=6.5))
                t = Table([[hi_flow], [en_para]], colWidths=[None])
                t.setStyle(TableStyle([
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]))
                return t
        except Exception:
            pass

    fn = "Helvetica-Bold" if bold_en else "Helvetica"
    return Paragraph(f"<b>{text_en}</b>" if bold_en else text_en, ParagraphStyle("EnPlain", fontName=fn, fontSize=font_size, leading=font_size * 1.15))


def _header_cell(en_text, hi_text="", sub_text="", align=1, en_font_size=6.8):
    """
    Renders clean, styled table header cells.
    Stacks English, shaped Devanagari, and subtext vertically so they never overflow narrow columns.
    """
    elements = []
    if en_text:
        elements.append(Paragraph(
            f"<b>{en_text}</b>",
            ParagraphStyle(
                "HdrEn",
                fontName="Helvetica-Bold",
                fontSize=en_font_size,
                leading=en_font_size * 1.15,
                alignment=align,
                textColor=colors.white,
            )
        ))
    if hi_text:
        elements.append(_devanagari_flowable(hi_text, 5.2, bold=True, align=align, color=(203, 213, 225, 255)))

    if sub_text:
        elements.append(Paragraph(
            f"<font size=5 color='#94A3B8'>{sub_text}</font>",
            ParagraphStyle(
                "HdrSub",
                fontName="Helvetica",
                fontSize=5,
                leading=6.2,
                alignment=align,
                textColor=colors.HexColor("#94A3B8"),
            )
        ))

    if len(elements) == 1:
        return elements[0]

    t = Table([[e] for e in elements], colWidths=[None])
    t.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("ALIGN", (0, 0), (-1, -1), "CENTER" if align == 1 else "LEFT"),
    ]))
    return t


def _draw_sheet_fiducials_and_decorations(canvas, doc, sheet_token):
    """
    Draws 4 corner fiducial markers [+] and machine-readable boundary markers
    so mobile phone photos / flatbed scans can be reliably straightened,
    perspective-corrected, and anchored.
    """
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#0F172A"))
    canvas.setFillColor(colors.HexColor("#0F172A"))
    canvas.setLineWidth(1.2)

    # 4 Corner Fiducial crosses [+] inset 5mm from edges
    inset = 5 * mm
    cross_len = 4 * mm

    corners = [
        (inset, PAGE_HEIGHT - inset),                     # Top-Left
        (PAGE_WIDTH - inset, PAGE_HEIGHT - inset),         # Top-Right
        (inset, inset),                                   # Bottom-Left
        (PAGE_WIDTH - inset, inset),                      # Bottom-Right
    ]

    for cx, cy in corners:
        canvas.line(cx - cross_len, cy, cx + cross_len, cy)
        canvas.line(cx, cy - cross_len, cx, cy + cross_len)
        canvas.circle(cx, cy, 1.2 * mm, stroke=1, fill=0)

    # Bottom machine token line
    canvas.setFont("Helvetica-Bold", 6.5)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.drawString(LEFT_MARGIN, 3.5 * mm, f"{sheet_token} | THPS INTERMEDIATE COLLEGE | COMPUTER GENERATED AWARD LIST")
    canvas.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, 3.5 * mm, timezone.now().strftime("PRINTED: %d-%b-%Y %H:%M"))

    canvas.restoreState()


def build_award_sheet_pdf(exam_test, section=None, students=None):
    """
    Generates a complete, multi-page printable A4 PDF Award Sheet for a given ExamTest.
    If section is provided, filters students to that section; otherwise all active students in class.
    """
    school_class = exam_test.school_class
    subject = exam_test.subject
    has_practical = bool(exam_test.practical_max_marks and exam_test.practical_max_marks > Decimal("0.00"))

    if students is None:
        qs = Student.objects.filter(is_active=True, current_class=school_class)
        if section:
            qs = qs.filter(current_section=section)
        # Order by roll_no (nulls last), then legacy_sid, then name
        students = list(qs.order_by("roll_no", "legacy_sid", "full_name"))

    total_students = len(students)
    total_pages = max(1, math.ceil(total_students / STUDENTS_PER_PAGE)) if total_students else 1

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=f"Award Sheet - {school_class.name} - {subject.name}",
    )

    story = []

    sec_code = section.name if section else "ALL"
    base_token = f"QEX2627-C{school_class.id}-S{sec_code}-T{exam_test.id}"

    for page_idx in range(total_pages):
        page_no = page_idx + 1
        start_i = page_idx * STUDENTS_PER_PAGE
        end_i = min(start_i + STUDENTS_PER_PAGE, total_students)
        page_students = students[start_i:end_i]

        sheet_token = f"{base_token}-P{page_no}OF{total_pages}"

        # 1. HEADER BANNER (Logo + Titles + QR Code)
        qr_drawing = make_qr_widget(sheet_token, size=46)
        logo_elem = Image(LOGO_PATH, width=14 * mm, height=14 * mm) if os.path.exists(LOGO_PATH) else Paragraph("<b>THPSIC</b>", ParagraphStyle("Lg", alignment=1))

        center_cell = [
            Paragraph("<b>T H P S &nbsp; I N T E R M E D I A T E &nbsp; C O L L E G E</b>", ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=11, leading=13, alignment=1, textColor=colors.HexColor("#0F172A"))),
            _devanagari_flowable("त्रैमासिक परीक्षा 2026-27 (अंक प्रविष्टि पत्रक)", 9, bold=True, align=1, color=(30, 58, 138, 255)),
            Paragraph("QUARTERLY EXAMINATION 2026-27 &mdash; TEACHER AWARD SHEET", ParagraphStyle("H3", fontName="Helvetica-Bold", fontSize=6.5, leading=8, alignment=1, textColor=colors.HexColor("#475569"))),
            Paragraph(f"<b>[ SHEET-ID: {sheet_token} ]</b>", ParagraphStyle("H4", fontName="Helvetica-Bold", fontSize=7.5, leading=9, alignment=1, textColor=colors.HexColor("#097969"))),
        ]

        header_table = Table([[logo_elem, center_cell, qr_drawing]], colWidths=[50, 440, 60])
        header_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 0), (2, 0), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 1.5 * mm))

        # 2. METADATA STRIP (Class, Section, Subject, Max/Pass Marks, Page)
        sec_label = f"Section: <b>{section.name}</b>" if section else "Section: <b>All</b>"
        pr_label = f" &nbsp;|&nbsp; Pr: <b>{int(exam_test.practical_max_marks)}</b>" if has_practical else ""
        sub_display_name = subject.name.split("(")[0].strip() if "(" in subject.name else subject.name
        meta_html = (
            f"Class: <b>{school_class.name}</b> &nbsp;|&nbsp; {sec_label} &nbsp;|&nbsp; "
            f"Subject: <b>{sub_display_name}</b> &nbsp;|&nbsp; "
            f"Max Marks: <b>{int(exam_test.max_marks)}</b> (Th: <b>{int(exam_test.theory_max_marks)}</b>{pr_label}) &nbsp;|&nbsp; "
            f"Pass: <b>{int(exam_test.pass_marks)}</b> &nbsp;|&nbsp; "
            f"Page: <b>{page_no} of {total_pages}</b>"
        )
        meta_para = Paragraph(meta_html, ParagraphStyle("MetaStrip", fontName="Helvetica", fontSize=7.8, leading=9.5, alignment=1, textColor=colors.HexColor("#0F172A")))
        meta_table = Table([[meta_para]], colWidths=[USABLE_WIDTH])
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#94A3B8")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 1.5 * mm))

        # 3. MAIN MARKS GRID TABLE (Dynamic Layout based on Practical)
        if has_practical:
            # Columns: S.N.(22), ROLL(30), ADM/SID(42), STUDENT(122), FATHER(96), THEORY(54), PRACTICAL(48), TOTAL(58), AB(38), SIGN(40) = 550 pt
            col_widths = [22, 30, 42, 122, 96, 54, 48, 58, 38, 40]
            headers = [
                _header_cell("S.N.", "क्र.", en_font_size=6.2),
                _header_cell("ROLL", "रोल", en_font_size=6.5),
                _header_cell("ADM/SID", "प्रवेश", en_font_size=6.5),
                _header_cell("STUDENT NAME", "विद्यार्थी का नाम", align=0, en_font_size=6.8),
                _header_cell("FATHER'S NAME", "पिता का नाम", align=0, en_font_size=6.8),
                _header_cell("THEORY", "लिखित", sub_text=f"Max {int(exam_test.theory_max_marks)}", en_font_size=6.5),
                _header_cell("PRACTICAL", "प्रायोगिक", sub_text=f"Max {int(exam_test.practical_max_marks)}", en_font_size=5.8),
                _header_cell("TOTAL", "कुल योग", sub_text=f"Max {int(exam_test.max_marks)}", en_font_size=6.5),
                _header_cell("ABSENT", sub_text="[ AB ]", en_font_size=6.2),
                _header_cell("SIGN", "हस्ताक्षर", en_font_size=6.2),
            ]
        else:
            # Pure Theory: Hide Practical & Total columns to provide ample room for names & handwriting boxes
            # Columns: S.N.(24), ROLL(32), ADM/SID(48), STUDENT(148), FATHER(122), THEORY(70), AB(46), SIGN(60) = 550 pt
            col_widths = [24, 32, 48, 148, 122, 70, 46, 60]
            headers = [
                _header_cell("S.N.", "क्र.", en_font_size=6.5),
                _header_cell("ROLL", "रोल", en_font_size=6.8),
                _header_cell("ADM/SID", "प्रवेश", en_font_size=6.8),
                _header_cell("STUDENT NAME", "विद्यार्थी का नाम", align=0, en_font_size=7.0),
                _header_cell("FATHER'S NAME", "पिता का नाम", align=0, en_font_size=7.0),
                _header_cell("THEORY", "लिखित अंक", sub_text=f"Max {int(exam_test.theory_max_marks)}", en_font_size=7.0),
                _header_cell("ABSENT", sub_text="[ AB ]", en_font_size=6.8),
                _header_cell("TEACHER SIGN", "हस्ताक्षर", en_font_size=6.8),
            ]

        table_rows = [headers]
        tstyles = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, 0), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
            ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#334155")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#64748B")),
        ]

        th_boxes_cnt = 3 if (exam_test.theory_max_marks and exam_test.theory_max_marks >= 100) else 2
        pr_boxes_cnt = 2

        for row_i, student in enumerate(page_students):
            curr_row_idx = row_i + 1
            s_no = str(start_i + row_i + 1)
            # Guard against multi-digit board registration numbers in roll_no
            roll_str = str(student.roll_no) if (student.roll_no and student.roll_no < 1000) else "—"
            adm_str = str(student.admission_no or student.legacy_sid or "")

            name_en = student.full_name
            name_hi = getattr(student, "full_name_hindi", "") or ""
            name_cell = _make_bilingual_cell(name_en, name_hi, font_size=7.2, bold_en=True)

            father_en = student.father_name or ""
            father_hi = getattr(student, "father_name_hindi", "") or ""
            father_cell = _make_bilingual_cell(father_en, father_hi, font_size=6.8, bold_en=False)

            th_cell = make_digit_boxes(th_boxes_cnt, box_w=13, box_h=15)
            ab_cell = Paragraph("<font size=8 color='#475569'><b>[ &nbsp; ]</b></font>", ParagraphStyle("AB", alignment=1))

            if has_practical:
                pr_cell = make_digit_boxes(pr_boxes_cnt, box_w=13, box_h=15)
                tot_cell = make_digit_boxes(3, box_w=12, box_h=15)
                row_data = [
                    Paragraph(s_no, ParagraphStyle("SN", fontName="Helvetica-Bold", fontSize=7.5, alignment=1)),
                    Paragraph(roll_str, ParagraphStyle("RL", fontName="Helvetica", fontSize=7.5, alignment=1)),
                    Paragraph(adm_str, ParagraphStyle("AD", fontName="Helvetica-Bold", fontSize=7.5, alignment=1, textColor=colors.HexColor("#1E3A8A"))),
                    name_cell,
                    father_cell,
                    th_cell,
                    pr_cell,
                    tot_cell,
                    ab_cell,
                    "",  # Teacher sign
                ]
            else:
                row_data = [
                    Paragraph(s_no, ParagraphStyle("SN", fontName="Helvetica-Bold", fontSize=7.5, alignment=1)),
                    Paragraph(roll_str, ParagraphStyle("RL", fontName="Helvetica", fontSize=7.5, alignment=1)),
                    Paragraph(adm_str, ParagraphStyle("AD", fontName="Helvetica-Bold", fontSize=7.5, alignment=1, textColor=colors.HexColor("#1E3A8A"))),
                    name_cell,
                    father_cell,
                    th_cell,
                    ab_cell,
                    "",  # Teacher sign
                ]

            table_rows.append(row_data)

            if row_i % 2 == 1:
                tstyles.append(("BACKGROUND", (0, curr_row_idx), (-1, curr_row_idx), colors.HexColor("#F8FAFC")))

            tstyles.append(("ALIGN", (0, curr_row_idx), (-1, curr_row_idx), "CENTER"))
            tstyles.append(("VALIGN", (0, curr_row_idx), (-1, curr_row_idx), "MIDDLE"))
            tstyles.append(("TOPPADDING", (0, curr_row_idx), (-1, curr_row_idx), 2.2))
            tstyles.append(("BOTTOMPADDING", (0, curr_row_idx), (-1, curr_row_idx), 2.2))

        marks_table = Table(table_rows, colWidths=col_widths)
        marks_table.setStyle(TableStyle(tstyles))
        story.append(marks_table)
        story.append(Spacer(1, 2 * mm))

        # 4. FOOTER VERIFICATION STRIP (2 Distinct Signatures + Counts)
        footer_data = [
            [
                Paragraph(f"<b>Total Enrolled:</b> {total_students} &nbsp;|&nbsp; <b>Appeared:</b> _____ &nbsp;|&nbsp; <b>Absent:</b> _____", ParagraphStyle("F1", fontName="Helvetica", fontSize=7, leading=8)),
                Paragraph("<b>Subject Teacher Sign:</b> ____________________", ParagraphStyle("F2", fontName="Helvetica", fontSize=7, leading=8)),
                Paragraph("<b>Examiner / Incharge Sign:</b> ____________________", ParagraphStyle("F3", fontName="Helvetica", fontSize=7, leading=8)),
            ]
        ]
        ftr_table = Table(footer_data, colWidths=[190, 180, 180])
        ftr_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#475569")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(ftr_table)

        # Instructions note
        instr_text = (
            "<b>Important Instructions:</b> "
            "1. Write one digit per box clearly in blue/black ballpoint pen. "
            "2. In absent cases, leave digit boxes empty and tick [ &#10003; ] in the [ AB ] column. "
            "3. Do not overwrite; if correction is needed, strike out neatly and sign beside it."
        )
        story.append(Spacer(1, 1 * mm))
        story.append(Paragraph(f"<font size=5.5 color='#475569'>{instr_text}</font>", ParagraphStyle("Ins", fontName="Helvetica", leading=7)))

        if page_idx < total_pages - 1:
            story.append(PageBreak())

    # Build PDF with background decorations & corner fiducial marks
    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_sheet_fiducials_and_decorations(c, d, base_token),
        onLaterPages=lambda c, d: _draw_sheet_fiducials_and_decorations(c, d, base_token)
    )
    buffer.seek(0)
    return buffer.getvalue()


def build_class_award_sheets_bundle_pdf(school_class, section=None, term=None):
    """
    Generates a single comprehensive multi-subject booklet PDF containing
    the blank award sheets for ALL subjects of a given Class (and Section).
    """
    import pymupdf

    if term is None:
        term = ExamTerm.objects.filter(session__is_active=True).order_by("display_order", "id").first()

    tests = ExamTest.objects.select_related("subject", "school_class", "term").filter(
        school_class=school_class,
        term=term
    ).order_by("subject__display_order", "subject__name")

    if not tests.exists():
        raise ValueError(f"No exam tests found for {school_class.name} in term {term.name if term else 'N/A'}")

    qs = Student.objects.filter(is_active=True, current_class=school_class)
    if section:
        qs = qs.filter(current_section=section)
    students = list(qs.order_by("roll_no", "legacy_sid", "full_name"))

    combined_doc = pymupdf.open()
    for test in tests:
        test_pdf_bytes = build_award_sheet_pdf(test, section=section, students=students)
        t_doc = pymupdf.open(stream=test_pdf_bytes, filetype="pdf")
        combined_doc.insert_pdf(t_doc)

    out_bytes = combined_doc.tobytes()
    combined_doc.close()
    return out_bytes
