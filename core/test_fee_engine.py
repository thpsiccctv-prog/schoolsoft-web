from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .fee_engine import _fixed_month_installments, calculate_student_due
from .models import (
    AcademicSession,
    FeeHead,
    FeeReceipt,
    FeeStructure,
    SchoolClass,
    Student,
    StudentOpeningBalance,
    StudentTransport,
)


class FeeEngineTestCase(TestCase):
    def setUp(self):
        self.session = AcademicSession.objects.create(
            name="2026-27",
            starts_on=date(2026, 4, 1),
            ends_on=date(2027, 3, 31),
        )
        self.school_class = SchoolClass.objects.create(name="I", display_order=1)
        self.old_student = Student.objects.create(
            legacy_sid=2505,
            admission_no="2505",
            full_name="JAMAL AHMAD",
            current_class=self.school_class,
            admission_date=date(2025, 4, 11),
        )
        self.new_student = Student.objects.create(
            legacy_sid=2609,
            admission_no="2609",
            full_name="ADITYA",
            current_class=self.school_class,
            admission_date=date(2026, 5, 5),
        )

        self._add_structure(
            name="Tuition Fee",
            amount="700.00",
            frequency=FeeHead.Frequency.MONTHLY,
            new_rule=FeeHead.ChargeRule.MONTHLY,
            old_rule=FeeHead.ChargeRule.MONTHLY,
        )
        self._add_structure(
            name="Admission Fee",
            amount="800.00",
            frequency=FeeHead.Frequency.ONE_TIME,
            applies_to=FeeHead.AppliesTo.NEW,
            new_rule=FeeHead.ChargeRule.ADMISSION_MONTH,
            old_rule=FeeHead.ChargeRule.NOT_APPLICABLE,
        )
        self._add_structure(
            name="One-time Fee Group",
            amount="1200.00",
            frequency=FeeHead.Frequency.ONE_TIME,
            new_rule=FeeHead.ChargeRule.ADMISSION_MONTH,
            old_rule=FeeHead.ChargeRule.FIXED_MONTHS,
            old_months=["JUL"],
        )
        self._add_structure(
            name="Exam Fee",
            amount="750.00",
            frequency=FeeHead.Frequency.INSTALLMENT,
            new_rule=FeeHead.ChargeRule.FIXED_MONTHS,
            old_rule=FeeHead.ChargeRule.FIXED_MONTHS,
            new_months=["SEP", "DEC", "MAR"],
            old_months=["SEP", "DEC", "MAR"],
        )

    def _add_structure(
        self,
        *,
        name,
        amount,
        frequency,
        new_rule,
        old_rule,
        applies_to=FeeHead.AppliesTo.BOTH,
        new_months=None,
        old_months=None,
        is_active=True,
    ):
        head = FeeHead.objects.create(
            name=name,
            frequency=frequency,
            applies_to=applies_to,
            new_student_charge_rule=new_rule,
            old_student_charge_rule=old_rule,
            new_student_charge_months=new_months or [],
            old_student_charge_months=old_months or [],
        )
        return FeeStructure.objects.create(
            session=self.session,
            school_class=self.school_class,
            fee_head=head,
            amount=Decimal(amount),
            is_active=is_active,
            source=FeeStructure.Source.FINAL_SHEET,
            source_reference="FINAL.xlsx/2-Class Fee/test",
        )

    def test_july_demand_derives_new_and_old_status(self):
        old_result = calculate_student_due(
            student=self.old_student,
            session=self.session,
            through_month="JUL",
        )
        new_result = calculate_student_due(
            student=self.new_student,
            session=self.session,
            through_month="JUL",
        )

        self.assertFalse(old_result.is_new_student)
        self.assertEqual(old_result.scheduled_fee_demand, Decimal("4000.00"))
        self.assertEqual(old_result.due_amount, Decimal("4000.00"))
        self.assertTrue(new_result.is_new_student)
        self.assertEqual(new_result.scheduled_fee_demand, Decimal("4800.00"))
        self.assertEqual(new_result.due_amount, Decimal("4800.00"))

    def test_amount_and_concession_produce_due_and_credit_without_legacy_previous_due(self):
        FeeReceipt.objects.create(
            receipt_no="2026-27/SF-53",
            student=self.new_student,
            session=self.session,
            receipt_date=date(2026, 5, 5),
            from_month="APRIL",
            to_month="MARCH",
            received_amount=Decimal("3000.00"),
            concession_amount=Decimal("2150.00"),
            previous_due_amount=Decimal("6000.00"),
            carried_forward=True,
        )
        FeeReceipt.objects.create(
            receipt_no="2026-27/SF-65",
            student=self.old_student,
            session=self.session,
            receipt_date=date(2026, 5, 7),
            from_month="APRIL",
            to_month="MARCH",
            received_amount=Decimal("3000.00"),
            concession_amount=Decimal("1150.00"),
            previous_due_amount=Decimal("6200.00"),
            carried_forward=True,
        )

        aditya = calculate_student_due(
            student=self.new_student,
            session=self.session,
            through_month="JUL",
        )
        jamal = calculate_student_due(
            student=self.old_student,
            session=self.session,
            through_month="JUL",
        )

        self.assertEqual(aditya.due_amount, Decimal("0.00"))
        self.assertEqual(aditya.credit_amount, Decimal("350.00"))
        self.assertEqual(jamal.due_amount, Decimal("0.00"))
        self.assertEqual(jamal.credit_amount, Decimal("150.00"))

    def test_receipt_cutoff_cancellation_and_late_fee(self):
        FeeReceipt.objects.create(
            receipt_no="VALID-JUL",
            student=self.old_student,
            session=self.session,
            receipt_date=date(2026, 7, 15),
            received_amount=Decimal("1000.00"),
            concession_amount=Decimal("100.00"),
            late_fee_amount=Decimal("50.00"),
        )
        FeeReceipt.objects.create(
            receipt_no="FUTURE-AUG",
            student=self.old_student,
            session=self.session,
            receipt_date=date(2026, 8, 1),
            received_amount=Decimal("999.00"),
        )
        FeeReceipt.objects.create(
            receipt_no="CANCELLED-JUL",
            student=self.old_student,
            session=self.session,
            receipt_date=date(2026, 7, 20),
            received_amount=Decimal("999.00"),
            is_cancelled=True,
        )

        result = calculate_student_due(
            student=self.old_student,
            session=self.session,
            through_month="JUL",
        )

        self.assertEqual(result.late_fee_amount, Decimal("50.00"))
        self.assertEqual(result.received_amount, Decimal("1000.00"))
        self.assertEqual(result.concession_amount, Decimal("100.00"))
        self.assertEqual(result.due_amount, Decimal("2950.00"))

    def test_exam_amount_is_annual_total_split_across_three_months(self):
        august = calculate_student_due(
            student=self.old_student,
            session=self.session,
            through_month="AUG",
        )
        september = calculate_student_due(
            student=self.old_student,
            session=self.session,
            through_month="SEP",
        )
        december = calculate_student_due(
            student=self.old_student,
            session=self.session,
            through_month="DEC",
        )
        march = calculate_student_due(
            student=self.old_student,
            session=self.session,
            through_month="MAR",
        )

        self.assertEqual(august.scheduled_fee_demand, Decimal("4700.00"))
        self.assertEqual(september.scheduled_fee_demand, Decimal("5650.00"))
        self.assertEqual(december.scheduled_fee_demand, Decimal("8000.00"))
        self.assertEqual(march.scheduled_fee_demand, Decimal("10350.00"))

    def test_fixed_month_rounding_remainder_goes_to_final_installment(self):
        installments = _fixed_month_installments(Decimal("100.00"), ["MAR", "SEP", "DEC"])

        self.assertEqual(installments["SEP"], Decimal("33.33"))
        self.assertEqual(installments["DEC"], Decimal("33.33"))
        self.assertEqual(installments["MAR"], Decimal("33.34"))
        self.assertEqual(sum(installments.values()), Decimal("100.00"))

    def test_transport_uses_only_confirmed_month_windows_and_allows_zero(self):
        StudentTransport.objects.create(
            student=self.old_student,
            session=self.session,
            monthly_amount=Decimal("300.00"),
            start_month="APR",
            billing_confirmed=True,
        )
        StudentTransport.objects.create(
            student=self.old_student,
            session=self.session,
            monthly_amount=Decimal("900.00"),
            start_month="APR",
            billing_confirmed=False,
        )
        zero_assignment = StudentTransport(
            student=self.new_student,
            session=self.session,
            monthly_amount=Decimal("0.00"),
            start_month="APR",
            billing_confirmed=True,
            note="Confirmed free transport",
        )
        zero_assignment.full_clean()
        zero_assignment.save()

        old_result = calculate_student_due(
            student=self.old_student,
            session=self.session,
            through_month="JUL",
        )
        new_result = calculate_student_due(
            student=self.new_student,
            session=self.session,
            through_month="JUL",
        )

        self.assertEqual(old_result.transport_demand, Decimal("1200.00"))
        self.assertEqual(new_result.transport_demand, Decimal("0.00"))

    def test_confirmed_transport_windows_cannot_overlap(self):
        first = StudentTransport(
            student=self.old_student,
            session=self.session,
            monthly_amount=Decimal("300.00"),
            start_month="APR",
            end_month="JUL",
            billing_confirmed=True,
        )
        first.full_clean()
        first.save()
        overlapping = StudentTransport(
            student=self.old_student,
            session=self.session,
            monthly_amount=Decimal("400.00"),
            start_month="JUL",
            end_month="SEP",
            billing_confirmed=True,
        )

        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_opening_balance_is_explicit_and_stale_structure_is_inactive(self):
        StudentOpeningBalance.objects.create(
            student=self.old_student,
            session=self.session,
            amount=Decimal("2750.00"),
            as_of_date=date(2026, 4, 1),
            source_reference="2025-26/SF-1000",
        )
        stale_head = FeeHead.objects.create(
            name="Stale Bootstrap Fee",
            new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
            old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        )
        stale_structure = FeeStructure.objects.create(
            session=self.session,
            school_class=self.school_class,
            fee_head=stale_head,
            amount=Decimal("999.00"),
        )

        result = calculate_student_due(
            student=self.old_student,
            session=self.session,
            through_month="JUL",
        )

        self.assertFalse(stale_structure.is_active)
        self.assertEqual(result.opening_balance_amount, Decimal("2750.00"))
        self.assertEqual(result.due_amount, Decimal("6750.00"))

    def test_missing_admission_date_blocks_new_old_derivation(self):
        student = Student.objects.create(
            full_name="Missing Admission Date",
            current_class=self.school_class,
        )

        with self.assertRaises(ValidationError):
            calculate_student_due(student=student, session=self.session, through_month="JUL")


