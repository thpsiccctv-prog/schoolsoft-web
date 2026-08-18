import os

pdf_path = r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\core\pdf.py'
with open(pdf_path, 'r', encoding='utf-8') as f:
    content = f.read()

feeder_pdf_func = '''

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
'''

if "def build_feeder_school_statement_pdf" not in content:
    with open(pdf_path, 'a', encoding='utf-8') as f:
        f.write(feeder_pdf_func)
    print("build_feeder_school_statement_pdf appended to core/pdf.py successfully!")
else:
    print("Function already present in core/pdf.py")
