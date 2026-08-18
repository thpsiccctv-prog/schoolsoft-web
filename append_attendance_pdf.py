import calendar

attendance_pdf_code = '''

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
            Paragraph(
                f"<b><font size='10' color='#0F172A'>STUDENT MONTHLY ATTENDANCE REGISTER (छात्र मासिक उपस्थिति पंजिका)</font></b>",
                styles["Normal"],
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
'''

pdf_path = r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\core\pdf.py'
with open(pdf_path, 'r', encoding='utf-8') as f:
    content = f.read()

if "def build_attendance_register_pdf" not in content:
    with open(pdf_path, 'a', encoding='utf-8') as f:
        f.write(attendance_pdf_code)
    print("build_attendance_register_pdf appended to core/pdf.py successfully!")
else:
    print("Function already present in core/pdf.py")
