from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_fee_receipt_pdf(receipt, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
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
        fontSize=18,
        leading=22,
        alignment=0, # Left align
        textColor=brand_color,
        fontName="Helvetica-Bold",
        spaceAfter=2 * mm,
    )
    small_style = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748b"),
    )
    badge_style = ParagraphStyle(
        "Badge",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        textColor=brand_color,
        backColor=colors.HexColor("#ecfdf5"),
        alignment=0,
        spaceBefore=4 * mm,
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
            [Paragraph(f"<b>Receipt No.</b><br/><font size=16>{receipt.receipt_no}</font>", 
                      ParagraphStyle("RNo", alignment=2, leading=20, textColor=text_color))]
        ]
    ]
    header_table = Table(header_data, colWidths=[110 * mm, 70 * mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('LINEBELOW', (0,0), (-1,-1), 1.5, border_color),
        ('BOTTOMPADDING', (0,0), (-1,-1), 15),
    ]))
    
    story.extend([header_table, Spacer(1, 8 * mm)])

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
    meta_table = Table(meta, colWidths=[35 * mm, 60 * mm, 30 * mm, 55 * mm])
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
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([meta_table, Spacer(1, 8 * mm)])

    line_rows = [["Fee Head Description", "Amount (Rs.)"]]
    for line in receipt.lines.select_related("fee_head").all():
        line_rows.append([line.fee_head.name, money(line.amount)])

    # Spacer row before totals
    line_rows.append(["", ""])
    
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

    fee_table = Table(line_rows, colWidths=[130 * mm, 50 * mm], repeatRows=1)
    
    ts = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, border_color),
        
        # Body Lines
        ("LINEBELOW", (0, 1), (-1, total_start_idx-2), 0.5, colors.HexColor("#e2e8f0")),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 1), (-1, total_start_idx-2), text_color),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        
        # Totals Section
        ("FONTNAME", (0, total_start_idx), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, total_start_idx), (-1, -1), colors.HexColor("#475569")),
        
        # Net Payable Row
        ("BACKGROUND", (0, net_idx), (-1, net_idx), light_bg),
        ("TEXTCOLOR", (0, net_idx), (-1, net_idx), text_color),
        ("LINEABOVE", (0, net_idx), (-1, net_idx), 1, border_color),
        ("LINEBELOW", (0, net_idx), (-1, net_idx), 1, border_color),
        ("FONTSIZE", (0, net_idx), (-1, net_idx), 11),
    ]
    
    if due_idx:
        ts.append(("TEXTCOLOR", (0, due_idx), (-1, due_idx), colors.HexColor("#dc2626")))
        
    fee_table.setStyle(TableStyle(ts))
    story.append(fee_table)

    if receipt.remarks:
        story.extend([Spacer(1, 5 * mm), Paragraph(f"<i>Remarks: {receipt.remarks}</i>", small_style)])

    story.extend(
        [
            Spacer(1, 25 * mm),
            Table(
                [["Cashier's Signature", "Parent / Guardian"]],
                colWidths=[70 * mm, 70 * mm],
                style=TableStyle(
                    [
                        ("LINEABOVE", (0, 0), (0, 0), 1, border_color),
                        ("LINEABOVE", (1, 0), (1, 0), 1, border_color),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#64748b")),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ]
                ),
            ),
        ]
    )

    # Add Watermark callback
    def add_watermark(canvas, doc):
        canvas.saveState()
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
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Title"],
        fontSize=15,
        leading=18,
        alignment=1,
        spaceAfter=1 * mm,
    )
    small_style = ParagraphStyle(
        "DocSmall",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=1,
    )
    heading_style = ParagraphStyle(
        "DocHeading",
        parent=styles["Normal"],
        fontSize=12,
        leading=15,
        alignment=1,
        spaceBefore=3 * mm,
        spaceAfter=4 * mm,
    )

    school_name = school_profile.name if school_profile else "SchoolSoft Modernization"
    story.append(Paragraph(school_name, title_style))
    if school_profile and school_profile.address:
        story.append(Paragraph(school_profile.address, small_style))
    contact_parts = []
    if school_profile and school_profile.phone:
        contact_parts.append(f"Phone: {school_profile.phone}")
    if school_profile and school_profile.email:
        contact_parts.append(f"Email: {school_profile.email}")
    if contact_parts:
        story.append(Paragraph(" | ".join(contact_parts), small_style))
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


