import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'schoolsoft.settings')
django.setup()

from core.models import Student, TransferCertificate, SchoolProfile, SchoolClass
from core.pdf import build_transfer_certificate_pdf

# Let's find an existing TC or create one
student = Student.objects.first()
if not student:
    print("No student found")
    exit()

tc, created = TransferCertificate.objects.get_or_create(
    student=student,
    defaults={
        'tc_number': 'TC-12345',
        'book_no': 'B1',
        'sr_no': 'SR-567',
        'subjects_offered': 'English, Hindi, Math, Science',
        'fee_concession_nature': 'None',
        'ncc_scout': 'No'
    }
)

sp = SchoolProfile.objects.first()
pdf_bytes = build_transfer_certificate_pdf(tc, sp)

out_path = 'test_tc.pdf'
with open(out_path, 'wb') as f:
    f.write(pdf_bytes)

print(f"Generated {out_path}")
def date_to_words(d):
    if not d: return ""
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
            "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
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
        ("LINEBELOW", (1,0), (1,-1), 0.5, colors.HexColor("#cbd5e1")), # only underline the value
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
