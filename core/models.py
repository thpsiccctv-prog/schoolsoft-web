from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AcademicSession(TimeStampedModel):
    name = models.CharField(max_length=20, unique=True)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-starts_on", "name"]

    def __str__(self):
        return self.name


class SchoolClass(TimeStampedModel):
    legacy_code = models.PositiveIntegerField(null=True, blank=True, unique=True)
    name = models.CharField(max_length=30, unique=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Class"
        verbose_name_plural = "Classes"

    def __str__(self):
        return self.name


class Section(TimeStampedModel):
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="sections")
    name = models.CharField(max_length=10)

    class Meta:
        ordering = ["school_class__display_order", "name"]
        unique_together = [("school_class", "name")]

    def __str__(self):
        return f"{self.school_class} - {self.name}"


class House(TimeStampedModel):
    """Student house (Red/Blue/Green/Yellow by default) - editable/renameable via
    Django admin, not hardcoded, so the school can rename or add houses later
    without a code change."""

    name = models.CharField(max_length=50, unique=True)
    color_code = models.CharField(max_length=20, blank=True, help_text="e.g. #DC2626 or 'Red'")
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class SchoolProfile(TimeStampedModel):
    legacy_comp_code = models.PositiveIntegerField(null=True, blank=True, unique=True)
    udise_code = models.CharField(max_length=50, blank=True)
    name = models.CharField(max_length=120)
    address_line1 = models.CharField(max_length=120, blank=True)
    address_line2 = models.CharField(max_length=120, blank=True)
    address_line3 = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    current_year = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_active", "name"]

    @property
    def address(self):
        return ", ".join(
            part
            for part in [self.address_line1, self.address_line2, self.address_line3]
            if part
        )

    def __str__(self):
        return self.name


class Student(TimeStampedModel):
    class Gender(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"
        OTHER = "O", "Other"
        UNKNOWN = "U", "Unknown"

    class Disability(models.TextChoices):
        NONE = "none", "None"
        VISUALLY_IMPAIRED = "visually_impaired", "Visually Impaired"
        HEARING_IMPAIRED = "hearing_impaired", "Hearing Impaired"
        PHYSICALLY_DISABLED = "physically_disabled", "Physically Disabled"

    class BloodGroup(models.TextChoices):
        A_POS = "A+", "A+"
        A_NEG = "A-", "A-"
        B_POS = "B+", "B+"
        B_NEG = "B-", "B-"
        AB_POS = "AB+", "AB+"
        AB_NEG = "AB-", "AB-"
        O_POS = "O+", "O+"
        O_NEG = "O-", "O-"

    legacy_sid = models.PositiveIntegerField(null=True, blank=True, unique=True)
    pen_number = models.CharField(max_length=50, blank=True)
    apaar_id = models.CharField(max_length=50, blank=True, verbose_name="APAAR ID")
    admission_no = models.CharField(max_length=30, blank=True)
    registration_no = models.CharField(max_length=30, blank=True)
    roll_no = models.PositiveIntegerField(null=True, blank=True)
    photo = models.ImageField(upload_to="student_photos/", null=True, blank=True)
    full_name = models.CharField(max_length=120)
    father_name = models.CharField(max_length=120, blank=True)
    mother_name = models.CharField(max_length=120, blank=True)
    guardian_name = models.CharField(max_length=120, blank=True, help_text="Only if parents are not available.")
    gender = models.CharField(max_length=1, choices=Gender.choices, default=Gender.UNKNOWN)
    date_of_birth = models.DateField(null=True, blank=True)
    aadhaar_no = models.CharField(max_length=25, blank=True)
    mother_aadhaar_no = models.CharField(max_length=25, blank=True)
    father_aadhaar_no = models.CharField(max_length=25, blank=True)
    nationality = models.CharField(max_length=50, default="Indian")
    caste = models.CharField(max_length=50, blank=True, help_text="Specific caste/community name, separate from reservation Category.")
    category = models.CharField(max_length=50, blank=True, help_text="General / OBC / SC / ST only.")
    is_minority = models.BooleanField(default=False)
    disability = models.CharField(max_length=30, choices=Disability.choices, default=Disability.NONE)
    religion = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    mobile_primary = models.CharField(max_length=50, blank=True)
    mobile_secondary = models.CharField(max_length=50, blank=True)
    blood_group = models.CharField(max_length=10, choices=BloodGroup.choices, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    address_permanent = models.TextField(blank=True)
    address_local = models.TextField(blank=True)
    village_locality = models.CharField(max_length=100, blank=True)
    post = models.CharField(max_length=100, blank=True)
    block = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    pin_code = models.CharField(max_length=10, blank=True)

    # Previous school details (for students admitted by transfer, from the admission form)
    previous_board_name = models.CharField(max_length=120, blank=True)
    previous_passing_year = models.CharField(max_length=10, blank=True)
    previous_roll_no = models.CharField(max_length=30, blank=True)
    previous_school_name = models.CharField(max_length=150, blank=True)
    previous_marks_obtained = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    previous_total_marks = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    previous_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Documents Received checklist (admission desk)
    doc_tc_received = models.BooleanField(default=False, verbose_name="TC Received")
    doc_aadhar_received = models.BooleanField(default=False, verbose_name="Aadhar Card Received")
    doc_marksheet_received = models.BooleanField(default=False, verbose_name="Marksheet Received")
    doc_birth_certificate_received = models.BooleanField(default=False, verbose_name="Birth Certificate Received")
    doc_character_certificate_received = models.BooleanField(default=False, verbose_name="Character Certificate Received")
    doc_photo_received = models.BooleanField(default=False, verbose_name="Passport Photo Received")
    current_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.PROTECT,
        related_name="students",
        null=True,
        blank=True,
    )
    current_section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="students",
        null=True,
        blank=True,
    )
    house = models.ForeignKey(
        House,
        on_delete=models.SET_NULL,
        related_name="students",
        null=True,
        blank=True,
    )
    admission_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["current_class__display_order", "current_section__name", "roll_no", "full_name"]
        indexes = [
            models.Index(fields=["full_name"]),
            models.Index(fields=["admission_no"]),
            models.Index(fields=["legacy_sid"]),
        ]

    def __str__(self):
        return self.full_name


