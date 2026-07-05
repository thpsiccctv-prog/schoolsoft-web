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
    class_label = ""
    if student.current_class:
        class_label = student.current_class.name
    if student.current_section:
        class_label = f"{class_label}-{student.current_section.name}" if class_label else student.current_section.name

    month_label = receipt.from_month
    if receipt.to_month and receipt.to_month != receipt.from_month:
        month_label = f"{receipt.from_month} to {receipt.to_month}"

    meta = [
        ["Student Name", student.full_name, "Date", receipt.receipt_date.strftime("%d-%m-%Y")],
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
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Transfer Certificate - {tc.tc_number}",
    )
    styles = getSampleStyleSheet()
    story = []

    # Fonts
    brand_color = colors.HexColor("#0f766e")
    title_style = ParagraphStyle(
        "TcTitle", parent=styles["Title"], fontSize=16, leading=20, alignment=1, textColor=brand_color, fontName="Helvetica-Bold", spaceAfter=2*mm
    )
    hindi_style = ParagraphStyle(
        "TcHindi", parent=styles["Normal"], fontName="NotoSansDevanagari", fontSize=14, alignment=1, spaceAfter=4*mm
    )
    small_style = ParagraphStyle(
        "TcSmall", parent=styles["Normal"], fontSize=9, leading=12, alignment=1
    )
    field_style = ParagraphStyle(
        "TcField", parent=styles["Normal"], fontName="NotoSansDevanagari", fontSize=9, leading=14
    )
    value_style = ParagraphStyle(
        "TcValue", parent=styles["Normal"], fontSize=9, leading=14, fontName="Helvetica-Bold"
    )

    school_name = school_profile.name if school_profile else "SCHOOLSOFT"
    story.append(Paragraph(school_name.upper(), title_style))
    if school_profile and school_profile.address_line1:
        addr = f"{school_profile.address_line1}, {school_profile.address_line2}".strip(", ")
        story.append(Paragraph(addr, small_style))
    
    contact_parts = []
    if school_profile and school_profile.phone: contact_parts.append(f"Ph: {school_profile.phone}")
    if school_profile and school_profile.email: contact_parts.append(f"Email: {school_profile.email}")
    if school_profile and getattr(school_profile, 'udise_code', None): contact_parts.append(f"UDISE: {school_profile.udise_code}")
    if contact_parts:
        story.append(Paragraph(" | ".join(contact_parts), small_style))
    
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("TRANSFER CERTIFICATE", title_style))
    story.append(Paragraph("स्थानान्तरण प्रमाण-पत्र", hindi_style))

    student = tc.student
    
    top_meta = [
        [f"Book No. / पुस्तक क्र.: {tc.book_no}", f"S.R. No. / छात्र पंजीका क्र.: {tc.sr_no}", f"Admission No. / प्रवेश क्र.: {student.admission_no}"],
        [f"TC No. / टी.सी. क्र.: {tc.tc_number}", f"PEN: {getattr(student, 'pen_number', '')}", f"Affiliation No.: _________"]
    ]
    meta_t = Table(top_meta, colWidths=[60*mm, 60*mm, 60*mm])
    meta_t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "NotoSansDevanagari"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("ALIGN", (0,0), (0,-1), "LEFT"),
        ("ALIGN", (1,0), (1,-1), "CENTER"),
        ("ALIGN", (2,0), (2,-1), "RIGHT"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(meta_t)
    story.append(Spacer(1, 2*mm))

    class_label = tc.last_class_studied.name if tc.last_class_studied else (student.current_class.name if student.current_class else "")
    if tc.last_section: class_label = f"{class_label}-{tc.last_section}" if class_label else tc.last_section
    
    promoted_class = tc.promoted_to_class if getattr(tc, 'qualified_for_promotion', False) else "N/A"

    fields = [
        ("1. Name of the Pupil / विद्यार्थी का नाम", student.full_name),
        ("2. Mother's Name / माता का नाम", student.mother_name or ""),
        ("3. Father's/Guardian's Name / पिता/अभिभावक का नाम", student.father_name or ""),
        ("4. Nationality / राष्ट्रीयता", getattr(student, 'nationality', 'Indian')),
        ("5. Whether belongs to SC/ST/OBC / क्या अनुसूचित जाति/जनजाति/अन्य पिछड़े वर्ग से हैं", getattr(student, 'category', '')),
        ("6. Date of first admission in the School with class / विद्यालय में प्रवेश की तिथि व कक्षा", f"{student.admission_date.strftime('%d-%m-%Y') if student.admission_date else ''} - Class {student.current_class.name if student.current_class else ''}"),
        ("7. Date of Birth / जन्म तिथि", student.date_of_birth.strftime('%d-%m-%Y') if student.date_of_birth else ""),
        ("   (in words / शब्दों में)", date_to_words(student.date_of_birth)),
        ("8. Class in which the pupil last studied / वह कक्षा जिसमें विद्यार्थी ने अंतिम बार अध्ययन किया", class_label),
        ("9. School/Board Annual Exam last taken / अंतिम विद्यालय/बोर्ड वार्षिक परीक्षा", ""),
        ("10. Whether failed, if so once/twice / क्या कभी अनुत्तीर्ण रहे", "Yes" if getattr(tc, 'whether_failed', False) else "No"),
        ("11. Subjects Studied / विषय जिनका अध्ययन किया", getattr(tc, 'subjects_offered', '')),
        ("12. Whether qualified for promotion / क्या पदोन्नति के अधिकारी हैं", f"Yes - {promoted_class}" if getattr(tc, 'qualified_for_promotion', False) else "No"),
        ("13. Month upto which school dues paid / वह माह जहाँ तक शुल्क जमा है", tc.fees_paid_upto or ""),
        ("14. Any fee concession availed of / क्या किसी शुल्क रियायत का लाभ उठाया गया", getattr(tc, 'fee_concession_nature', '') or "No"),
        ("15. Total No. of working days / कुल कार्य दिवस", str(tc.total_working_days or '')),
        ("16. Total working days present / विद्यार्थी की कुल उपस्थिति", str(tc.days_present or '')),
        ("17. Whether NCC Cadet/Scout / क्या एनसीसी कैडेट / स्काउट हैं", getattr(tc, 'ncc_scout', '') or "No"),
        ("18. Games played or extra-curricular activities / खेल-कूद व गतिविधियाँ", ""),
        ("19. General conduct / सामान्य आचरण", tc.get_conduct_display()),
        ("20. Date of application for certificate / आवेदन की तिथि", ""),
        ("21. Date of issue of certificate / प्रमाण-पत्र जारी करने की तिथि", tc.issue_date.strftime('%d-%m-%Y') if tc.issue_date else ""),
        ("22. Reasons for leaving the school / विद्यालय छोड़ने का कारण", tc.reason_for_leaving or ""),
        ("23. Any other remarks / कोई अन्य टिप्पणी", tc.remarks or "")
    ]

    table_data = []
    for label, val in fields:
        table_data.append([Paragraph(label, field_style), Paragraph(val, value_style)])
        
    t = Table(table_data, colWidths=[110*mm, 70*mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("LINEBELOW", (1,0), (1,-1), 0.5, colors.HexColor("#cbd5e1")),
    ]))
    story.append(t)
    
    story.append(Spacer(1, 15*mm))
    
    sig_data = [
        ["Signature of Class Teacher", "Checked by", "Principal\n(Seal)"]
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
        c_name = row.student.current_class.name if row.student.current_class else ""
        s_name = row.student.current_section.name if row.student.current_section else ""
        class_str = f"{c_name}-{s_name}" if s_name else c_name
        
        table_data.append([
            row.receipt_date.strftime("%d-%m-%Y"),
            row.receipt_no,
            str(row.student.legacy_sid),
            row.student.full_name[:20],
            class_str,
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
        ["Gross Pay", money(payment.gross_pay), "Total Deductions", money(payment.total_deductions)],
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

    document.build(story)
    buffer.seek(0)
    return buffer.getvalue()
