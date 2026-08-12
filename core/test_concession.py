"""
Tests for StudentConcession model and its integration with the fee engine.

Scenarios covered:
  1. months_in_range() — unit tests (no DB)
  2. Monthly waiver APR–JUN only: discount applies for JUL/AUG but NOT for months after range
  3. Monthly waiver JUL onwards: zero discount for APR–JUN, correct count from JUL
  4. One-time concession: deducts fixed amount regardless of through_month
  5. Inactive concession: zero discount
  6. full_free: waives entire demand
  7. Sibling-discount applies same month-range logic as monthly_waiver
  8. student_fee_defaults API: active_concession payload in JSON response
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase
from django.urls import reverse

from .fee_engine import calculate_student_due
from .models import (
    ACADEMIC_MONTHS,
    AcademicSession,
    FeeHead,
    FeeStructure,
    SchoolClass,
    Student,
    StudentConcession,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MONEY = lambda x: Decimal(x).quantize(Decimal("0.01"))


def _make_session(name="2026-27"):
    return AcademicSession.objects.create(
        name=name,
        starts_on=date(2026, 4, 1),
        ends_on=date(2027, 3, 31),
        is_active=True,
    )


def _make_student(school_class, admission_date=date(2025, 4, 1)):
    return Student.objects.create(
        full_name="Test Student",
        current_class=school_class,
        admission_date=admission_date,
        is_active=True,
    )


def _make_monthly_head(amount):
    """Create a MONTHLY fee head with a FeeStructure."""
    school_class = SchoolClass.objects.create(name="I", display_order=1)
    session = _make_session()
    student = _make_student(school_class)
    head = FeeHead.objects.create(
        name="Tuition Fee",
        new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
    )
    FeeStructure.objects.create(
        session=session,
        school_class=school_class,
        fee_head=head,
        amount=amount,
        is_active=True,
    )
    return session, school_class, student, head


# ---------------------------------------------------------------------------
# 1. Unit tests for months_in_range (no DB needed)
# ---------------------------------------------------------------------------

class MonthsInRangeTests(TestCase):
    """Test StudentConcession.months_in_range() without touching the DB."""

    def _concession(self, from_month="", to_month=""):
        c = StudentConcession.__new__(StudentConcession)
        c.from_month = from_month
        c.to_month = to_month
        c.is_active = True
        return c

    def test_full_session_no_range(self):
        """Blank from/to → whole session. Through AUG (index 4) = 5 months."""
        c = self._concession()
        self.assertEqual(c.months_in_range(4), 5)  # APR=0..AUG=4

    def test_full_session_through_mar(self):
        """Blank → whole session through MAR (index 11) = 12."""
        c = self._concession()
        self.assertEqual(c.months_in_range(11), 12)

    def test_range_apr_to_jun(self):
        """APR–JUN. Through JUL (index 3) → only APR,MAY,JUN = 3 months."""
        c = self._concession(from_month="APR", to_month="JUN")
        self.assertEqual(c.months_in_range(3), 3)   # target is JUL but range caps at JUN
        self.assertEqual(c.months_in_range(2), 3)   # JUN exactly
        self.assertEqual(c.months_in_range(11), 3)  # MAR — still capped at JUN

    def test_range_jul_to_mar(self):
        """JUL–MAR. Through APR (index 0) → 0 (before range start)."""
        c = self._concession(from_month="JUL", to_month="MAR")
        self.assertEqual(c.months_in_range(0), 0)   # APR — before range
        self.assertEqual(c.months_in_range(2), 0)   # JUN — still before JUL
        self.assertEqual(c.months_in_range(3), 1)   # JUL exactly = 1
        self.assertEqual(c.months_in_range(4), 2)   # AUG = 2
        self.assertEqual(c.months_in_range(11), 9)  # MAR = 9 (JUL..MAR)

    def test_single_month_range(self):
        """from_month == to_month → at most 1 month."""
        c = self._concession(from_month="AUG", to_month="AUG")
        self.assertEqual(c.months_in_range(3), 0)   # before AUG
        self.assertEqual(c.months_in_range(4), 1)   # exactly AUG
        self.assertEqual(c.months_in_range(11), 1)  # after AUG — capped

    def test_only_from_month(self):
        """from_month only → to defaults to MAR (end of session)."""
        c = self._concession(from_month="JUL")
        self.assertEqual(c.months_in_range(2), 0)   # JUN — before JUL
        self.assertEqual(c.months_in_range(11), 9)  # MAR = 9 months (JUL..MAR)

    def test_only_to_month(self):
        """to_month only → from defaults to APR (start of session)."""
        c = self._concession(to_month="JUN")
        self.assertEqual(c.months_in_range(2), 3)   # JUN = 3 months (APR,MAY,JUN)
        self.assertEqual(c.months_in_range(11), 3)  # still capped at JUN


# ---------------------------------------------------------------------------
# 2 & 3. Monthly waiver with month range — fee engine integration
# ---------------------------------------------------------------------------

class MonthlyWaiverFeeEngineTests(TestCase):
    """
    Monthly waiver: per-month discount × months-in-range.
    Uses a single ₹1000/month tuition fee for clarity.
    """

    def setUp(self):
        self.school_class = SchoolClass.objects.create(name="II", display_order=2)
        self.session = _make_session()
        self.student = _make_student(self.school_class)
        self.head = FeeHead.objects.create(
            name="Tuition Fee",
            new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
            old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        )
        FeeStructure.objects.create(
            session=self.session,
            school_class=self.school_class,
            fee_head=self.head,
            amount=Decimal("1000.00"),
            is_active=True,
        )

    def _due(self, month):
        return calculate_student_due(
            student=self.student,
            session=self.session,
            through_month=month,
        )

    def test_monthly_waiver_apr_to_jun_stops_at_range_end(self):
        """
        Waiver ₹500/month APR–JUN only.
        Through APR: demand=1000, waiver=500, due=500.
        Through JUL: demand=4000, waiver=1500 (3 months, range ends JUN), due=2500.
        Through AUG: demand=5000, waiver=1500 (still 3 months), due=3500.
        """
        StudentConcession.objects.create(
            student=self.student,
            session=self.session,
            concession_type="monthly_waiver",
            amount_type="fixed",
            amount=Decimal("500.00"),
            from_month="APR",
            to_month="JUN",
            reason="Test",
            approved_by_name="Principal",
            is_active=True,
        )

        apr = self._due("APR")
        self.assertEqual(apr.policy_concession_amount, MONEY("500.00"))
        self.assertEqual(apr.due_amount, MONEY("500.00"))

        jul = self._due("JUL")
        # 4 months demand = 4000, waiver = 500*3 = 1500
        self.assertEqual(jul.policy_concession_amount, MONEY("1500.00"))
        self.assertEqual(jul.due_amount, MONEY("2500.00"))

        aug = self._due("AUG")
        # 5 months demand = 5000, waiver still = 1500 (range ended JUN)
        self.assertEqual(aug.policy_concession_amount, MONEY("1500.00"))
        self.assertEqual(aug.due_amount, MONEY("3500.00"))

    def test_monthly_waiver_jul_onwards_zero_before_range(self):
        """
        Waiver ₹200/month JUL–MAR.
        Through APR: demand=1000, waiver=0 (before JUL), due=1000.
        Through JUN: demand=3000, waiver=0, due=3000.
        Through JUL: demand=4000, waiver=200, due=3800.
        Through SEP: demand=6000, waiver=600 (3 months), due=5400.
        """
        StudentConcession.objects.create(
            student=self.student,
            session=self.session,
            concession_type="monthly_waiver",
            amount_type="fixed",
            amount=Decimal("200.00"),
            from_month="JUL",
            to_month="MAR",
            reason="Test",
            approved_by_name="Principal",
            is_active=True,
        )

        apr = self._due("APR")
        self.assertEqual(apr.policy_concession_amount, MONEY("0.00"))
        self.assertEqual(apr.due_amount, MONEY("1000.00"))

        jun = self._due("JUN")
        self.assertEqual(jun.policy_concession_amount, MONEY("0.00"))

        jul = self._due("JUL")
        self.assertEqual(jul.policy_concession_amount, MONEY("200.00"))
        self.assertEqual(jul.due_amount, MONEY("3800.00"))

        sep = self._due("SEP")
        # SEP index=5, range JUL(3)..MAR(11), months in range ≤ 5 = JUL,AUG,SEP = 3
        self.assertEqual(sep.policy_concession_amount, MONEY("600.00"))
        self.assertEqual(sep.due_amount, MONEY("5400.00"))

    def test_monthly_waiver_no_range_applies_all_months(self):
        """Blank from/to: waiver applies every month from APR."""
        StudentConcession.objects.create(
            student=self.student,
            session=self.session,
            concession_type="monthly_waiver",
            amount_type="fixed",
            amount=Decimal("100.00"),
            from_month="",
            to_month="",
            reason="Test",
            approved_by_name="Principal",
            is_active=True,
        )

        aug = self._due("AUG")
        # 5 months × ₹100 = ₹500 waiver
        self.assertEqual(aug.policy_concession_amount, MONEY("500.00"))

    def test_percentage_waiver(self):
        """50% monthly waiver APR–MAY (2 months, ₹1000 fee → ₹500/month discount)."""
        StudentConcession.objects.create(
            student=self.student,
            session=self.session,
            concession_type="sibling_discount",
            amount_type="percent",
            amount=Decimal("50"),
            from_month="APR",
            to_month="MAY",
            reason="Sibling",
            approved_by_name="Principal",
            is_active=True,
        )

        may = self._due("MAY")
        # 2 months × 50% × 1000 = 1000 off on 2000 demand
        self.assertEqual(may.policy_concession_amount, MONEY("1000.00"))

        aug = self._due("AUG")
        # range ends MAY — still only 2 months discount
        self.assertEqual(aug.policy_concession_amount, MONEY("1000.00"))


# ---------------------------------------------------------------------------
# 4. One-time concession
# ---------------------------------------------------------------------------

class OneTimeConcessionTests(TestCase):
    def setUp(self):
        self.school_class = SchoolClass.objects.create(name="III", display_order=3)
        self.session = _make_session()
        self.student = _make_student(self.school_class)
        head = FeeHead.objects.create(
            name="Tuition Fee",
            new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
            old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        )
        FeeStructure.objects.create(
            session=self.session,
            school_class=self.school_class,
            fee_head=head,
            amount=Decimal("800.00"),
            is_active=True,
        )

    def _due(self, month):
        return calculate_student_due(
            student=self.student,
            session=self.session,
            through_month=month,
        )

    def test_one_time_deducts_same_amount_regardless_of_month(self):
        """One-time ₹300: same policy_concession_amount for APR, JUL, MAR."""
        StudentConcession.objects.create(
            student=self.student,
            session=self.session,
            concession_type="one_time",
            amount_type="fixed",
            amount=Decimal("300.00"),
            from_month="",
            to_month="",
            reason="Scholarship",
            approved_by_name="Principal",
            is_active=True,
        )

        for month in ("APR", "JUL", "MAR"):
            with self.subTest(month=month):
                result = self._due(month)
                self.assertEqual(
                    result.policy_concession_amount,
                    MONEY("300.00"),
                    msg=f"One-time concession should always be ₹300, got {result.policy_concession_amount} for {month}",
                )


# ---------------------------------------------------------------------------
# 5. Inactive concession → zero discount
# ---------------------------------------------------------------------------

    def test_one_time_starts_from_configured_month(self):
        StudentConcession.objects.create(
            student=self.student,
            session=self.session,
            concession_type="one_time",
            amount_type="fixed",
            amount=Decimal("300.00"),
            from_month="JUL",
            to_month="",
            reason="Scholarship from July",
            approved_by_name="Principal",
            is_active=True,
        )

        self.assertEqual(self._due("JUN").policy_concession_amount, MONEY("0.00"))
        self.assertEqual(self._due("JUL").policy_concession_amount, MONEY("300.00"))
        self.assertEqual(self._due("MAR").policy_concession_amount, MONEY("300.00"))


class InactiveConcessionTests(TestCase):
    def setUp(self):
        self.school_class = SchoolClass.objects.create(name="IV", display_order=4)
        self.session = _make_session()
        self.student = _make_student(self.school_class)
        head = FeeHead.objects.create(
            name="Tuition Fee",
            new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
            old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        )
        FeeStructure.objects.create(
            session=self.session,
            school_class=self.school_class,
            fee_head=head,
            amount=Decimal("500.00"),
            is_active=True,
        )

    def test_inactive_concession_gives_zero_policy_discount(self):
        StudentConcession.objects.create(
            student=self.student,
            session=self.session,
            concession_type="monthly_waiver",
            amount_type="fixed",
            amount=Decimal("500.00"),
            from_month="",
            to_month="",
            reason="Cancelled",
            approved_by_name="Principal",
            is_active=False,  # <-- inactive
        )

        result = calculate_student_due(
            student=self.student,
            session=self.session,
            through_month="AUG",
        )
        self.assertEqual(result.policy_concession_amount, MONEY("0.00"))


# ---------------------------------------------------------------------------
# 6. Full-free concession
# ---------------------------------------------------------------------------

class FullFreeConcessionTests(TestCase):
    def setUp(self):
        self.school_class = SchoolClass.objects.create(name="V", display_order=5)
        self.session = _make_session()
        self.student = _make_student(self.school_class)
        head = FeeHead.objects.create(
            name="Tuition Fee",
            new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
            old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        )
        FeeStructure.objects.create(
            session=self.session,
            school_class=self.school_class,
            fee_head=head,
            amount=Decimal("600.00"),
            is_active=True,
        )

    def test_full_free_waives_entire_demand(self):
        StudentConcession.objects.create(
            student=self.student,
            session=self.session,
            concession_type="full_free",
            amount_type="full",
            amount=None,
            from_month="",
            to_month="",
            reason="Sponsored",
            approved_by_name="Trustee",
            is_active=True,
        )

        result = calculate_student_due(
            student=self.student,
            session=self.session,
            through_month="AUG",
        )
        # Full fee for 5 months = 3000; policy concession = 3000; due = 0
        self.assertEqual(result.policy_concession_amount, result.scheduled_fee_demand)
        self.assertEqual(result.due_amount, MONEY("0.00"))


# ---------------------------------------------------------------------------
# 7. Model.clean() validation
# ---------------------------------------------------------------------------

class ConcessionModelCleanTests(TestCase):
    def setUp(self):
        self.school_class = SchoolClass.objects.create(name="VI", display_order=6)
        self.session = _make_session()
        self.student = Student.objects.create(
            full_name="Clean Test Student",
            current_class=self.school_class,
            admission_date=date(2025, 4, 1),
            is_active=True,
        )

    def _base(self, **kwargs):
        defaults = dict(
            student=self.student,
            session=self.session,
            concession_type="monthly_waiver",
            amount_type="fixed",
            amount=Decimal("100"),
            from_month="",
            to_month="",
            reason="Test",
            approved_by_name="Principal",
            is_active=True,
        )
        defaults.update(kwargs)
        return StudentConcession(**defaults)

    def test_one_time_percent_raises(self):
        from django.core.exceptions import ValidationError
        c = self._base(concession_type="one_time", amount_type="percent", amount=Decimal("50"))
        with self.assertRaises(ValidationError) as ctx:
            c.clean()
        self.assertIn("amount_type", ctx.exception.message_dict)

    def test_full_free_percent_raises(self):
        from django.core.exceptions import ValidationError
        c = self._base(concession_type="full_free", amount_type="percent", amount=Decimal("50"))
        with self.assertRaises(ValidationError) as ctx:
            c.clean()
        self.assertIn("amount_type", ctx.exception.message_dict)

    def test_to_month_before_from_month_raises(self):
        from django.core.exceptions import ValidationError
        c = self._base(from_month="AUG", to_month="APR")
        with self.assertRaises(ValidationError) as ctx:
            c.clean()
        self.assertIn("to_month", ctx.exception.message_dict)

    def test_valid_concession_cleans_ok(self):
        c = self._base(from_month="APR", to_month="JUN")
        c.clean()  # Should not raise

    def test_full_type_blanks_amount(self):
        c = self._base(amount_type="full", amount=Decimal("999"))
        c.clean()
        self.assertIsNone(c.amount)


# ---------------------------------------------------------------------------
# 8. student_fee_defaults API: active_concession in response
# ---------------------------------------------------------------------------

class StudentFeeDefaultsApiConcessionTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="tester_conc", email="tc@example.com", password="pass"
        )
        self.client.force_login(self.user)

        self.school_class = SchoolClass.objects.create(name="VII", display_order=7)
        self.session = _make_session()
        self.student = Student.objects.create(
            full_name="API Concession Student",
            current_class=self.school_class,
            admission_date=date(2025, 4, 1),
            is_active=True,
        )
        head = FeeHead.objects.create(
            name="Tuition Fee",
            new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
            old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        )
        FeeStructure.objects.create(
            session=self.session,
            school_class=self.school_class,
            fee_head=head,
            amount=Decimal("500.00"),
            is_active=True,
        )

    def _get_defaults(self, month="APR"):
        return self.client.get(
            reverse("core:student_fee_defaults", args=[self.student.id]),
            {"session": self.session.id, "from_month": "APR", "month": month},
        )

    def test_no_concession_active_concession_is_null(self):
        response = self._get_defaults()
        data = response.json()
        self.assertIsNone(data.get("active_concession"))

    def test_active_concession_returned_in_json(self):
        StudentConcession.objects.create(
            student=self.student,
            session=self.session,
            concession_type="monthly_waiver",
            amount_type="fixed",
            amount=Decimal("200.00"),
            from_month="APR",
            to_month="JUN",
            reason="Merit scholarship",
            approved_by_name="Principal",
            is_active=True,
        )

        response = self._get_defaults()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        ac = data.get("active_concession")

        self.assertIsNotNone(ac, "active_concession should be present in response")
        self.assertIn("Monthly Fee Waiver", ac["type"])
        self.assertIn("200", ac["amount"])
        self.assertIn("APR", ac["month_range"])
        self.assertIn("JUN", ac["month_range"])
        self.assertEqual(ac["approved_by"], "Principal")

    def test_inactive_concession_not_returned(self):
        StudentConcession.objects.create(
            student=self.student,
            session=self.session,
            concession_type="monthly_waiver",
            amount_type="fixed",
            amount=Decimal("200.00"),
            from_month="",
            to_month="",
            reason="Cancelled",
            approved_by_name="Principal",
            is_active=False,
        )

        response = self._get_defaults()
        data = response.json()
        self.assertIsNone(data.get("active_concession"))