class FeeHead(TimeStampedModel):
    class Frequency(models.TextChoices):
        ONE_TIME = "one_time", "One time"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUAL = "annual", "Annual"
        OPTIONAL = "optional", "Optional"

    name = models.CharField(max_length=80, unique=True)
    legacy_column = models.CharField(max_length=80, blank=True)
    frequency = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY)
    is_transport = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class FeeStructure(TimeStampedModel):
    session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="fee_structures")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="fee_structures")
    fee_head = models.ForeignKey(FeeHead, on_delete=models.PROTECT, related_name="fee_structures")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["session__name", "school_class__display_order", "fee_head__name"]
        unique_together = [("session", "school_class", "fee_head")]

    def __str__(self):
        return f"{self.session} / {self.school_class} / {self.fee_head}"


class FeeReceipt(TimeStampedModel):
    class PaymentMode(models.TextChoices):
        CASH = "cash", "Cash"
        CHEQUE = "cheque", "Cheque"
        ONLINE = "online", "Online"
        CARD = "card", "Card"
        OTHER = "other", "Other"

    legacy_receipt_no = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    receipt_no = models.CharField(max_length=30, unique=True)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="fee_receipts")
    session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="fee_receipts")
    student_name_snapshot = models.CharField(max_length=120, blank=True)
    father_name_snapshot = models.CharField(max_length=120, blank=True)
    class_snapshot = models.CharField(max_length=30, blank=True)
    section_snapshot = models.CharField(max_length=10, blank=True)
    receipt_date = models.DateField(default=timezone.localdate)
    from_month = models.CharField(max_length=25, blank=True)
    to_month = models.CharField(max_length=25, blank=True)
    payment_mode = models.CharField(max_length=20, choices=PaymentMode.choices, default=PaymentMode.CASH)
    concession_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    late_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    received_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    legacy_fee_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    legacy_net_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    legacy_due_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    remarks = models.CharField(max_length=255, blank=True)
    is_cancelled = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="cancelled_receipts",
        null=True,
        blank=True,
    )
    cancel_reason = models.CharField(max_length=255, blank=True)
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="edited_receipts",
        null=True,
        blank=True,
    )
    edit_reason = models.CharField(max_length=255, blank=True)
    edit_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-receipt_date", "-id"]
        indexes = [
            models.Index(fields=["receipt_date"]),
            models.Index(fields=["legacy_receipt_no"]),
        ]

    @property
    def line_total(self):
        return sum((line.amount for line in self.lines.all()), Decimal("0.00"))

    @property
    def payable_amount(self):
        return self.line_total + self.late_fee_amount - self.concession_amount

    @property
    def display_student_name(self):
        return self.student_name_snapshot or self.student.full_name

    @property
    def display_father_name(self):
        return self.father_name_snapshot or self.student.father_name

    @property
    def display_class_name(self):
        if self.class_snapshot:
            return self.class_snapshot
        return self.student.current_class.name if self.student.current_class else ""

    @property
    def display_section_name(self):
        if self.section_snapshot:
            return self.section_snapshot
        return self.student.current_section.name if self.student.current_section else ""

    @property
    def display_class_section(self):
        class_name = self.display_class_name
        section_name = self.display_section_name
        if class_name and section_name:
            return f"{class_name}-{section_name}"
        return class_name or section_name

    def __str__(self):
        return self.receipt_no


