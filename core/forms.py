from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import AcademicSession, FeeHead, FeeReceipt, SalaryPayment, Staff, Student, TransferCertificate


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
        ).order_by("full_name")
        self.fields["session"].queryset = AcademicSession.objects.order_by("-is_active", "-starts_on", "name")
        self.fields["receipt_date"].initial = timezone.localdate()
        self.fields["student"].empty_label = "Select student"
        self.fields["session"].empty_label = "Select session"

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
