from decimal import Decimal

from django import forms
from django.db.models import Max
from django.utils import timezone

from .models import AcademicSession, AccountGroup, FeeHead, FeeReceipt, SalaryPayment, Staff, Student, TransferCertificate, LedgerAccount, Voucher


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
        details = " | ".join(part for part in [sid, class_label, admission] if part)
        status_marker = "" if obj.is_active else " [INACTIVE]"
        return f"{obj.full_name}{status_marker} ({details})"


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "registration_no",
            "admission_no",
            "legacy_sid",
            "admission_date",
            "full_name",
            "current_class",
            "current_section",
            "date_of_birth",
            "gender",
            "father_name",
            "mother_name",
            "category",
            "religion",
            "mobile_primary",
            "mobile_secondary",
            "aadhaar_no",
            "address_local",
            "address_permanent",
            "is_active",
        ]
        widgets = {
            "admission_date": forms.DateInput(attrs={"type": "date"}),
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "address_local": forms.Textarea(attrs={"rows": 2}),
            "address_permanent": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            if "admission_date" not in self.initial:
                self.fields["admission_date"].initial = timezone.localdate()
            if "legacy_sid" not in self.initial:
                max_sid = Student.objects.aggregate(max_sid=Max("legacy_sid"))["max_sid"]
                self.fields["legacy_sid"].initial = (max_sid or 0) + 1
            
        for field_name, field in self.fields.items():
            if field_name != "is_active":
                field.widget.attrs.setdefault("class", "form-control")


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
    def __init__(self, *args, **kwargs):
        self.fee_heads = list(FeeHead.objects.filter(is_active=True).order_by("name"))
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

        if total <= Decimal("0.00"):
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


class TransferCertificateForm(forms.ModelForm):
    class Meta:
        model = TransferCertificate
        fields = [
            "issue_date",
            "date_of_leaving",
            "last_class_studied",
            "last_section",
            "reason_for_leaving",
            "conduct",
            "general_progress",
            "total_working_days",
            "days_present",
            "fees_paid_upto",
            "qualified_for_promotion",
            "promoted_to_class",
            "remarks",
        ]
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "date"}),
            "date_of_leaving": forms.DateInput(attrs={"type": "date"}),
            "reason_for_leaving": forms.TextInput(),
            "fees_paid_upto": forms.TextInput(),
            "promoted_to_class": forms.TextInput(),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["issue_date"].initial = timezone.localdate()
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


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
            "basic_pay",
            "da",
            "other_allowances",
            "pf_deduction",
            "esi_deduction",
            "other_deduction",
            "advance_recovery",
            "remarks",
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
        expense_payment_ledgers = (expense_ledgers | advance_ledgers).distinct()
        income_ledgers = active_ledgers.filter(group__group_type=AccountGroup.GroupType.INCOME)

        if self.voucher_kind == "expense":
            self.fields["credit_account"].queryset = cash_ledgers
            self.fields["debit_account"].queryset = expense_payment_ledgers
            self.fields["credit_account"].empty_label = None
            self.fields["debit_account"].empty_label = "Select expense / advance head"
        elif self.voucher_kind == "receipt":
            income_receipt_ledgers = (income_ledgers | advance_ledgers).distinct()
            self.fields["debit_account"].queryset = cash_ledgers
            self.fields["credit_account"].queryset = income_receipt_ledgers
            self.fields["debit_account"].empty_label = None
            self.fields["credit_account"].empty_label = "Select income / advance head"

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
                if not (is_expense or is_advance):
                    self.add_error("debit_account", "Expense / Advance Head me Expense ya Advance Given ledger select kijiye.")
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
                if not (is_income or is_advance):
                    self.add_error("credit_account", "Income Head me sirf Income ya Advance Given ledger select kijiye.")
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
