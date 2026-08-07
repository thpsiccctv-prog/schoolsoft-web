from decimal import Decimal

from django import forms
from django.db.models import Count, Max
from django.utils import timezone

from .models import AcademicSession, AccountGroup, DisciplineRecord, Family, FeeHead, FeeReceipt, House, InventoryIssue, InventoryItem, SalaryPayment, Section, Staff, Student, TransferCertificate, LedgerAccount, Voucher, TransportRoute, StudentTransport

class SectionSelect(forms.Select):
    """Renders each <option> with a data-class attribute so student_form.html can
    show only the sections belonging to the currently selected class, client-side."""

    def optgroups(self, name, value, attrs=None):
        try:
            from core.models import Section
            self._temp_map = {s.id: str(s.school_class_id) for s in Section.objects.all()}
        except Exception:
            self._temp_map = {}
        return super().optgroups(name, value, attrs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value and hasattr(self, "_temp_map"):
            try:
                # value could be a ModelChoiceIteratorValue, so convert to str first
                class_id = self._temp_map.get(int(str(value)))
                if class_id:
                    option["attrs"]["data-class"] = class_id
            except (ValueError, TypeError):
                pass
        return option


class StudentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        class_bits = []
        if obj.current_class:
            class_bits.append(obj.current_class.name)
        if obj.current_section:
            class_bits.append(obj.current_section.name)
        class_label = "-".join(class_bits)
        sid = f"SID {obj.legacy_sid}" if obj.legacy_sid else "No SID"
        admission = f"Adm {obj.admission_no}" if obj.admission_no else ""
        father = f"Father {obj.father_name}" if obj.father_name else ""
        mobile = f"Mobile {obj.mobile_primary}" if obj.mobile_primary else ""
        details = " | ".join(part for part in [sid, class_label, admission, father, mobile] if part)
        status_marker = "" if obj.is_active else " [INACTIVE]"
        return f"{obj.full_name}{status_marker} ({details})"


class TransportRouteChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} - ₹{obj.monthly_charge}"

