replacement_pdf_code = '''def _build_fee_receipt_story(receipt, school_profile=None):
    styles = getSampleStyleSheet()
    
    # Premium Styles
    brand_color = colors.HexColor("#0f766e")
    text_color = colors.HexColor("#1e293b")
    light_bg = colors.HexColor("#f8fafc")
    border_color = colors.HexColor("#cbd5e1")
    
    title_style = ParagraphStyle(
        "ReceiptTitle",
        parent=styles["Title"],
        fontSize=12,
        leading=13,
        alignment=0, # Left align
        textColor=brand_color,
        fontName="Helvetica-Bold",
        spaceAfter=1 * mm,
    )
    small_style = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=5.6,
        leading=6.4,
        textColor=colors.HexColor("#64748b"),
    )
    badge_style = ParagraphStyle(
        "Badge",
        parent=styles["Normal"],
        fontSize=6,
        leading=6.8,
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
    
    # Clear, hard-to-miss payment-status badge
    if receipt.is_cancelled:
        status_badge = None
    elif receipt.legacy_due_amount > 0:
        status_badge = Paragraph(
            f"DUE - Rs. {money(receipt.legacy_due_amount)}",
            ParagraphStyle("StatusDue", alignment=2, fontName="Helvetica-Bold", fontSize=8.5,
                          textColor=colors.white, backColor=colors.HexColor("#dc2626"), spaceBefore=2 * mm),
        )
    else:
        status_badge = Paragraph(
            "FULLY PAID",
            ParagraphStyle("StatusPaid", alignment=2, fontName="Helvetica-Bold", fontSize=8.5,
                          textColor=colors.white, backColor=colors.HexColor("#15803d"), spaceBefore=2 * mm),
        )

    receipt_no_cell = [Paragraph(f"<b>Receipt No.</b><br/><font size=11>{receipt.receipt_no}</font>",
                                 ParagraphStyle("RNo", alignment=2, leading=13, textColor=text_color))]
    if status_badge is not None:
        receipt_no_cell.append(status_badge)

    # Header Table (School Info Left, Receipt No Right)
    header_data = [
        [
            [Paragraph(school_name.upper(), title_style),
             Paragraph(school_address, small_style),
             Paragraph(school_contact, small_style),
             Paragraph(" FEE RECEIPT ", badge_style)],
            receipt_no_cell
        ]
    ]
    header_table = Table(header_data, colWidths=[125 * mm, 57 * mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('LINEBELOW', (0,0), (-1,-1), 1.5, border_color),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    
    story.extend([header_table, Spacer(1, 1.5 * mm)])

    student = receipt.student
    class_label = receipt.display_class_section

    month_label = receipt.from_month
    if receipt.to_month and receipt.to_month != receipt.from_month:
        month_label = f"{receipt.from_month} to {receipt.to_month}"

    meta_label_style = ParagraphStyle(
        "ReceiptMetaLabel",
        parent=small_style,
        fontName="Helvetica-Bold",
        fontSize=6.2,
        leading=6.8,
        textColor=colors.HexColor("#475569"),
    )
    meta_value_style = ParagraphStyle(
        "ReceiptMetaValue",
        parent=small_style,
        fontSize=6.2,
        leading=6.8,
        textColor=text_color,
    )

    def meta_cell(value, style):
        return Paragraph(escape(str(value or "")), style)

    meta = [
        [meta_cell("Student Name", meta_label_style), meta_cell(receipt.display_student_name, meta_value_style), meta_cell("Date", meta_label_style), meta_cell(receipt.receipt_date.strftime("%d-%m-%Y"), meta_value_style)],
        [meta_cell("SID / Admn", meta_label_style), meta_cell(f"{student.legacy_sid or ''} / {student.admission_no or ''}", meta_value_style), meta_cell("Class", meta_label_style), meta_cell(class_label, meta_value_style)],
        [meta_cell("Fee Month", meta_label_style), meta_cell(month_label, meta_value_style), meta_cell("Mode", meta_label_style), meta_cell(receipt.get_payment_mode_display(), meta_value_style)],
    ]
    meta_table = Table(meta, colWidths=[28 * mm, 64 * mm, 25 * mm, 65 * mm])
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
                ("FONTSIZE", (0, 0), (-1, -1), 6.2),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
            ]
        )
    )
    story.extend([meta_table, Spacer(1, 1.5 * mm)])

    line_rows = [["Fee Head Description", "Amount (Rs.)"]]
    for line in receipt.lines.select_related("fee_head").all():
        line_rows.append([line.fee_head.name, money(line.amount)])

    body_last_idx = len(line_rows) - 1
    total_start_idx = len(line_rows)
    line_rows.append(["Fee Total", money(receipt.legacy_fee_total)])

    previous_due_idx = None
    if receipt.previous_due_amount > 0:
        previous_due_idx = len(line_rows)
        line_rows.append(["Previous Due (carried forward)", f"+ {money(receipt.previous_due_amount)}"])

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

    fee_table = Table(line_rows, colWidths=[136 * mm, 46 * mm], repeatRows=1)
    
    ts = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, border_color),
        
        # Body Lines
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.2),
        ("TEXTCOLOR", (0, 1), (-1, body_last_idx), text_color),
        ("TOPPADDING", (0, 0), (-1, -1), 1.1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.1),
        
        # Totals Section
        ("FONTNAME", (0, total_start_idx), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, total_start_idx), (-1, -1), colors.HexColor("#475569")),
        ("LINEABOVE", (0, total_start_idx), (-1, total_start_idx), 1, border_color),
        
        # Net Payable Row
        ("BACKGROUND", (0, net_idx), (-1, net_idx), light_bg),
        ("TEXTCOLOR", (0, net_idx), (-1, net_idx), text_color),
        ("LINEABOVE", (0, net_idx), (-1, net_idx), 1, border_color),
        ("LINEBELOW", (0, net_idx), (-1, net_idx), 1, border_color),
        ("FONTSIZE", (0, net_idx), (-1, net_idx), 7.2),
    ]

    if body_last_idx >= 1:
        ts.append(("LINEBELOW", (0, 1), (-1, body_last_idx), 0.5, colors.HexColor("#e2e8f0")))
    
    if due_idx:
        ts.append(("TEXTCOLOR", (0, due_idx), (-1, due_idx), colors.HexColor("#dc2626")))

    if previous_due_idx is not None:
        ts.append(("TEXTCOLOR", (0, previous_due_idx), (-1, previous_due_idx), colors.HexColor("#7c3aed")))
        ts.append(("FONTNAME", (0, previous_due_idx), (-1, previous_due_idx), "Helvetica-Bold"))

    fee_table.setStyle(TableStyle(ts))
    story.append(fee_table)

    if receipt.remarks:
        story.extend([Spacer(1, 1 * mm), Paragraph(f"<i>Remarks: {receipt.remarks}</i>", small_style)])

    story.extend(
        [
            Spacer(1, 3 * mm),
            Table(
                [["Cashier's Signature", "Parent / Guardian"]],
                colWidths=[82 * mm, 82 * mm],
                style=TableStyle(
                    [
                        ("LINEABOVE", (0, 0), (0, 0), 1, border_color),
                        ("LINEABOVE", (1, 0), (1, 0), 1, border_color),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTSIZE", (0, 0), (-1, -1), 6),
                        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#64748b")),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ]
                ),
            ),
        ]
    )
    return story


def build_fee_receipt_pdf(receipt, school_profile=None):
    buffer = BytesIO()
    page_size = landscape(A5)
    page_width, page_height = page_size
    document = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=7 * mm,
        leftMargin=7 * mm,
        topMargin=6 * mm,
        bottomMargin=7 * mm,
        title=f"Fee Receipt {receipt.receipt_no}",
    )

    story = _build_fee_receipt_story(receipt, school_profile)

    def add_watermark(canvas, doc):
        canvas.saveState()
        if receipt.is_cancelled:
            canvas.setFont('Helvetica-Bold', 60)
            canvas.setFillColor(colors.HexColor("#dc2626"), alpha=0.2)
            canvas.translate(page_width / 2, page_height / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "CANCELLED")
        elif receipt.is_edited:
            canvas.setFont('Helvetica-Bold', 60)
            canvas.setFillColor(colors.HexColor("#f59e0b"), alpha=0.2)
            canvas.translate(page_width / 2, page_height / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "EDITED")
            canvas.restoreState()
            canvas.saveState()
            canvas.setFont('Helvetica', 5.5)
            canvas.setFillColor(colors.HexColor("#b45309"))
            footer_text = f"Edited on {receipt.edited_at.strftime('%d-%m-%Y %H:%M')} by {receipt.edited_by.username if receipt.edited_by else 'System'}. Reason: {receipt.edit_reason}"
            canvas.drawCentredString(page_width / 2, 4 * mm, footer_text[:115])
        else:
            canvas.setFont('Helvetica-Bold', 68)
            canvas.setFillColor(colors.HexColor("#0f766e"), alpha=0.04)
            canvas.translate(page_width / 2, page_height / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "SCHOOLSOFT")
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

    # Top-half Frame (width=182mm, height=138mm, centered horizontally with 14mm left/right margin)
    # y1 from bottom of page: 148.5mm + 4mm = 152.5mm
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
            canvas.setFont('Helvetica-Bold', 60)
            canvas.setFillColor(colors.HexColor("#dc2626"), alpha=0.2)
            canvas.translate(center_x, center_y)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "CANCELLED")
        elif receipt.is_edited:
            canvas.setFont('Helvetica-Bold', 60)
            canvas.setFillColor(colors.HexColor("#f59e0b"), alpha=0.2)
            canvas.translate(center_x, center_y)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "EDITED")
            canvas.restoreState()
            canvas.saveState()
            canvas.setFont('Helvetica', 5.5)
            canvas.setFillColor(colors.HexColor("#b45309"))
            footer_text = f"Edited on {receipt.edited_at.strftime('%d-%m-%Y %H:%M')} by {receipt.edited_by.username if receipt.edited_by else 'System'}. Reason: {receipt.edit_reason}"
            canvas.drawCentredString(center_x, 148.5 * mm + 4 * mm, footer_text[:115])
        else:
            canvas.setFont('Helvetica-Bold', 68)
            canvas.setFillColor(colors.HexColor("#0f766e"), alpha=0.04)
            canvas.translate(center_x, center_y)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "SCHOOLSOFT")
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
'''

pdf_path = r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\core\pdf.py'
with open(pdf_path, 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = "def build_fee_receipt_pdf(receipt, school_profile=None):"
end_marker = "def build_due_report_pdf(rows, totals, school_profile=None):"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + replacement_pdf_code + "\n\n\n" + content[end_idx:]
    with open(pdf_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("core/pdf.py successfully updated with _build_fee_receipt_story, build_fee_receipt_pdf, and build_fee_receipt_pdf_2up!")
else:
    print(f"Error finding markers: start_idx={start_idx}, end_idx={end_idx}")
