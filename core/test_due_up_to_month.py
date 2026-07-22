from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .pdf import (
    _DUE_SLIP_GUARDIAN_ENGLISH_NOTE,
    _DUE_SLIP_GUARDIAN_MESSAGE_LINES,
    _due_slip_public_fee_rows,
)
from .models import (
    AcademicSession,
    FeeHead,
    FeeReceipt,
    FeeStructure,
    SchoolClass,
    SchoolProfile,
    Section,
    Student,
)


def pdf_page_count(pdf_bytes):
    return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))


class DueUpToMonthViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="due-admin",
            email="due@example.com",
            password="testpass123",
        )
        self.client.force_login(self.user)
        self.session = AcademicSession.objects.create(
            name="2026-27",
            starts_on=date(2026, 4, 1),
            ends_on=date(2027, 3, 31),
            is_active=True,
        )
        self.school_class = SchoolClass.objects.create(name="I", display_order=1)
        self.section = Section.objects.create(school_class=self.school_class, name="A")
        SchoolProfile.objects.create(
            name="THPS English Medium School",
            address_line1="Dudahi, Kushinagar",
            phone="9999999999",
            is_active=True,
        )
        tuition = FeeHead.objects.create(
            name="Tuition Fee",
            frequency=FeeHead.Frequency.MONTHLY,
            applies_to=FeeHead.AppliesTo.BOTH,
            new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
            old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        )
        admission = FeeHead.objects.create(
            name="Admission Fee",
            frequency=FeeHead.Frequency.ONE_TIME,
            applies_to=FeeHead.AppliesTo.NEW,
            new_student_charge_rule=FeeHead.ChargeRule.ADMISSION_MONTH,
            old_student_charge_rule=FeeHead.ChargeRule.NOT_APPLICABLE,
        )
        FeeStructure.objects.create(
            session=self.session,
            school_class=self.school_class,
            fee_head=tuition,
            amount=Decimal("700.00"),
            is_active=True,
        )
        FeeStructure.objects.create(
            session=self.session,
            school_class=self.school_class,
            fee_head=admission,
            amount=Decimal("800.00"),
            is_active=True,
        )
        self.old_student = Student.objects.create(
            legacy_sid=2505,
            admission_no="2505",
            full_name="JAMAL AHMAD",
            father_name="MD ASLAM",
            current_class=self.school_class,
            current_section=self.section,
            admission_date=date(2025, 4, 11),
            is_active=True,
        )
        self.new_student = Student.objects.create(
            legacy_sid=2609,
            admission_no="2609",
            full_name="ADITYA",
            father_name="GAUTAM KUSHWAHA",
            current_class=self.school_class,
            current_section=self.section,
            admission_date=date(2026, 5, 5),
            is_active=True,
        )
        self.inactive_student = Student.objects.create(
            legacy_sid=2393,
            full_name="INACTIVE STUDENT",
            current_class=self.school_class,
            current_section=self.section,
            admission_date=date(2025, 4, 1),
            is_active=False,
        )
        self.missing_date_student = Student.objects.create(
            legacy_sid=9998,
            full_name="MISSING DATE",
            current_class=self.school_class,
            current_section=self.section,
            admission_date=None,
            is_active=True,
        )
        FeeReceipt.objects.create(
            receipt_no="JUL-OLD",
            student=self.old_student,
            session=self.session,
            receipt_date=date(2026, 7, 10),
            received_amount=Decimal("1000.00"),
            concession_amount=Decimal("100.00"),
        )
        FeeReceipt.objects.create(
            receipt_no="JUL-NEW",
            student=self.new_student,
            session=self.session,
            receipt_date=date(2026, 7, 11),
            received_amount=Decimal("4000.00"),
        )
        FeeReceipt.objects.create(
            receipt_no="AUG-FUTURE",
            student=self.old_student,
            session=self.session,
            receipt_date=date(2026, 8, 1),
            received_amount=Decimal("999.00"),
        )
        FeeReceipt.objects.create(
            receipt_no="JUL-CANCELLED",
            student=self.old_student,
            session=self.session,
            receipt_date=date(2026, 7, 12),
            received_amount=Decimal("999.00"),
            is_cancelled=True,
        )

    def params(self, **overrides):
        values = {
            "session": self.session.id,
            "class": self.school_class.id,
            "section": self.section.id,
            "month": "JUL",
            "status": "active",
            "balance": "all",
        }
        values.update(overrides)
        return values

    def test_report_uses_fee_engine_and_separates_due_from_credit(self):
        response = self.client.get(reverse("core:due_up_to_month_report"), self.params())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Due up to Month")
        self.assertContains(response, "JAMAL AHMAD")
        self.assertContains(response, "ADITYA")
        self.assertEqual(response.context["target_label"], "July 2026")
        self.assertEqual(response.context["total_students"], 2)
        self.assertEqual(len(response.context["skipped"]), 1)
        self.assertContains(response, "Active only")
        self.assertContains(response, "Due Slips (8/A4)")
        self.assertNotContains(response, "Due Slips (4/A4)")
        self.assertNotContains(response, ">Inactive</option>")
        self.assertNotContains(response, ">All</option>")
        totals = response.context["totals"]
        self.assertEqual(totals["gross_demand"], Decimal("6400.00"))
        self.assertEqual(totals["received_amount"], Decimal("5000.00"))
        self.assertEqual(totals["concession_amount"], Decimal("100.00"))
        self.assertEqual(totals["due_amount"], Decimal("1700.00"))
        self.assertEqual(totals["credit_amount"], Decimal("400.00"))

    def test_balance_filter_and_active_only_scope(self):
        due_response = self.client.get(
            reverse("core:due_up_to_month_report"),
            self.params(balance="due"),
        )
        self.assertContains(due_response, "JAMAL AHMAD")
        self.assertNotContains(due_response, "ADITYA")

        for attempted_status in ("inactive", "all"):
            with self.subTest(attempted_status=attempted_status):
                response = self.client.get(
                    reverse("core:due_up_to_month_report"),
                    self.params(status=attempted_status, balance="all"),
                )
                self.assertContains(response, "JAMAL AHMAD")
                self.assertContains(response, "ADITYA")
                self.assertNotContains(response, "INACTIVE STUDENT")
                self.assertEqual(response.context["selected_status"], "active")
                self.assertEqual(response.context["candidate_count"], 3)
                self.assertEqual(response.context["calculated_count"], 2)
                self.assertEqual(response.context["total_students"], 2)
                self.assertContains(response, "restricted to active students")

    def test_invalid_month_is_safe_and_visible(self):
        response = self.client.get(
            reverse("core:due_up_to_month_report"),
            self.params(month="NOT-A-MONTH"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["filter_errors"])
        self.assertContains(response, "Selected target month is invalid")

    def test_report_and_eight_up_slip_pdfs(self):
        for index in range(8):
            Student.objects.create(
                legacy_sid=3000 + index,
                full_name=f"EXTRA DUE {index}",
                father_name="TEST FATHER",
                current_class=self.school_class,
                current_section=self.section,
                admission_date=date(2025, 4, 1),
                is_active=True,
            )

        report_response = self.client.get(
            reverse("core:due_up_to_month_report_pdf"),
            self.params(),
        )
        slip_response = self.client.get(
            reverse("core:due_slip_pdf"),
            self.params(),
        )

        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response["Content-Type"], "application/pdf")
        self.assertGreaterEqual(pdf_page_count(report_response.content), 1)
        self.assertEqual(slip_response.status_code, 200)
        self.assertEqual(slip_response["Content-Type"], "application/pdf")
        self.assertEqual(pdf_page_count(slip_response.content), 2)

    def test_guardian_due_slip_summary_never_exposes_concession_or_payment(self):
        result = SimpleNamespace(
            through_month="JUL",
            gross_demand=Decimal("2800.00"),
            due_amount=Decimal("1700.00"),
        )

        rows = _due_slip_public_fee_rows(result, "July 2026")
        visible_text = " ".join(str(value) for row in rows for value in row).lower()

        self.assertEqual(rows[0][1], "Rs. 2,800.00")
        self.assertEqual(rows[1][1], "Rs. 1,700.00")
        self.assertNotIn("concession", visible_text)
        self.assertNotIn("discount", visible_text)
        self.assertNotIn("amount paid", visible_text)

    def test_guardian_due_slip_uses_exact_motivational_footer(self):
        message = " ".join(_DUE_SLIP_GUARDIAN_MESSAGE_LINES)

        self.assertEqual(
            message,
            "आपके बच्चे का उज्ज्वल भविष्य ही हमारा लक्ष्य है। "
            "समय पर शुल्क जमा कर उनकी शिक्षा-यात्रा को निरंतर और सशक्त बनाएँ। "
            "आपके विश्वास और सहयोग के लिए THPS परिवार हृदय से आभारी है।",
        )
        self.assertEqual(
            _DUE_SLIP_GUARDIAN_ENGLISH_NOTE,
            "Please deposit the amount due at the school office and collect the official receipt.",
        )
        self.assertIn("बच्चे", message)
        self.assertIn("शिक्षा", message)
        self.assertIn("विश्वास", message)
        self.assertNotIn("concession", message.lower())

    def test_report_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("core:due_up_to_month_report"), self.params())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login"), response["Location"])