class FeeEngineModelValidationTests(TestCase):
    def setUp(self):
        self.session = AcademicSession.objects.create(
            name="2026-27",
            starts_on=date(2026, 4, 1),
            ends_on=date(2027, 3, 31),
        )
        self.school_class = SchoolClass.objects.create(name="I")
        self.student = Student.objects.create(
            full_name="Validation Student",
            current_class=self.school_class,
            admission_date=date(2025, 4, 1),
        )

    def test_fixed_month_rule_requires_months(self):
        head = FeeHead(
            name="Broken Exam",
            frequency=FeeHead.Frequency.INSTALLMENT,
            new_student_charge_rule=FeeHead.ChargeRule.FIXED_MONTHS,
            old_student_charge_rule=FeeHead.ChargeRule.FIXED_MONTHS,
        )

        with self.assertRaises(ValidationError):
            head.full_clean()

    def test_opening_balance_is_unique_and_nonnegative(self):
        StudentOpeningBalance.objects.create(
            student=self.student,
            session=self.session,
            amount=Decimal("100.00"),
            as_of_date=date(2026, 4, 1),
            source_reference="verified",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentOpeningBalance.objects.create(
                student=self.student,
                session=self.session,
                amount=Decimal("50.00"),
                as_of_date=date(2026, 4, 1),
                source_reference="duplicate",
            )

        negative = StudentOpeningBalance(
            student=self.student,
            session=self.session,
            amount=Decimal("-1.00"),
            as_of_date=date(2026, 4, 1),
            source_reference="invalid",
        )
        with self.assertRaises(ValidationError):
            negative.full_clean()


class FeeEnginePreflightCommandTests(TestCase):
    def setUp(self):
        self.session = AcademicSession.objects.create(name="2026-27")
        self.student = Student.objects.create(full_name="Preflight Student")

    def _receipt(self, **overrides):
        values = {
            "receipt_no": f"PREFLIGHT-{FeeReceipt.objects.count() + 1}",
            "student": self.student,
            "session": self.session,
            "receipt_date": date(2026, 7, 1),
        }
        values.update(overrides)
        return FeeReceipt.objects.create(**values)

    def test_preflight_passes_when_deprecated_fields_are_unused(self):
        self._receipt()
        output = StringIO()

        call_command("check_fee_engine_preflight", stdout=output)

        self.assertIn("preflight PASS", output.getvalue())

    def test_preflight_blocks_nonzero_previous_due(self):
        self._receipt(previous_due_amount=Decimal("1.00"))

        with self.assertRaises(CommandError):
            call_command("check_fee_engine_preflight")

    def test_preflight_blocks_carried_forward(self):
        self._receipt(carried_forward=True)

        with self.assertRaises(CommandError):
            call_command("check_fee_engine_preflight")
