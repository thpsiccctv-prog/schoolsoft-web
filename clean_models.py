clean_block = '''class Person(TimeStampedModel):
    """Represents an individual or external party (Lender, Vendor, Manager, etc.).
    Used to safely consolidate ledgers that belong to the same real-world entity
    without relying on string matching."""

    class PersonType(models.TextChoices):
        LENDER = "lender", "Lender"
        MANAGER = "manager", "Manager"
        VENDOR = "vendor", "Vendor"
        OTHER = "other", "Other"

    name = models.CharField(max_length=120, unique=True)
    person_type = models.CharField(max_length=20, choices=PersonType.choices, default=PersonType.OTHER)
    contact_info = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_person_type_display()})"


class LedgerAccount(TimeStampedModel):
    """Individual account head under a group (Cash, Diesel, Bank, etc.)."""

    group = models.ForeignKey(
        AccountGroup, on_delete=models.PROTECT, related_name="ledgers"
    )
    person = models.ForeignKey(
        Person, on_delete=models.SET_NULL, related_name="ledgers", null=True, blank=True,
        help_text="Optional link to a Person for consolidating personal accounts."
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


class FeederSchool(TimeStampedModel):
    """Attached/Feeder school (अटैच्ड विद्यालय) whose students take admission
    in Section B / Section C for Classes 9-12 UP Board registration."""

    name = models.CharField(max_length=150, unique=True, verbose_name="School Name")
    code = models.CharField(max_length=30, unique=True, blank=True, verbose_name="School Code")
    contact_person = models.CharField(max_length=100, blank=True, verbose_name="Contact Person / Manager / Principal")
    phone = models.CharField(max_length=50, blank=True, verbose_name="Phone Number")
    village_address = models.CharField(max_length=200, blank=True, verbose_name="Village / Town / Location")
    package_rate_per_student = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("1500.00"),
        verbose_name="Package Rate per Student (₹)",
        help_text="Fixed 2-year package rate per student (e.g. ₹1,500 or ₹1,800)."
    )
    ledger_account = models.OneToOneField(
        LedgerAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name="feeder_school_profile",
        help_text="Linked Sundry Debtors ledger account."
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Attached / Feeder School"
        verbose_name_plural = "Attached / Feeder Schools"

    def __str__(self):
        return self.name

    @property
    def total_enrolled_students(self):
        return self.students.filter(is_active=True).count()

    @property
    def total_demand(self):
        return self.total_enrolled_students * self.package_rate_per_student

    @property
    def total_received(self):
        if not self.ledger_account:
            return Decimal("0.00")
        from django.db.models import Sum
        received = Voucher.objects.filter(
            credit_account=self.ledger_account,
            is_cancelled=False
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        return received

    @property
    def balance_due(self):
        return max(Decimal("0.00"), self.total_demand - self.total_received)


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
'''

file_path = r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\core\models.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Target start: class Person(TimeStampedModel):
start_marker = "class Person(TimeStampedModel):"
end_marker = "class VoucherType(models.TextChoices):"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker) + len(end_marker)

# We want to replace from start_idx to end_idx with clean_block up to VoucherType
prefix = content[:start_idx]
suffix = content[content.find("CASH_PAYMENT = \"CPMT\"", end_idx):]

new_content = prefix + clean_block + "        " + suffix
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Models cleaned successfully!")