class StudentForm(forms.ModelForm):
    transport_required = forms.BooleanField(required=False, label="Transport Required?")
    transport_route = TransportRouteChoiceField(
        queryset=TransportRoute.objects.none(),
        required=False,
        label="Route",
        empty_label="-- Select Route --"
    )
    stop_name = forms.CharField(required=False, label="Stop Name", max_length=100)

    class Meta:
        model = Student
        fields = [
            "registration_no",
            "admission_no",
            "scholar_register_no",
            "pen_number",
            "apaar_id",
            "legacy_sid",
            "admission_date",
            "full_name",
            "current_class",
            "current_section",
            "house",
            "roll_no",
            "photo",
            "date_of_birth",
            "gender",
            "aadhaar_no",
            "father_name",
            "mother_name",
            "guardian_name",
            "mother_aadhaar_no",
            "father_aadhaar_no",
            "caste",
            "category",
            "is_minority",
            "disability",
            "religion",
            "email",
            "mobile_primary",
            "mobile_secondary",
            "blood_group",
            "weight_kg",
            "height_cm",
            "address_local",
            "address_permanent",
            "village_locality",
            "post",
            "block",
            "district",
            "pin_code",
            "previous_board_name",
            "previous_passing_year",
            "previous_roll_no",
            "previous_school_name",
            "previous_marks_obtained",
            "previous_total_marks",
            "previous_percentage",
            "doc_tc_received",
            "doc_aadhar_received",
            "doc_marksheet_received",
            "doc_birth_certificate_received",
            "doc_character_certificate_received",
            "doc_photo_received",
            "is_active",
        ]
        widgets = {
            "admission_date": forms.DateInput(attrs={"type": "date"}),
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "address_local": forms.Textarea(attrs={"rows": 2}),
            "address_permanent": forms.Textarea(attrs={"rows": 2}),
            "current_section": SectionSelect(),
        }
        labels = {
            "scholar_register_no": "Scholar Register Book No.",
            "pen_number": "PEN Number",
            "apaar_id": "APAAR ID",
            "caste": "Caste",
            "category": "Category (General/OBC/SC/ST)",
            "is_minority": "Minority",
            "pin_code": "PIN Code",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["transport_route"].queryset = TransportRoute.objects.filter(is_active=True).order_by("name")
        self.fields["scholar_register_no"].disabled = True
        self.fields["scholar_register_no"].help_text = "Automatic from Admission No. (100 students per register)."
        
        # Prefill transport fields for existing students
        if self.instance.pk:
            transport = self.instance.transport_assignments.filter(is_active=True).first()
            if transport:
                self.initial["transport_required"] = True
                self.initial["transport_route"] = transport.route
                self.initial["stop_name"] = transport.stop_name

        if not self.instance.pk:
            if "admission_date" not in self.initial:
                self.initial["admission_date"] = timezone.localdate()
            if "legacy_sid" not in self.initial:
                max_sid = Student.objects.aggregate(max_sid=Max("legacy_sid"))["max_sid"]
                self.fields["legacy_sid"].initial = (max_sid or 0) + 1
            if "house" not in self.initial:
                # Auto-suggest the least-populated active house (round-robin
                # balance). Staff can still change it before saving.
                suggested = (
                    House.objects.filter(is_active=True)
                    .annotate(student_count=Count("students"))
                    .order_by("student_count", "display_order")
                    .first()
                )
                if suggested:
                    self.fields["house"].initial = suggested.pk

        self.fields["current_section"].label_from_instance = lambda obj: obj.name

        for field_name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        transport_required = cleaned_data.get("transport_required")
        transport_route = cleaned_data.get("transport_route")
        stop_name = cleaned_data.get("stop_name")

        if transport_required:
            if not transport_route:
                self.add_error("transport_route", "Please select a route if transport is required.")
            if not stop_name:
                self.add_error("stop_name", "Please enter a stop name if transport is required.")
                
        return cleaned_data

class FeeReceiptEntryForm(forms.ModelForm):
    student = StudentChoiceField(queryset=Student.objects.none())

    class Meta:
        model = FeeReceipt
        fields = [
            "student",
            "session",
            "receipt_date",
            "from_month",
            "to_month",
            "payment_mode",
            "concession_amount",
            "late_fee_amount",
            "received_amount",
            "remarks",
        ]
        widgets = {
            "receipt_date": forms.DateInput(attrs={"type": "date"}),
            "remarks": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.select_related(
            "current_class",
            "current_section",
        ).filter(is_active=True).order_by("full_name")
        self.fields["session"].queryset = AcademicSession.objects.filter(is_active=True).order_by("-starts_on", "name")
        active_session = AcademicSession.objects.filter(is_active=True).order_by("-starts_on").first()
        if "session" not in self.initial and active_session:
            self.fields["session"].initial = active_session
        self.fields["receipt_date"].initial = timezone.localdate()
        self.fields["student"].empty_label = "Select active student"
        self.fields["session"].empty_label = "Select session"

class FeeReceiptEditForm(FeeReceiptEntryForm):
    edit_reason = forms.CharField(
        max_length=255,
        required=True,
        label="Reason for Correction",
        widget=forms.TextInput(attrs={"placeholder": "Enter reason for this correction"}),
    )

    class Meta(FeeReceiptEntryForm.Meta):
        fields = FeeReceiptEntryForm.Meta.fields + ["edit_reason"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Phase 1: Restrict changes to student, session, and month to prevent duplicate receipt overlaps.
        self.fields["student"].disabled = True
        self.fields["session"].disabled = True
        self.fields["from_month"].disabled = True
        self.fields["to_month"].disabled = True
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class FeeReceiptLineEntryForm(forms.Form):
    def __init__(self, *args, require_positive_total=True, **kwargs):
        self.fee_heads = list(FeeHead.objects.filter(is_active=True).order_by("name"))
        # New receipts require a fee-head amount. Receipt correction can pass
        # False only for a historical previous-due-only receipt whose deprecated
        # value remains stored but is no longer editable.
        self.require_positive_total = require_positive_total
        super().__init__(*args, **kwargs)

        for fee_head in self.fee_heads:
            self.fields[self.field_name(fee_head)] = forms.DecimalField(
                label=fee_head.name,
                required=False,
                min_value=Decimal("0.00"),
                max_digits=10,
                decimal_places=2,
                initial=Decimal("0.00"),
                widget=forms.NumberInput(attrs={"step": "0.01", "class": "form-control amount-input"}),
            )

    def clean(self):
        cleaned_data = super().clean()
        total = Decimal("0.00")

        for fee_head in self.fee_heads:
            amount = cleaned_data.get(self.field_name(fee_head)) or Decimal("0.00")
            total += amount

        if self.require_positive_total and total <= Decimal("0.00"):
            raise forms.ValidationError("At least one fee head amount is required.")

        cleaned_data["line_total"] = total
        return cleaned_data

    def amounts(self):
        for fee_head in self.fee_heads:
            amount = self.cleaned_data.get(self.field_name(fee_head)) or Decimal("0.00")
            if amount > Decimal("0.00"):
                yield fee_head, amount

    def field_name(self, fee_head):
        return f"fee_head_{fee_head.id}"


class DisciplineRecordForm(forms.ModelForm):
    class Meta:
        model = DisciplineRecord
        fields = [
            "incident_date",
            "category",
            "severity",
            "description",
            "action_taken",
            "parent_notified",
        ]
        widgets = {
            "incident_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "action_taken": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["incident_date"].initial = timezone.localdate()
        for field_name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-control")


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ["name", "category", "unit_price", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-control")


class InventoryIssueForm(forms.ModelForm):
    class Meta:
        model = InventoryIssue
        fields = ["item", "issue_date", "quantity", "amount_charged", "remarks"]
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "date"}),
            "remarks": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = InventoryItem.objects.filter(is_active=True)
        self.fields["issue_date"].initial = timezone.localdate()
        self.fields["amount_charged"].help_text = (
            "Defaults to item price x quantity - reduce for a concession, or set to 0 for a free issue."
        )
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-control")


class FamilyForm(forms.ModelForm):
    class Meta:
        model = Family
        fields = ["name", "primary_mobile", "secondary_mobile", "address", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class TransferCertificateForm(forms.ModelForm):
    class Meta:
        model = TransferCertificate
        fields = [
            "issue_date",
            "withdrawal_file_no",
            "application_date",
            "date_of_leaving",
            "last_class_studied",
            "last_section",
            "reason_for_leaving",
            "annual_exam_result",
            "subjects_offered",
            "whether_failed",
            "conduct",
            "general_progress",
            "total_working_days",
            "days_present",
            "fees_paid_upto",
            "fee_concession_nature",
            "ncc_scout",
            "extracurricular_activities",
            "qualified_for_promotion",
            "promoted_to_class",
            "struck_off_date",
            "remarks",
        ]
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "date"}),
            "application_date": forms.DateInput(attrs={"type": "date"}),
            "date_of_leaving": forms.DateInput(attrs={"type": "date"}),
            "struck_off_date": forms.DateInput(attrs={"type": "date"}),
            "reason_for_leaving": forms.TextInput(),
            "withdrawal_file_no": forms.TextInput(),
            "fees_paid_upto": forms.TextInput(),
            "promoted_to_class": forms.TextInput(),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

    # Fields that must always be known before a TC is issued - a TC missing
    # any of these is administratively incomplete. Fields left optional
    # (annual_exam_result, subjects_offered - not meaningful for Nursery-UKG;
    # fee_concession_nature, ncc_scout, extracurricular_activities - genuinely
    # blank/"No" for most students) are intentionally NOT forced here; the PDF
    # renders sensible "No"/blank fallbacks for those already.
    REQUIRED_FOR_ISSUE = [
        "application_date",
        "date_of_leaving",
        "reason_for_leaving",
        "total_working_days",
        "days_present",
        "fees_paid_upto",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["issue_date"].initial = timezone.localdate()
        for name in self.REQUIRED_FOR_ISSUE:
            self.fields[name].required = True
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        application_date = cleaned.get("application_date")
        date_of_leaving = cleaned.get("date_of_leaving")
        issue_date = cleaned.get("issue_date")
        total_working_days = cleaned.get("total_working_days")
        days_present = cleaned.get("days_present")

        if application_date and issue_date and application_date > issue_date:
            self.add_error("application_date", "Application date cannot be after the TC issue date.")
        if date_of_leaving and issue_date and date_of_leaving > issue_date:
            self.add_error("date_of_leaving", "Date of leaving cannot be after the TC issue date.")
        if total_working_days is not None and days_present is not None and days_present > total_working_days:
            self.add_error("days_present", "Days present cannot exceed total working days.")

        return cleaned


class StaffChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        code = f"Code {obj.legacy_emp_code}" if obj.legacy_emp_code else ""
        details = " | ".join(part for part in [code, obj.designation] if part)
        return f"{obj.full_name} ({details})" if details else obj.full_name


class SalaryPaymentForm(forms.ModelForm):
    staff = StaffChoiceField(queryset=Staff.objects.none())

    class Meta:
        model = SalaryPayment
        fields = [
            "staff",
            "pay_month",
            "payment_date",
            "payment_mode",
            "amount_paid",      # actual cash given — primary clerk field
            "remarks",
            # accounting/advanced fields (pre-filled from staff master)
            "basic_pay",
            "da",
            "other_allowances",
            "pf_deduction",
            "esi_deduction",
            "other_deduction",
            "advance_recovery",
        ]
        widgets = {
            "pay_month": forms.DateInput(attrs={"type": "date"}),
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "remarks": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["staff"].queryset = Staff.objects.filter(is_active=True).order_by("full_name")
        self.fields["staff"].empty_label = "Select staff"
        self.fields["payment_date"].initial = timezone.localdate()
        self.fields["amount_paid"].label = "Aaj ka Payment (₹)"
        self.fields["amount_paid"].required = True
        # Advanced accounting fields are optional — pre-filled via JS from staff master
        for fname in ["basic_pay", "da", "other_allowances", "pf_deduction", "esi_deduction",
                      "other_deduction", "advance_recovery"]:
            self.fields[fname].required = False
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data:
            return cleaned_data

        gross = sum([
            cleaned_data.get("basic_pay", Decimal("0.00")),
            cleaned_data.get("da", Decimal("0.00")),
            cleaned_data.get("other_allowances", Decimal("0.00"))
        ])

        deductions = sum([
            cleaned_data.get("pf_deduction", Decimal("0.00")),
            cleaned_data.get("esi_deduction", Decimal("0.00")),
            cleaned_data.get("other_deduction", Decimal("0.00"))
        ])

        advance_recovery = cleaned_data.get("advance_recovery", Decimal("0.00"))
        net_pay = gross - deductions - advance_recovery

        if net_pay < 0:
            self.add_error("advance_recovery", "Net pay cannot be negative. Advance recovery is too high.")

        return cleaned_data


class LedgerAccountForm(forms.ModelForm):
    class Meta:
        model = LedgerAccount
        fields = ["group", "name", "opening_balance", "opening_balance_date", "is_cash_or_bank", "is_active", "display_order"]
        widgets = {
            "opening_balance_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-control")


class VoucherForm(forms.ModelForm):
    class Meta:
        model = Voucher
        fields = [
            "voucher_date",
            "payment_mode",
            "debit_account",
            "credit_account",
            "amount",
            "paid_to_or_received_from",
            "staff",
            "narration",
            "physical_slip_no",
        ]
        widgets = {
            "voucher_date": forms.DateInput(attrs={"type": "date"}),
            "narration": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        self.voucher_kind = kwargs.pop("voucher_kind", None)
        super().__init__(*args, **kwargs)
        self.fields["voucher_date"].initial = timezone.localdate()

        active_ledgers = LedgerAccount.objects.select_related("group").filter(is_active=True)
        cash_ledgers = active_ledgers.filter(is_cash_or_bank=True)
        expense_ledgers = active_ledgers.filter(group__group_type=AccountGroup.GroupType.EXPENSE)
        advance_ledgers = active_ledgers.filter(group__name__iexact="Advance Given")
        # Liability ledgers cover both directions of a personal loan/advance someone gives the
        # school (e.g. "Pragati Personal/Advance A/C" from the legacy ledger): receiving the loan
        # (a receipt crediting Liability) and repaying it later (an expense debiting Liability).
        # Without this, staff have no way to record either side through Daily Expense / New
        # Other Receipt - a real gap now that expenses/loans are meant to be entered live here.
        liability_ledgers = active_ledgers.filter(group__group_type=AccountGroup.GroupType.LIABILITY)
        expense_payment_ledgers = (expense_ledgers | advance_ledgers | liability_ledgers).distinct()
        income_ledgers = active_ledgers.filter(group__group_type=AccountGroup.GroupType.INCOME)

        if self.voucher_kind == "expense":
            self.fields["credit_account"].queryset = cash_ledgers
            self.fields["debit_account"].queryset = expense_payment_ledgers
            self.fields["credit_account"].empty_label = None
            self.fields["debit_account"].empty_label = "Select expense / advance / loan repayment head"
        elif self.voucher_kind == "receipt":
            income_receipt_ledgers = (income_ledgers | advance_ledgers | liability_ledgers).distinct()
            self.fields["debit_account"].queryset = cash_ledgers
            self.fields["credit_account"].queryset = income_receipt_ledgers
            self.fields["debit_account"].empty_label = None
            self.fields["credit_account"].empty_label = "Select income / advance / loan received head"

        self.fields["staff"].queryset = Staff.objects.filter(is_active=True)
        self.fields["staff"].empty_label = "Select staff"

        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

        if self.voucher_kind == "expense":
            self.fields["paid_to_or_received_from"].widget.attrs.setdefault("list", "staff-name-options")
            self.fields["paid_to_or_received_from"].widget.attrs.setdefault("autocomplete", "off")

    def clean(self):
        cleaned_data = super().clean()
        debit_account = cleaned_data.get("debit_account")
        credit_account = cleaned_data.get("credit_account")
        staff = cleaned_data.get("staff")

        if self.voucher_kind == "expense":
            if credit_account and not credit_account.is_cash_or_bank:
                self.add_error("credit_account", "Expense me payment Cash/Bank account se hi hoga.")
            if debit_account:
                is_expense = debit_account.group.group_type == AccountGroup.GroupType.EXPENSE
                is_advance = debit_account.group.name.lower() == "advance given"
                # Liability: repaying a personal loan/advance someone gave the school (e.g.
                # "Pragati ka paisa wapas kar diya gya") reduces what's owed - a Liability debit,
                # not an Expense. See VoucherForm.__init__ for the fuller reasoning.
                is_liability = debit_account.group.group_type == AccountGroup.GroupType.LIABILITY
                if not (is_expense or is_advance or is_liability):
                    self.add_error("debit_account", "Expense / Advance Head me Expense, Liability, ya Advance Given ledger select kijiye.")
                if debit_account.name.lower() == "staff advance":
                    if not staff:
                        self.add_error("staff", "Staff Advance ke liye staff select kijiye.")
                    else:
                        cleaned_data["paid_to_or_received_from"] = staff.full_name
                else:
                    cleaned_data["staff"] = None
        elif self.voucher_kind == "receipt":
            if debit_account and not debit_account.is_cash_or_bank:
                self.add_error("debit_account", "Receipt me paisa Cash/Bank account me hi aayega.")
            if credit_account:
                is_income = credit_account.group.group_type == AccountGroup.GroupType.INCOME
                is_advance = credit_account.group.name.lower() == "advance given"
                # Liability: receiving a personal loan/advance from someone (e.g. Pragati covering
                # a cash shortfall) is real cash in, but it's not Income - it's a Liability the
                # school now owes back.
                is_liability = credit_account.group.group_type == AccountGroup.GroupType.LIABILITY
                if not (is_income or is_advance or is_liability):
                    self.add_error("credit_account", "Income Head me sirf Income, Liability, ya Advance Given ledger select kijiye.")
                if credit_account.name.lower() == "staff advance":
                    if not staff:
                        self.add_error("staff", "Staff Advance refund ke liye staff select kijiye.")
                    else:
                        cleaned_data["paid_to_or_received_from"] = staff.full_name
                else:
                    cleaned_data["staff"] = None

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.staff_id:
            instance.paid_to_or_received_from = instance.staff.full_name
        if commit:
            instance.save()
        return instance


class VoucherEditForm(VoucherForm):
    edit_reason = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={"class": "form-control"}))

    class Meta(VoucherForm.Meta):
        fields = VoucherForm.Meta.fields + ["edit_reason"]
