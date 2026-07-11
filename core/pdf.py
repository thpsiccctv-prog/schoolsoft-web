from decimal import Decimal
import os
from io import BytesIO

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

try:
    _reg_path = os.path.join(settings.BASE_DIR, 'static', 'core', 'fonts', 'NotoSansDevanagari-Regular.ttf')
    _bold_path = os.path.join(settings.BASE_DIR, 'static', 'core', 'fonts', 'NotoSansDevanagari-Bold.ttf')
    pdfmetrics.registerFont(TTFont('NotoSansDevanagari', _reg_path))
    pdfmetrics.registerFont(TTFont('NotoSansDevanagari-Bold', _bold_path))
    pdfmetrics.registerFontFamily('NotoSansDevanagari', normal='NotoSansDevanagari', bold='NotoSansDevanagari-Bold')
except Exception:
    pass


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
        rightMargin=11 * mm,
        leftMargin=11 * mm,
        topMargin=9 * mm,
        bottomMargin=9 * mm,
        title=f"Transfer Certificate - {tc.tc_number}",
    )
    styles = getSampleStyleSheet()
    story = []

    # Fonts
    brand_color = colors.HexColor("#0f766e")
    title_style = ParagraphStyle(
        "TcTitle", parent=styles["Title"], fontSize=16, leading=20, alignment=1, textColor=brand_color, fontName="Helvetica-Bold", spaceAfter=2*mm
    )
    small_style = ParagraphStyle(
        "TcSmall", parent=styles["Normal"], fontSize=8, leading=10, alignment=1
    )
    field_style = ParagraphStyle(
        "TcField", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=10
    )
    value_style = ParagraphStyle(
        "TcValue", parent=styles["Normal"], fontSize=8, leading=10, fontName="Helvetica-Bold"
    )

    school_name = school_profile.name if school_profile else "SCHOOLSOFT"
    logo_path = os.path.join(settings.BASE_DIR, "static", "core", "school_logo.png")
    school_heading = [Paragraph(school_name.upper(), title_style)]
    if school_profile and school_profile.address_line1:
        addr = f"{school_profile.address_line1}, {school_profile.address_line2}".strip(", ")
        school_heading.append(Paragraph(addr, small_style))
    
    contact_parts = []
    if school_profile and school_profile.phone: contact_parts.append(f"Ph: {school_profile.phone}")
    if school_profile and school_profile.email: contact_parts.append(f"Email: {school_profile.email}")
    if school_profile and getattr(school_profile, 'udise_code', None): contact_parts.append(f"UDISE: {school_profile.udise_code}")
    if contact_parts:
        school_heading.append(Paragraph(" | ".join(contact_parts), small_style))
    logo = Image(logo_path, 20 * mm, 20 * mm) if os.path.exists(logo_path) else ""
    header = Table([[logo, school_heading, ""]], colWidths=[25 * mm, 139 * mm, 25 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "CENTER")]))
    story.append(header)
    story.append(Table([[""]], colWidths=[189 * mm], rowHeights=[1 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#b58a2a"))])))
    
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("TRANSFER CERTIFICATE", title_style))

    student = tc.student

    top_meta = [
        [f"Book No.: {tc.book_no}", f"S.R. No.: {student.scholar_register_no or tc.sr_no}", f"Admission No.: {student.admission_no}"],
        [f"TC No.: {tc.tc_number}", f"PEN: {getattr(student, 'pen_number', '')}", f"Medium: {getattr(school_profile, 'medium', '') or 'English'}"],
        [f"UDISE: {getattr(school_profile, 'udise_code', '')}", f"Recognition: {getattr(school_profile, 'recognition_no', '') or 'Not entered'}", f"Recognized up to: {getattr(school_profile, 'recognized_upto', '') or 'Not entered'}"]
    ]
    meta_t = Table(top_meta, colWidths=[63*mm, 63*mm, 63*mm])
    meta_t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("ALIGN", (0,0), (0,-1), "LEFT"),
        ("ALIGN", (1,0), (1,-1), "CENTER"),
        ("ALIGN", (2,0), (2,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#9aa5b1")),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3), ("TOPPADDING", (0,0), (-1,-1), 3),
    ]))
    story.append(meta_t)
    story.append(Spacer(1, 2*mm))

    class_label = tc.last_class_studied.name if tc.last_class_studied else (student.current_class.name if student.current_class else "")
    if tc.last_section: class_label = f"{class_label}-{tc.last_section}" if class_label else tc.last_section

    promoted_class = tc.promoted_to_class if getattr(tc, 'qualified_for_promotion', False) else "N/A"

    fields = [
        ("1. Name of the Pupil", student.full_name),
        ("2. Mother's Name", student.mother_name or ""),
        ("3. Father's/Guardian's Name", student.father_name or ""),
        ("4. Nationality", getattr(student, 'nationality', 'Indian')),
        ("5. Whether belongs to SC/ST/OBC", getattr(student, 'category', '')),
        ("6. Date of first admission in the School with class", f"{student.admission_date.strftime('%d-%m-%Y') if student.admission_date else ''} - Class {student.current_class.name if student.current_class else ''}"),
        ("7. Date of Birth", student.date_of_birth.strftime('%d-%m-%Y') if student.date_of_birth else ""),
        ("   (in words)", date_to_words(student.date_of_birth)),
        ("8. Class in which the pupil last studied", class_label),
        ("9. School/Board Annual Exam last taken with result", tc.annual_exam_result or ""),
        ("10. Whether failed, if so once/twice", "Yes" if getattr(tc, 'whether_failed', False) else "No"),
        ("11. Subjects Studied", getattr(tc, 'subjects_offered', '')),
        ("12. Whether qualified for promotion", f"Yes - {promoted_class}" if getattr(tc, 'qualified_for_promotion', False) else "No"),
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
        
    t = Table(table_data, colWidths=[105*mm, 84*mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("TOPPADDING", (0,0), (-1,-1), 2),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#9aa5b1")),
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#f7f8f8")),
    ]))
    story.append(t)
    
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("CERTIFIED that the above entries have been verified with the Admission/Scholar Register and school records and are correct.", small_style))
    story.append(Spacer(1, 8*mm))
    
    sig_data = [
        ["Prepared by\n(Name & Designation)", "Checked by\n(Name & Designation)", "Head Teacher / Principal\n(Signature with official seal)"]
    ]
    sig_t = Table(sig_data, colWidths=[60*mm, 60*mm, 60*mm])
    sig_t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (0,0), (0,0), "LEFT"),
        ("ALIGN", (1,0), (1,0), "CENTER"),
        ("ALIGN", (2,0), (2,0), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "BOTTOM"),
    ]))
    story.append(sig_t)
    story.append(Spacer(1, 3*mm))
    counter = Table([
        ["COUNTERSIGN / OFFICE VERIFICATION (only where required by the competent authority)"],
        ["Verified with original Scholar Register. Signature: ______________  Name/Designation: ______________  Date: ________  Office Seal"],
    ], colWidths=[189*mm])
    counter.setStyle(TableStyle([("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#17202a")), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f3f6f5")), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7), ("ALIGN", (0,0), (-1,-1), "CENTER"), ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3)]))
    story.append(counter)

    document.build(story)
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
    styles = getSampleStyleSheet()
    story = []

    brand_color = colors.HexColor("#0f766e")
    title_style = ParagraphStyle(
        "SrTitle", parent=styles["Title"], fontSize=14, leading=17, alignment=1,
        textColor=brand_color, fontName="Helvetica-Bold", spaceAfter=1 * mm,
    )
    subtitle_style = ParagraphStyle("SrSubtitle", parent=styles["Normal"], fontSize=9, leading=11, alignment=1)
    small_style = ParagraphStyle("SrSmall", parent=styles["Normal"], fontSize=8, leading=10, alignment=1)
    field_style = ParagraphStyle("SrField", parent=styles["Normal"], fontName="Helvetica", fontSize=7.5, leading=9)
    value_style = ParagraphStyle("SrValue", parent=styles["Normal"], fontSize=8.5, leading=10, fontName="Helvetica-Bold")
    note_style = ParagraphStyle("SrNote", parent=styles["Normal"], fontSize=7, leading=9)

    school_name = school_profile.name if school_profile else "SCHOOLSOFT"
    logo_path = os.path.join(settings.BASE_DIR, "static", "core", "school_logo.png")
    school_heading = [Paragraph(school_name.upper(), title_style)]
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
    header = Table([[logo, school_heading, ""]], colWidths=[25 * mm, 139 * mm, 25 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "CENTER")]))
    story.append(header)
    story.append(Table([[""]], colWidths=[189 * mm], rowHeights=[1 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#b58a2a"))])))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("SCHOLAR'S REGISTER &amp; TRANSFER CERTIFICATE FORM", title_style))
    story.append(Paragraph("(Chhatra Patravali tatha Sthanantaran Pramaan-Patra) - Office Copy, Not for Student", subtitle_style))
    story.append(Spacer(1, 3 * mm))

    tc = getattr(student, "transfer_certificate", None)

    top_meta = [[
        f"Admission File No.: {student.admission_no or ''}",
        f"Transfer Certificate No.: {tc.tc_number if tc else ''}",
        f"Register No.: {student.scholar_register_no or ''}",
    ]]
    meta_t = Table(top_meta, colWidths=[63 * mm, 63 * mm, 63 * mm])
    meta_t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9aa5b1")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_t)
    story.append(Spacer(1, 2 * mm))

    caste_religion = " / ".join(part for part in [student.religion, student.caste] if part) or ""
    address = student.address_permanent or student.address_local or ""

    info_rows = [
        [Paragraph("Name of the Scholar", field_style), Paragraph(student.full_name, value_style),
         Paragraph("Nationality", field_style), Paragraph(student.nationality or "Indian", value_style)],
        [Paragraph("Religion / Caste", field_style), Paragraph(caste_religion, value_style),
         Paragraph("Category", field_style), Paragraph(student.category or "", value_style)],
        [Paragraph("Father's Name", field_style), Paragraph(student.father_name or "", value_style),
         Paragraph("Mother's Name", field_style), Paragraph(student.mother_name or "", value_style)],
        [Paragraph("Date of Birth", field_style), Paragraph(student.date_of_birth.strftime("%d-%m-%Y") if student.date_of_birth else "", value_style),
         Paragraph("Date of Birth (in words)", field_style), Paragraph(date_to_words(student.date_of_birth), value_style)],
        [Paragraph("First Admission Date", field_style), Paragraph(student.admission_date.strftime("%d-%m-%Y") if student.admission_date else "", value_style),
         Paragraph("Current Class", field_style), Paragraph(student.current_class.name if student.current_class else "", value_style)],
        [Paragraph("Aadhaar Number", field_style), Paragraph(student.aadhaar_no or "", value_style),
         Paragraph("Last Institution Attended", field_style), Paragraph(student.previous_school_name or "", value_style)],
        [Paragraph("Address", field_style), Paragraph(address, value_style), "", ""],
    ]
    info_t = Table(info_rows, colWidths=[32 * mm, 62 * mm, 32 * mm, 63 * mm])
    info_t.setStyle(TableStyle([
        ("SPAN", (1, 6), (3, 6)),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9aa5b1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f7f8f8")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f7f8f8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(info_t)
    story.append(Spacer(1, 4 * mm))

    tc_class_name = None
    if tc:
        tc_class_name = tc.last_class_studied.name if tc.last_class_studied else (
            student.current_class.name if student.current_class else None
        )

    grid_header = ["Class", "Date of\nAdmission", "Date of\nPromotion", "Date of\nRemoval", "Cause of Removal", "Year", "Conduct", "Work", "Sign."]
    grid_data = [grid_header]
    for cls in _SCHOLAR_REGISTER_CLASS_ROWS:
        row = [cls, "", "", "", "", "", "", "", ""]
        if tc_class_name and cls.upper() == tc_class_name.strip().upper():
            removal_date = tc.struck_off_date or tc.date_of_leaving
            row[3] = removal_date.strftime("%d-%m-%Y") if removal_date else ""
            row[4] = (tc.reason_for_leaving or "")[:28]
            row[5] = tc.issue_date.strftime("%Y") if tc.issue_date else ""
            row[6] = tc.get_conduct_display()
        grid_data.append(row)

    grid_t = Table(
        grid_data,
        colWidths=[13 * mm, 21 * mm, 21 * mm, 21 * mm, 38 * mm, 13 * mm, 20 * mm, 20 * mm, 15 * mm],
        repeatRows=1,
    )
    grid_t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
        ("BACKGROUND", (0, 0), (-1, 0), brand_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(grid_t)
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph(
        "Class-wise admission and promotion history is not tracked in this system, so those cells are intentionally "
        "blank and must be completed from the physical register. If the student has left, only verified removal "
        "details from the Transfer Certificate are printed.",
        note_style,
    ))
    story.append(Paragraph(
        "Note: 1. If the student has studied classes VI to VIII, this should be mentioned in the Work column. "
        "2. For a student leaving any class from IX to X, attendance/lectures should be entered on the back of "
        "this form.",
        note_style,
    ))
    story.append(Spacer(1, 8 * mm))

    cert_t = Table(
        [
            ["I - Certified that the entries as records details of the student have been daily checked from the admission form and that they are complete."],
            ["Head of Institute: ______________________"],
            ["II - Certified that the above student's Register has been posted up to the last of the student's leaving as required by the Department Rules & T.C. Issued."],
            ["Prepared by: ______________________          Date: ____________          Head of Institute: ______________________"],
        ],
        colWidths=[189 * mm],
    )
    cert_t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (0, 1), (0, 1), "RIGHT"),
        ("ALIGN", (0, 3), (0, 3), "RIGHT"),
    ]))
    story.append(cert_t)

    document.build(story)
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
