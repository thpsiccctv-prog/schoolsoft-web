import os
import re

file_path = r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\core\models.py'
with open(file_path, 'r', encoding='utf-8') as f:
    code = f.read()

# Fields to add to Student model
student_additional_fields = '''
    full_name_hindi = models.CharField(
        blank=True,
        max_length=120,
        verbose_name="Full Name (Hindi)",
        help_text="छात्र/छात्रा का नाम हिंदी में (admission form print ke liye).",
    )
    father_name_hindi = models.CharField(
        blank=True,
        max_length=120,
        verbose_name="Father's Name (Hindi)",
        help_text="पिता का नाम हिंदी में।",
    )
    mother_name_hindi = models.CharField(
        blank=True,
        max_length=120,
        verbose_name="Mother's Name (Hindi)",
        help_text="माता का नाम हिंदी में।",
    )
    exam_medium = models.CharField(
        blank=True,
        choices=[("H", "Hindi"), ("E", "English")],
        max_length=1,
        verbose_name="Exam Medium",
        help_text="परीक्षा माध्यम: Hindi or English (UP Board form field).",
    )
    subject_group = models.CharField(
        blank=True,
        choices=[("HS", "High School (IX/X)"), ("A", "Arts / Humanities"), ("B", "Science"), ("C", "Commerce")],
        help_text="Board subject group for Class IX-XII admission forms.",
        max_length=10,
        verbose_name="Subject Group",
    )
    subject_1_code = models.CharField(blank=True, max_length=10, verbose_name="1st Subject")
    subject_2_code = models.CharField(blank=True, max_length=10, verbose_name="2nd Subject")
    subject_3_code = models.CharField(blank=True, max_length=10, verbose_name="3rd Subject")
    subject_4_code = models.CharField(blank=True, max_length=10, verbose_name="4th Subject")
    subject_5_code = models.CharField(blank=True, max_length=10, verbose_name="5th Subject")
    subject_6_code = models.CharField(blank=True, max_length=10, verbose_name="6th Subject")
    subject_7_code = models.CharField(blank=True, max_length=10, verbose_name="7th Subject")
    subject_voc_code = models.CharField(
        blank=True,
        help_text="UP Board SubjectVOCCode column.",
        max_length=10,
        verbose_name="Subject VOC",
    )
    subject_rev_voc_code = models.CharField(
        blank=True,
        help_text="UP Board Class 9 SubjectRevVOCCode column.",
        max_length=10,
        verbose_name="Subject RevVOC",
    )
    address_street_area = models.CharField(blank=True, max_length=150, verbose_name="Street / Mohalla / Area")
    board_candidate_type_1_code = models.CharField(
        blank=True,
        choices=[("1", "1 - Regular"), ("2", "2 - Reappear / Re-admission"), ("3", "3 - Other Recognised School")],
        default="1",
        max_length=1,
        verbose_name="Board Candidate Type 1",
    )
    board_candidate_type_2_code = models.CharField(
        blank=True,
        choices=[
            ("0", "0 - None"),
            ("1", "1 - Blindness"),
            ("2", "2 - Hearing Impairment"),
            ("3", "3 - Multiple Disabilities incl. Deaf-blindness"),
            ("4", "4 - Low Vision"),
            ("5", "5 - Leprosy Cured"),
            ("6", "6 - Locomotor Disability"),
            ("7", "7 - Dwarfism"),
            ("8", "8 - Intellectual Disability"),
            ("9", "9 - Mental Illness"),
            ("10", "10 - Autism Spectrum Disorder"),
            ("11", "11 - Cerebral Palsy"),
            ("12", "12 - Muscular Dystrophy"),
            ("13", "13 - Chronic Neurological Conditions"),
            ("14", "14 - Specific Learning Disabilities"),
            ("15", "15 - Multiple Sclerosis"),
            ("16", "16 - Speech and Language Disability"),
            ("17", "17 - Thalassemia"),
            ("18", "18 - Hemophilia"),
            ("19", "19 - Sickle Cell Disease"),
            ("20", "20 - Acid Attack Victim"),
            ("21", "21 - Parkinsons Disease"),
        ],
        default="0",
        max_length=2,
        verbose_name="Board Candidate Type 2",
    )
    board_caste_code = models.CharField(
        blank=True,
        choices=[("1", "1 - SC"), ("2", "2 - ST"), ("3", "3 - OBC"), ("4", "4 - General"), ("5", "5 - EWS")],
        max_length=1,
        verbose_name="Board Caste Code",
    )
    board_sr_number = models.CharField(blank=True, max_length=50, verbose_name="Board Sr Number")
    class8_unique_id = models.CharField(blank=True, max_length=50, verbose_name="Class 8 Unique ID")
    nationality_other = models.CharField(blank=True, max_length=100)
    previous_board_source = models.CharField(
        blank=True,
        choices=[("upboard", "Class 11 - UP Board"), ("other", "Class 11 - Other Board")],
        help_text="Required to choose Class 11 UP Board vs Other Board registration format.",
        max_length=10,
        verbose_name="Previous Board Source",
    )
    state = models.CharField(blank=True, default="Uttar Pradesh", max_length=100)
    fee_package_enabled = models.BooleanField(
        default=False,
        help_text="Use for Section D/Commerce package students or direct X/XII negotiated admission.",
        verbose_name="Package Fee Applicable",
    )
    fee_package_note = models.CharField(blank=True, max_length=255, verbose_name="Package Note")
    fee_package_total = models.DecimalField(
        decimal_places=2,
        default=Decimal("0.00"),
        max_digits=10,
        validators=[MinValueValidator(0)],
        verbose_name="Package Total",
    )
    feeder_school = models.ForeignKey(
        "FeederSchool",
        on_delete=models.SET_NULL,
        related_name="students",
        null=True,
        blank=True,
        verbose_name="Attached Feeder School",
        help_text="Feeder school (अटैच्ड विद्यालय) if student belongs to Section B/C."
    )
'''

# Student properties
student_properties = '''
    @property
    def fee_section_name(self):
        return (self.current_section.name if self.current_section else "").strip().upper()

    @property
    def fee_class_name(self):
        return (self.current_class.name if self.current_class else "").strip().upper()

    @property
    def is_zero_fee_section(self):
        return self.fee_section_name in {"B", "C"}

    @property
    def is_commerce_class(self):
        return "COM" in self.fee_class_name

    @property
    def uses_fee_package(self):
        if self.is_zero_fee_section:
            return False
        return bool(self.fee_package_enabled or self.fee_section_name == "D")

    @property
    def effective_fee_package_total(self):
        if not self.uses_fee_package:
            return Decimal("0.00")
        return self.fee_package_total if self.fee_package_total > 0 else Decimal("4500.00")
'''

# Check if Decimal and MinValueValidator are imported
if "from django.core.validators import MinValueValidator" not in code:
    code = "from django.core.validators import MinValueValidator\n" + code

# Insert student_additional_fields into Student model right before 'admission_date = models.DateField'
if "full_name_hindi" not in code:
    target = "admission_date = models.DateField(null=True, blank=True)"
    code = code.replace(target, student_additional_fields + "\n    " + target)

# Insert student properties if not present
if "def is_zero_fee_section" not in code:
    target = "def __str__(self):\n        return self.full_name"
    code = code.replace(target, target + "\n" + student_properties)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(code)

print("Student fields updated successfully!")