class FeeReceiptAuditLog(TimeStampedModel):
    class ActionChoices(models.TextChoices):
        CREATED = "created", "Created"
        EDITED = "edited", "Edited"
        CANCELLED = "cancelled", "Cancelled"

    receipt = models.ForeignKey(FeeReceipt, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=20, choices=ActionChoices.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipt_audit_logs",
    )
    changed_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True)
    before_snapshot = models.JSONField(null=True, blank=True)
    after_snapshot = models.JSONField(null=True, blank=True)
    changes = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.receipt.receipt_no} - {self.get_action_display()} at {self.changed_at.strftime('%Y-%m-%d %H:%M')}"


class FeeReceiptLine(TimeStampedModel):
    receipt = models.ForeignKey(FeeReceipt, on_delete=models.CASCADE, related_name="lines")
    fee_head = models.ForeignKey(FeeHead, on_delete=models.PROTECT, related_name="receipt_lines")
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["fee_head__name"]
        unique_together = [("receipt", "fee_head")]

    def __str__(self):
        return f"{self.receipt} - {self.fee_head}"


class TransferCertificate(TimeStampedModel):
    class Conduct(models.TextChoices):
        EXCELLENT = "excellent", "Excellent"
        GOOD = "good", "Good"
        SATISFACTORY = "satisfactory", "Satisfactory"
        POOR = "poor", "Poor"

    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name="transfer_certificate")
    tc_number = models.CharField(max_length=30, unique=True)
    book_no = models.CharField(max_length=30, blank=True)
    sr_no = models.CharField(max_length=30, blank=True)
    issue_date = models.DateField(default=timezone.localdate)
    date_of_leaving = models.DateField(null=True, blank=True)
    last_class_studied = models.ForeignKey(
        SchoolClass, on_delete=models.PROTECT, related_name="transfer_certificates", null=True, blank=True
    )
    last_section = models.CharField(max_length=10, blank=True)
    reason_for_leaving = models.CharField(max_length=255, blank=True)
    subjects_offered = models.CharField(max_length=255, blank=True)
    whether_failed = models.BooleanField(default=False)
    fee_concession_nature = models.CharField(max_length=255, blank=True)
    ncc_scout = models.CharField(max_length=100, blank=True)
    struck_off_date = models.DateField(null=True, blank=True)
    school_category = models.CharField(max_length=50, default="Independent")
    conduct = models.CharField(max_length=20, choices=Conduct.choices, default=Conduct.GOOD)
    general_progress = models.CharField(max_length=20, choices=Conduct.choices, default=Conduct.GOOD)
    total_working_days = models.PositiveIntegerField(null=True, blank=True)
    days_present = models.PositiveIntegerField(null=True, blank=True)
    fees_paid_upto = models.CharField(max_length=50, blank=True)
    qualified_for_promotion = models.BooleanField(default=True)
    promoted_to_class = models.CharField(max_length=30, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-issue_date", "-id"]

    def __str__(self):
        return f"TC {self.tc_number} - {self.student}"


class DisciplineRecord(TimeStampedModel):
    """Admin/Principal-only disciplinary incident log, kept separate from the
    TC's General Conduct rating (that stays a manual staff judgment call made
    at TC time). Used for internal tracking and a printable PTM summary."""

    class Severity(models.TextChoices):
        MINOR = "minor", "Minor"
        MAJOR = "major", "Major"
        SEVERE = "severe", "Severe"

    class Category(models.TextChoices):
        LATE_COMING = "late_coming", "Late Coming"
        ATTENDANCE = "attendance", "Attendance Issue"
        MISCONDUCT = "misconduct", "Misconduct"
        BULLYING = "bullying", "Bullying / Ragging"
        PROPERTY_DAMAGE = "property_damage", "Property Damage"
        ACADEMIC_DISHONESTY = "academic_dishonesty", "Academic Dishonesty (Cheating)"
        UNIFORM_GROOMING = "uniform_grooming", "Uniform / Grooming"
        OTHER = "other", "Other"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="discipline_records")
    incident_date = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MINOR)
    description = models.TextField()
    action_taken = models.TextField(blank=True)
    parent_notified = models.BooleanField(default=False)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discipline_records_reported",
    )

    class Meta:
        ordering = ["-incident_date", "-id"]

    def __str__(self):
        return f"{self.student.full_name} - {self.get_category_display()} ({self.incident_date})"


