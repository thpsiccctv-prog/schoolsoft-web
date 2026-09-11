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
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle
)

from core.models import ExamTest, SchoolClass, Section, Student, ExamTerm
from core.pdf import _devanagari_flowable


# Page geometry (A4: 595.27 x 841.89 pt)
PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT_MARGIN = 8 * mm   # ~22.68 pt
RIGHT_MARGIN = 8 * mm
TOP_MARGIN = 7 * mm
BOTTOM_MARGIN = 7 * mm
USABLE_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN  # ~550 pt

STUDENTS_PER_PAGE = 26  # Generous row height (~20-21 pt) for neat handwriting


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

    # 4 Corner Fiducial crosses [+]
    # Inset 5mm from page edges
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
    canvas.setFont("Helvetica-Bold", 7)
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
    term = exam_test.term
    subject = exam_test.subject

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

    styles = getSampleStyleSheet()

    header_title_style = ParagraphStyle(
        "SheetHeaderTitle",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        alignment=1,  # Center
        textColor=colors.HexColor("#0F172A"),
    )
    sub_title_style = ParagraphStyle(
        "SheetSubTitle",
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=11.5,
        alignment=1,
        textColor=colors.HexColor("#1E3A8A"),
    )
    sheet_badge_style = ParagraphStyle(
        "SheetBadge",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=9.5,
        alignment=1,
        textColor=colors.HexColor("#097969"),
    )
    cell_bold_style = ParagraphStyle(
        "CellBold",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#0F172A"),
    )
    cell_regular_style = ParagraphStyle(
        "CellReg",
        fontName="Helvetica",
        fontSize=7.2,
        leading=8.5,
        textColor=colors.HexColor("#1E293B"),
    )
    cell_hindi_style = ParagraphStyle(
        "CellHindi",
        fontName="NotoSansDevanagari",
        fontSize=7.2,
        leading=8.5,
        textColor=colors.HexColor("#0F172A"),
    )
    col_hdr_style = ParagraphStyle(
        "ColHdr",
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8,
        alignment=1,
        textColor=colors.HexColor("#FFFFFF"),
    )

    has_practical = (exam_test.practical_max_marks and exam_test.practical_max_marks > Decimal("0.00"))

    story = []

    for page_idx in range(total_pages):
        page_no = page_idx + 1
        start_i = page_idx * STUDENTS_PER_PAGE
        end_i = min(start_i + STUDENTS_PER_PAGE, total_students)
        page_students = students[start_i:end_i]

        sec_code = section.name if section else "ALL"
        sheet_token = f"QEX2627-C{school_class.id}-S{sec_code}-T{exam_test.id}-P{page_no}OF{total_pages}"

        # 1. School Header Banner
        sub_title_cell = _make_bilingual_cell("QUARTERLY EXAMINATION 2026-27 — AWARD LIST", "त्रैमासिक परीक्षा 2026-27 (अंक प्रविष्टि पत्रक)", font_size=9.5, bold_en=True)
        header_data = [
            [
                Paragraph("<b>T H P S INTERMEDIATE COLLEGE</b>", header_title_style),
            ],
            [
                sub_title_cell,
            ],
            [
                Paragraph(f"<b>[ SHEET-ID: {sheet_token} ]</b>", sheet_badge_style),
            ],
        ]
        hdr_table = Table(header_data, colWidths=[USABLE_WIDTH])
        hdr_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(hdr_table)
        story.append(Spacer(1, 1.5 * mm))

        # 2. Metadata Strip (Class, Section, Subject, Max/Pass Marks, Page)
        sec_label = f"Section: <b>{section.name}</b>" if section else "Section: <b>All</b>"
        pr_label = f" | Pr: <b>{int(exam_test.practical_max_marks)}</b>" if has_practical else ""
        sub_display_name = subject.name.split("(")[0].strip() if "(" in subject.name else subject.name
        meta_html = (
            f"Class: <b>{school_class.name}</b> &nbsp;|&nbsp; {sec_label} &nbsp;|&nbsp; "
            f"Subject: <b>{sub_display_name}</b> &nbsp;|&nbsp; "
            f"Max Marks: <b>{int(exam_test.max_marks)}</b> (Th: <b>{int(exam_test.theory_max_marks)}</b>{pr_label}) &nbsp;|&nbsp; "
            f"Pass: <b>{int(exam_test.pass_marks)}</b> &nbsp;|&nbsp; "
            f"Page: <b>{page_no} / {total_pages}</b>"
        )
        meta_para = Paragraph(meta_html, ParagraphStyle("MetaStrip", fontName="Helvetica", fontSize=8, leading=10, alignment=1, textColor=colors.HexColor("#0F172A")))
        meta_table = Table([[meta_para]], colWidths=[USABLE_WIDTH])
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#94A3B8")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 1.5 * mm))

        # 3. Main Marks Grid Table
        # Columns:
        # S.No(22), Roll(30), Adm(38), Student Name(128), Father Name(102), Theory(48), Practical(48), Total(50), AB(34), Sign(50)
        # Sum = 22 + 30 + 38 + 128 + 102 + 48 + 48 + 50 + 34 + 50 = 550 pt
        col_widths = [22, 30, 38, 128, 102, 48, 48, 50, 34, 50]

        th_header = Paragraph(f"<b>THEORY</b><br/><font size=5.5 color='#94A3B8'>Max {int(exam_test.theory_max_marks)}</font>", col_hdr_style)
        if has_practical:
            pr_header = Paragraph(f"<b>PRACTICAL</b><br/><font size=5.5 color='#94A3B8'>Max {int(exam_test.practical_max_marks)}</font>", col_hdr_style)
        else:
            pr_header = Paragraph(f"<b>PRACTICAL</b><br/><font size=5.5 color='#94A3B8'>N/A (0)</font>", col_hdr_style)

        tot_header = Paragraph(f"<b>TOTAL</b><br/><font size=5.5 color='#94A3B8'>Max {int(exam_test.max_marks)}</font>", col_hdr_style)

        table_rows = [
            [
                Paragraph("<b>S.N.</b>", col_hdr_style),
                Paragraph("<b>ROLL</b>", col_hdr_style),
                Paragraph("<b>ADM/SID</b>", col_hdr_style),
                Paragraph("<b>STUDENT NAME</b>", col_hdr_style),
                Paragraph("<b>FATHER'S NAME</b>", col_hdr_style),
                th_header,
                pr_header,
                tot_header,
                Paragraph("<b>ABSENT<br/>[ AB ]</b>", col_hdr_style),
                Paragraph("<b>TEACHER<br/>SIGN</b>", col_hdr_style),
            ]
        ]

        tstyles = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, 0), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 2.5),
            ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#334155")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#64748B")),
        ]

        for row_i, student in enumerate(page_students):
            curr_row_idx = row_i + 1
            s_no = str(start_i + row_i + 1)
            roll_str = str(student.roll_no) if student.roll_no else "-"
            adm_str = str(student.admission_no or student.legacy_sid or "")

            # Student name display: Hindi (if present) + English
            name_en = student.full_name
            name_hi = getattr(student, "full_name_hindi", "") or ""
            name_flowable = _make_bilingual_cell(name_en, name_hi, font_size=7.2, bold_en=True)

            # Father name display
            father_en = student.father_name or ""
            father_hi = getattr(student, "father_name_hindi", "") or ""
            father_flowable = _make_bilingual_cell(father_en, father_hi, font_size=6.8, bold_en=False)

            # Practical cell: if 0, hatch/gray out
            pr_content = "" if has_practical else Paragraph("<font color='#94A3B8'>&mdash;</font>", ParagraphStyle("NA", alignment=1))

            table_rows.append([
                Paragraph(s_no, ParagraphStyle("SN", fontName="Helvetica-Bold", fontSize=7.5, alignment=1)),
                Paragraph(roll_str, ParagraphStyle("RL", fontName="Helvetica-Bold", fontSize=7.5, alignment=1)),
                Paragraph(adm_str, ParagraphStyle("AD", fontName="Helvetica", fontSize=7, alignment=1)),
                name_flowable,
                father_flowable,
                "",  # Theory blank box for teacher handwriting
                pr_content,  # Practical blank box (or dash)
                "",  # Total blank box for teacher handwriting
                Paragraph("<font size=8 color='#94A3B8'>[ &nbsp; ]</font>", ParagraphStyle("AB", alignment=1)),
                "",  # Sign
            ])

            # Alternating background
            if row_i % 2 == 1:
                tstyles.append(("BACKGROUND", (0, curr_row_idx), (-1, curr_row_idx), colors.HexColor("#F8FAFC")))

            # Center alignment for numerical/code columns
            tstyles.append(("ALIGN", (0, curr_row_idx), (2, curr_row_idx), "CENTER"))
            tstyles.append(("ALIGN", (5, curr_row_idx), (9, curr_row_idx), "CENTER"))
            tstyles.append(("VALIGN", (0, curr_row_idx), (-1, curr_row_idx), "MIDDLE"))
            tstyles.append(("TOPPADDING", (0, curr_row_idx), (-1, curr_row_idx), 2.2))
            tstyles.append(("BOTTOMPADDING", (0, curr_row_idx), (-1, curr_row_idx), 2.2))

            # If no practical, tint practical column gray
            if not has_practical:
                tstyles.append(("BACKGROUND", (6, curr_row_idx), (6, curr_row_idx), colors.HexColor("#E2E8F0")))

        marks_table = Table(table_rows, colWidths=col_widths)
        marks_table.setStyle(TableStyle(tstyles))
        story.append(marks_table)
        story.append(Spacer(1, 2 * mm))

        # 4. Teacher Summary & Verification Footer
        footer_data = [
            [
                Paragraph(f"<b>Total Students:</b> {total_students}", cell_bold_style),
                Paragraph("<b>Appeared:</b> _______", cell_bold_style),
                Paragraph("<b>Absent:</b> _______", cell_bold_style),
                Paragraph("<b>Teacher Name:</b> ____________________", cell_bold_style),
                Paragraph("<b>Sign & Date:</b> ______________", cell_bold_style),
            ]
        ]
        ftr_table = Table(footer_data, colWidths=[85, 75, 75, 185, 130])
        ftr_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#475569")),
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
            "<b>Instructions for Teacher:</b> "
            "1. Write marks clearly using blue/black ballpoint pen. "
            "2. Write both Theory & Practical and calculate Total for double-entry validation. "
            "3. Tick [ &#10003; ] in the [ AB ] column for absent students."
        )
        story.append(Spacer(1, 1 * mm))
        story.append(Paragraph(f"<font size=6 color='#475569'>{instr_text}</font>", ParagraphStyle("Inst", fontName="Helvetica", leading=7.5)))

        if page_idx < total_pages - 1:
            story.append(PageBreak())

    # Build PDF with background decorations & corner fiducial marks
    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_sheet_fiducials_and_decorations(c, d, f"QEX2627-C{school_class.id}-T{exam_test.id}"),
        onLaterPages=lambda c, d: _draw_sheet_fiducials_and_decorations(c, d, f"QEX2627-C{school_class.id}-T{exam_test.id}")
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