def build_transfer_certificate_pdf(tc, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Transfer Certificate - {tc.tc_number}",
    )
    styles = getSampleStyleSheet()
    story = []
    _school_header(story, school_profile, "TRANSFER CERTIFICATE", styles)

    body_style = ParagraphStyle(
        "TcBody",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=17,
        spaceAfter=3 * mm,
    )

    student = tc.student
    class_label = tc.last_class_studied.name if tc.last_class_studied else (student.current_class.name if student.current_class else "")
    if tc.last_section:
        class_label = f"{class_label}-{tc.last_section}" if class_label else tc.last_section

    rows = [
        ["TC No.", tc.tc_number, "Issue Date", tc.issue_date.strftime("%d-%m-%Y")],
        ["Student Name", student.full_name, "SID / Admission No.", f"{student.legacy_sid or ''} / {student.admission_no or ''}"],
        ["Father's Name", student.father_name or "", "Mother's Name", student.mother_name or ""],
        ["Date of Birth", student.date_of_birth.strftime("%d-%m-%Y") if student.date_of_birth else "", "Last Class Studied", class_label],
        ["Date of Leaving", tc.date_of_leaving.strftime("%d-%m-%Y") if tc.date_of_leaving else "", "Reason for Leaving", tc.reason_for_leaving or ""],
        ["Conduct", tc.get_conduct_display(), "General Progress", tc.get_general_progress_display()],
        [
            "Attendance",
            f"{tc.days_present or ''} / {tc.total_working_days or ''}" if (tc.days_present or tc.total_working_days) else "",
            "Fees Paid Upto",
            tc.fees_paid_upto or "",
        ],
        [
            "Qualified for Promotion",
            "Yes" if tc.qualified_for_promotion else "No",
            "Promoted To",
            tc.promoted_to_class or "",
        ],
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
    story.extend([table, Spacer(1, 5 * mm)])

    if tc.remarks:
        story.append(Paragraph(f"Remarks: {tc.remarks}", body_style))

    story.extend(
        [
            Spacer(1, 22 * mm),
            Table(
                [["Class Teacher", "Principal / Headmaster"]],
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


def build_character_certificate_pdf(student, school_profile=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Character Certificate - {student.full_name}",
    )
    styles = getSampleStyleSheet()
    story = []
    _school_header(story, school_profile, "CHARACTER CERTIFICATE", styles)

    body_style = ParagraphStyle(
        "CcBody",
        parent=styles["Normal"],
        fontSize=11.5,
        leading=20,
        spaceAfter=4 * mm,
        firstLineIndent=8 * mm,
    )

    class_label = student.current_class.name if student.current_class else ""
    if student.current_section:
        class_label = f"{class_label}-{student.current_section.name}" if class_label else student.current_section.name

    father_bit = f" S/o. / D/o. {student.father_name}" if student.father_name else ""
    text = (
        f"This is to certify that <b>{student.full_name}</b>{father_bit}, "
        f"Admission No. <b>{student.admission_no or '-'}</b>, is / was a bona fide student of this school, "
        f"studying in Class <b>{class_label or '-'}</b>."
    )
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(text, body_style))
    story.append(
        Paragraph(
            "During the period of his/her stay in this institution, his/her character and conduct have been found to be good.",
            body_style,
        )
    )
    story.append(Paragraph("We wish him/her success in future endeavours.", body_style))

    story.extend(
        [
            Spacer(1, 24 * mm),
            Table(
                [["Date: " + timezone_today(), "Principal / Headmaster"]],
                colWidths=[80 * mm, 80 * mm],
                style=TableStyle(
                    [
                        ("LINEABOVE", (1, 0), (1, 0), 0.5, colors.black),
                        ("ALIGN", (0, 0), (0, 0), "LEFT"),
                        ("ALIGN", (1, 0), (1, 0), "CENTER"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ]
                ),
            ),
        ]
    )

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
    _school_header(story, school_profile, f"REPORT CARD - {term.name.upper()}", styles)

    class_label = student.current_class.name if student.current_class else ""
    if student.current_section:
        class_label = f"{class_label}-{student.current_section.name}" if class_label else student.current_section.name

    meta_rows = [
        ["Student Name", student.full_name, "SID", student.legacy_sid or ""],
        ["Class", class_label, "Roll No.", student.roll_no or ""],
        ["Father's Name", student.father_name or "", "Session", term.session.name],
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

    rows = [["Subject", "Max Marks", "Marks Obtained", "Grade"]]
    total_max = Decimal("0.00")
    total_obtained = Decimal("0.00")
    for mark in exam_marks:
        obtained_label = "AB" if mark.is_absent else money(mark.marks_obtained or Decimal("0.00"))
        rows.append(
            [
                mark.exam_test.subject.name,
                money(mark.exam_test.max_marks),
                obtained_label,
                mark.grade,
            ]
        )
        total_max += mark.exam_test.max_marks
        if not mark.is_absent and mark.marks_obtained is not None:
            total_obtained += mark.marks_obtained

    overall_pct = (total_obtained / total_max * Decimal("100")) if total_max else Decimal("0.00")
    rows.append(["Total", money(total_max), money(total_obtained), f"{overall_pct:.1f}%"])

    marks_table = Table(rows, colWidths=[70 * mm, 35 * mm, 40 * mm, 35 * mm], repeatRows=1)
    total_row = len(rows) - 1
    marks_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8d0dc")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, total_row), (-1, total_row), "Helvetica-Bold"),
                ("BACKGROUND", (0, total_row), (-1, total_row), colors.HexColor("#f8fafc")),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(marks_table)

    story.extend(
        [
            Spacer(1, 20 * mm),
            Table(
                [["Class Teacher", "Principal"]],
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