class InventoryItem(TimeStampedModel):
    """Master catalog of uniform/book/stationery items the school issues to
    students - just a name, category and standard price. Kept separate from
    FeeHead on purpose: this is physical-goods distribution/concession
    tracking, not a fee ledger entry."""

    class Category(models.TextChoices):
        UNIFORM = "uniform", "Uniform"
        SHOES = "shoes", "Shoes"
        BOOK = "book", "Book"
        STATIONERY = "stationery", "Stationery"
        OTHER = "other", "Other"

    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name


class InventoryIssue(TimeStampedModel):
    """One record of an item (or a quantity of it) handed to a student.
    unit_price is snapshotted from the item at issue time so a later price
    change doesn't rewrite history. amount_charged is what was actually
    collected - staff can reduce it below quantity*unit_price for a
    concession, or set it to 0 for a fully free issue; amount_charged is the
    single source of truth rather than a separate is_free flag."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="inventory_issues")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="issues")
    issue_date = models.DateField(default=timezone.localdate)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    amount_charged = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    remarks = models.CharField(max_length=200, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_issues_recorded",
    )

    class Meta:
        ordering = ["-issue_date", "-id"]

    @property
    def is_free(self):
        return self.amount_charged == 0

    @property
    def full_price(self):
        return self.unit_price * self.quantity

    @property
    def concession_amount(self):
        full = self.full_price
        return full - self.amount_charged if full > self.amount_charged else Decimal("0")

    def __str__(self):
        return f"{self.item.name} x{self.quantity} -> {self.student.full_name}"


class Subject(TimeStampedModel):
    name = models.CharField(max_length=80, unique=True)
    legacy_code = models.CharField(max_length=40, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class ExamTerm(TimeStampedModel):
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name="exam_terms")
    name = models.CharField(max_length=60)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["session__name", "display_order", "name"]
        unique_together = [("session", "name")]

    def __str__(self):
        return f"{self.name} ({self.session})"


class ExamTest(TimeStampedModel):
    term = models.ForeignKey(ExamTerm, on_delete=models.CASCADE, related_name="tests")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="exam_tests")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="exam_tests")
    max_marks = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("100.00"))
    pass_marks = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("33.00"))

    class Meta:
        ordering = ["term__display_order", "school_class__display_order", "subject__display_order"]
        unique_together = [("term", "school_class", "subject")]

    def __str__(self):
        return f"{self.term} / {self.school_class} / {self.subject}"


class ExamMark(TimeStampedModel):
    exam_test = models.ForeignKey(ExamTest, on_delete=models.CASCADE, related_name="marks")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="exam_marks")
    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    is_absent = models.BooleanField(default=False)
    grade = models.CharField(max_length=5, blank=True)
    remarks = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["exam_test__subject__display_order"]
        unique_together = [("exam_test", "student")]

    @property
    def percentage(self):
        if self.is_absent or self.marks_obtained is None or not self.exam_test.max_marks:
            return None
        return (self.marks_obtained / self.exam_test.max_marks) * Decimal("100")

    def compute_grade(self):
        if self.is_absent or self.marks_obtained is None:
            return "AB"
        pct = self.percentage
        return grade_for_percentage(pct)

    def save(self, *args, **kwargs):
        if not self.grade:
            self.grade = self.compute_grade()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.exam_test}"


def grade_for_percentage(pct):
    if pct is None:
        return "AB"
    pct = float(pct)
    if pct >= 90:
        return "A1"
    if pct >= 80:
        return "A2"
    if pct >= 70:
        return "B1"
    if pct >= 60:
        return "B2"
    if pct >= 50:
        return "C1"
    if pct >= 40:
        return "C2"
    if pct >= 33:
        return "D"
    return "E"


class Staff(TimeStampedModel):
    class StaffType(models.TextChoices):
        TEACHING = "teaching", "Teaching"
        NON_TEACHING = "non_teaching", "Non-teaching"
        ADMIN = "admin", "Admin"
        OTHER = "other", "Other"

    legacy_emp_code = models.PositiveIntegerField(null=True, blank=True, unique=True)
    full_name = models.CharField(max_length=120)
    designation = models.CharField(max_length=80, blank=True)
    staff_type = models.CharField(max_length=20, choices=StaffType.choices, default=StaffType.TEACHING)
    qualification = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    date_of_joining = models.DateField(null=True, blank=True)
    date_of_leaving = models.DateField(null=True, blank=True)
    pf_applicable = models.BooleanField(default=False)
    pf_account_no = models.CharField(max_length=40, blank=True)
    esi_applicable = models.BooleanField(default=False)
    esi_account_no = models.CharField(max_length=40, blank=True)
    basic_pay = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    da = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    other_allowances = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["full_name"]),
            models.Index(fields=["legacy_emp_code"]),
        ]

    @property
    def gross_salary(self):
        return self.basic_pay + self.da + self.other_allowances

    def __str__(self):
        return self.full_name


class SalaryPayment(TimeStampedModel):
    class PaymentMode(models.TextChoices):
        CASH = "cash", "Cash"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CHEQUE = "cheque", "Cheque"
        OTHER = "other", "Other"

    slip_no = models.CharField(max_length=30, unique=True)
    staff = models.ForeignKey(Staff, on_delete=models.PROTECT, related_name="salary_payments")
    pay_month = models.DateField(help_text="Use the 1st of the salary month, e.g. 2026-07-01 for July 2026.")
    payment_date = models.DateField(default=timezone.localdate)
    payment_mode = models.CharField(max_length=20, choices=PaymentMode.choices, default=PaymentMode.CASH)
    basic_pay = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    da = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    other_allowances = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    pf_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    esi_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    other_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    advance_recovery = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    remarks = models.CharField(max_length=255, blank=True)
    
    is_cancelled = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="cancelled_salary_payments",
        null=True,
        blank=True,
    )
    cancel_reason = models.CharField(max_length=255, blank=True)
    
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="edited_salary_payments",
        null=True,
        blank=True,
    )
    edit_reason = models.CharField(max_length=255, blank=True)
    edit_count = models.PositiveIntegerField(default=0)


    class Meta:
        ordering = ["-pay_month", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "pay_month"],
                condition=models.Q(is_cancelled=False),
                name="unique_active_salary"
            )
        ]

    @property
    def gross_pay(self):
        return self.basic_pay + self.da + self.other_allowances

    @property
    def total_deductions(self):
        return self.pf_deduction + self.esi_deduction + self.other_deduction

    @property
    def net_pay(self):
        return self.gross_pay - self.total_deductions - self.advance_recovery

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.net_pay < 0:
            raise ValidationError({"advance_recovery": "Net pay cannot be negative. Advance recovery is too high."})

    def __str__(self):
        return f"{self.slip_no} - {self.staff}"


class SalaryPaymentAuditLog(TimeStampedModel):
    class ActionChoices(models.TextChoices):
        CREATED = "created", "Created"
        EDITED = "edited", "Edited"
        CANCELLED = "cancelled", "Cancelled"

    payment = models.ForeignKey(SalaryPayment, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=20, choices=ActionChoices.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_audit_logs",
    )
    changed_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True)
    before_snapshot = models.JSONField(null=True, blank=True)
    after_snapshot = models.JSONField(null=True, blank=True)
    changes = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.payment.slip_no} - {self.get_action_display()} at {self.changed_at.strftime('%Y-%m-%d %H:%M')}"



class TransportBus(TimeStampedModel):
    legacy_bus_code = models.PositiveIntegerField(null=True, blank=True, unique=True)
    name = models.CharField(max_length=60)
    vehicle_no = models.CharField(max_length=60, blank=True)
    driver_name = models.CharField(max_length=80, blank=True)
    helpline = models.CharField(max_length=50, blank=True)
    default_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "vehicle_no"]

    def __str__(self):
        return self.vehicle_no or self.name


class TransportRoute(TimeStampedModel):
    legacy_route_code = models.PositiveIntegerField(null=True, blank=True, unique=True)
    name = models.CharField(max_length=100)
    monthly_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class StudentTransport(TimeStampedModel):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="transport_assignments")
    route = models.ForeignKey(
        TransportRoute,
        on_delete=models.SET_NULL,
        related_name="student_assignments",
        null=True,
        blank=True,
    )
    bus = models.ForeignKey(
        TransportBus,
        on_delete=models.SET_NULL,
        related_name="student_assignments",
        null=True,
        blank=True,
    )
    legacy_sr_no = models.PositiveIntegerField(null=True, blank=True, unique=True)
    legacy_student_name = models.CharField(max_length=120, blank=True)
    legacy_father_name = models.CharField(max_length=120, blank=True)
    legacy_route_name = models.CharField(max_length=100, blank=True)
    legacy_bus_label = models.CharField(max_length=60, blank=True)
    stop_name = models.CharField(max_length=100, blank=True)
    applied_on = models.DateField(null=True, blank=True)
    charge_month = models.CharField(max_length=30, blank=True)
    due_month = models.CharField(max_length=30, blank=True)
    is_transport_enabled = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = [
            "student__current_class__display_order",
            "student__current_section__name",
            "student__full_name",
        ]

    def __str__(self):
        route = self.route or self.legacy_route_name or "No route"
        return f"{self.student} - {route}"


class LegacyImportBatch(TimeStampedModel):
    source_database = models.CharField(max_length=255)
    source_table = models.CharField(max_length=80)
    records_seen = models.PositiveIntegerField(default=0)
    records_imported = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.source_table} import on {self.created_at:%Y-%m-%d}"


# ---------------------------------------------------------------------------
# Accounting — Phase 1 MVP (Daily Expense / Cash Book)
# ---------------------------------------------------------------------------


class AccountGroup(TimeStampedModel):
    """Top-level account classification (Asset, Expense, Income, etc.)."""

    class GroupType(models.TextChoices):
        ASSET = "asset", "Asset"
        EXPENSE = "expense", "Expense"
        INCOME = "income", "Income"
        LIABILITY = "liability", "Liability"

    name = models.CharField(max_length=60, unique=True)
    group_type = models.CharField(
        max_length=20, choices=GroupType.choices, default=GroupType.EXPENSE
    )
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class LedgerAccount(TimeStampedModel):
    """Individual account head under a group (Cash, Diesel, Bank, etc.)."""

    group = models.ForeignKey(
        AccountGroup, on_delete=models.PROTECT, related_name="ledgers"
    )
    name = models.CharField(max_length=80, unique=True)
    opening_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="Balance when the system starts using this ledger.",
    )
    opening_balance_date = models.DateField(
        null=True, blank=True,
        help_text="Date from which the opening balance applies.",
    )
    is_cash_or_bank = models.BooleanField(
        default=False,
        help_text="True for Cash in Hand / Bank accounts (used in Cash Book).",
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class VoucherCounter(models.Model):
    """Race-safe auto-numbering: one counter per voucher type per session."""

    session = models.ForeignKey(
        AcademicSession, on_delete=models.CASCADE, related_name="voucher_counters"
    )
    voucher_type = models.CharField(max_length=10)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("session", "voucher_type")]

    def __str__(self):
        return f"{self.voucher_type} / {self.session} → {self.last_number}"


class Voucher(TimeStampedModel):
    """Single-line accounting voucher (expense / receipt / contra / opening).

    Every voucher records one debit and one credit, maintaining double-entry
    bookkeeping.  Multi-line journal entries are planned for Phase 2.
    """

    class VoucherType(models.TextChoices):
        CASH_PAYMENT = "CPMT", "Cash Payment"
        CASH_RECEIPT = "CREC", "Cash Receipt"
        BANK = "BNK", "Bank Payment / Receipt"
        CONTRA = "CNTR", "Contra (Cash ↔ Bank)"
        OPENING = "OPEN", "Opening Balance"

    class PaymentMode(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank"
        ONLINE = "online", "Online"
        CHEQUE = "cheque", "Cheque"

    voucher_no = models.CharField(max_length=30, unique=True)
    voucher_type = models.CharField(
        max_length=10, choices=VoucherType.choices, default=VoucherType.CASH_PAYMENT
    )
    session = models.ForeignKey(
        AcademicSession, on_delete=models.PROTECT, related_name="vouchers"
    )
    voucher_date = models.DateField(default=timezone.localdate)
    debit_account = models.ForeignKey(
        LedgerAccount, on_delete=models.PROTECT, related_name="debit_vouchers",
        help_text="Account debited (money goes TO this account).",
    )
    credit_account = models.ForeignKey(
        LedgerAccount, on_delete=models.PROTECT, related_name="credit_vouchers",
        help_text="Account credited (money comes FROM this account).",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_to_or_received_from = models.CharField(
        max_length=120, blank=True,
        help_text="Person name (e.g. 'Ramesh Driver').",
    )
    narration = models.TextField(blank=True)
    payment_mode = models.CharField(
        max_length=20, choices=PaymentMode.choices, default=PaymentMode.CASH
    )
    physical_slip_no = models.CharField(
        max_length=30, blank=True,
        help_text="Optional physical voucher pad reference number.",
    )
    staff = models.ForeignKey(
        'core.Staff', on_delete=models.SET_NULL, null=True, blank=True,
        related_name="vouchers",
        help_text="Linked staff member for salary and staff advance.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="created_vouchers", null=True, blank=True,
    )

    # --- Cancel audit ---
    is_cancelled = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="cancelled_vouchers", null=True, blank=True,
    )
    cancel_reason = models.CharField(max_length=255, blank=True)

    # --- Edit audit ---
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="edited_vouchers", null=True, blank=True,
    )
    edit_reason = models.CharField(max_length=255, blank=True)
    edit_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-voucher_date", "-id"]
        indexes = [
            models.Index(fields=["voucher_date"]),
            models.Index(fields=["voucher_type"]),
        ]

    def __str__(self):
        return f"{self.voucher_no} — Rs. {self.amount}"


class VoucherAuditLog(models.Model):
    """Audit trail for voucher edits and cancellations."""

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        EDITED = "edited", "Edited"
        CANCELLED = "cancelled", "Cancelled"

    voucher = models.ForeignKey(
        Voucher, on_delete=models.CASCADE, related_name="audit_logs"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="voucher_audit_logs", null=True, blank=True,
    )
    changed_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True)
    before_snapshot = models.JSONField(null=True, blank=True)
    after_snapshot = models.JSONField(null=True, blank=True)
    changes = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.voucher.voucher_no} — {self.action} by {self.changed_by}"


class ModuleAccess(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        verbose_name = "SchoolSoft module permission"
        verbose_name_plural = "SchoolSoft module permissions"
        permissions = [
            ("access_all_modules", "SchoolSoft: Access all modules"),
            ("access_dashboard", "SchoolSoft: Open dashboard"),
            ("access_students", "SchoolSoft: Students and admissions"),
            ("access_fee_collection", "SchoolSoft: Fee collection"),
            ("access_receipts", "SchoolSoft: Receipt register and receipt PDFs"),
            ("access_dues", "SchoolSoft: Dues report"),
            ("access_collection", "SchoolSoft: Collection report"),
            ("access_fee_setup", "SchoolSoft: Fee setup"),
            ("access_marks", "SchoolSoft: Marks and marksheets"),
            ("access_staff", "SchoolSoft: Staff and salary"),
            ("access_transport", "SchoolSoft: Transport"),
            ("access_school_profile", "SchoolSoft: School profile"),
            ("access_accounts", "SchoolSoft: Accounts and cash book"),
            ("access_inventory", "SchoolSoft: Inventory (uniform/books)"),
        ]
