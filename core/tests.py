from datetime import date, timedelta
from decimal import Decimal
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .access import READONLY_GROUP

from .forms import VoucherForm
from .whatsapp import build_wa_link, fee_due_message, normalize_indian_mobile
from .models import (
    AccountGroup,
    AcademicSession,
    DisciplineRecord,
    ExamMark,
    ExamTerm,
    ExamTest,
    Family,
    FeeHead,
    FeeReceipt,
    FeeReceiptLine,
    FeeStructure,
    House,
    InventoryIssue,
    InventoryItem,
    LedgerAccount,
    SalaryPayment,
    SchoolClass,
    SchoolProfile,
    Section,
    Staff,
    Student,
    StudentTransport,
    Subject,
    TransferCertificate,
    TransportBus,
    TransportRoute,
    Voucher,
)


def pdf_page_count(pdf_bytes):
    return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))


class AuthenticatedClientMixin:
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(
            username="tester",
            email="tester@example.com",
            password="testpass123",
        )
        self.client.force_login(self.user)


class WorkspaceAuthTests(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login"), response["Location"])


class DashboardTests(AuthenticatedClientMixin, TestCase):
    def test_dashboard_loads(self):
        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_superuser_sees_all_kpis_and_tiles(self):
        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertSetEqual(
            {kpi["label"] for kpi in response.context["dashboard_kpis"]},
            {"Today's Collection", "Today's Expense", "Total Dues", "Active Students"},
        )
        self.assertSetEqual(
            {tile["label"] for tile in response.context["tiles"]},
            {
                "Fee Collection", "Students", "Receipts", "Dues", "Marks",
                "Collection", "Fee Setup", "Staff", "Transport", "School Profile",
            },
        )
        self.assertContains(response, "New Fee Receipt")

    def test_student_list_loads(self):
        response = self.client.get(reverse("core:student_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Students")

    def test_numeric_student_identifier_takes_priority_over_mobile_suffix(self):
        exact = Student.objects.create(
            full_name="Exact SID Student", legacy_sid=2290, admission_no="2290", is_active=True
        )
        Student.objects.create(
            full_name="Mobile Suffix Student", legacy_sid=2248, mobile_primary="9915972290", is_active=True
        )

        response = self.client.get(reverse("core:student_list"), {"q": "2290"})

        self.assertContains(response, exact.full_name)
        self.assertNotContains(response, "Mobile Suffix Student")

    def test_student_detail_loads_from_list(self):
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(
            legacy_sid=1001,
            admission_no="A-1001",
            full_name="Detail Student",
            father_name="Detail Father",
            current_class=school_class,
            mobile_primary="9999999999",
        )

        list_response = self.client.get(reverse("core:student_list"), {"q": "Detail Student"})
        detail_response = self.client.get(reverse("core:student_detail", args=[student.id]))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, reverse("core:student_detail", args=[student.id]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Detail Student")
        self.assertContains(detail_response, "Detail Father")
        self.assertContains(detail_response, "Form PDF")
        self.assertContains(detail_response, "Marksheet")

    def test_school_profile_page_loads(self):
        SchoolProfile.objects.create(
            legacy_comp_code=9,
            name="THPS ENGLISH MEDIUM SCHOOL",
            address_line1="DUDAHI 274302",
            address_line2="KUSHINAGAR",
            address_line3="(U.P)",
            phone="7379568527",
            email="thpses@gmail.com",
            current_year="2026-27",
            is_active=True,
        )

        response = self.client.get(reverse("core:school_profile_detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "THPS ENGLISH MEDIUM SCHOOL")
        self.assertContains(response, "7379568527")
        self.assertContains(response, "thpses@gmail.com")
        self.assertContains(response, "2026-27")

    def test_fee_structure_report_loads_and_filters(self):
        session = AcademicSession.objects.create(name="2026-27", is_active=True)
        class_one = SchoolClass.objects.create(name="I", display_order=1)
        class_two = SchoolClass.objects.create(name="II", display_order=2)
        tuition = FeeHead.objects.create(name="Tuition Fee")
        zero_head = FeeHead.objects.create(name="Zero Fee")
        FeeStructure.objects.create(
            session=session,
            school_class=class_one,
            fee_head=tuition,
            amount=Decimal("500.00"),
        )
        FeeStructure.objects.create(
            session=session,
            school_class=class_one,
            fee_head=zero_head,
            amount=Decimal("0.00"),
        )
        FeeStructure.objects.create(
            session=session,
            school_class=class_two,
            fee_head=tuition,
            amount=Decimal("700.00"),
        )

        response = self.client.get(reverse("core:fee_structure_report"), {"class": class_one.id})
        all_rows_response = self.client.get(
            reverse("core:fee_structure_report"),
            {"class": class_one.id, "rows": "all"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fee Structure")
        self.assertContains(response, "Tuition Fee")
        self.assertContains(response, "500.00")
        self.assertNotContains(response, "700.00")
        self.assertNotContains(response, "Zero Fee")

        self.assertEqual(all_rows_response.status_code, 200)
        self.assertContains(all_rows_response, "Zero Fee")


def _grant_module_permissions(user, *module_codenames):
    perms = Permission.objects.filter(content_type__app_label="core", codename__in=module_codenames)
    user.user_permissions.set(list(perms))


class DashboardPermissionTests(TestCase):
    def test_restricted_user_only_sees_permitted_modules(self):
        user = get_user_model().objects.create_user(username="student_desk_user", password="pw12345")
        _grant_module_permissions(user, "access_dashboard", "access_students")
        self.client.force_login(user)

        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Academics")
        self.assertNotContains(response, "Finance")
        self.assertNotContains(response, "Operations")
        self.assertNotContains(response, "Administration")
        self.assertEqual(
            [kpi["label"] for kpi in response.context["dashboard_kpis"]],
            ["Active Students"],
        )
        self.assertEqual([tile["label"] for tile in response.context["tiles"]], ["Students"])

    def test_restricted_dashboard_skips_unauthorized_finance_queries(self):
        user = get_user_model().objects.create_user(username="query_guard_user", password="pw12345")
        _grant_module_permissions(user, "access_dashboard", "access_students")
        self.client.force_login(user)

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("core:dashboard"))

        sql = "\n".join(query["sql"].lower() for query in queries.captured_queries)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("core_feereceipt", sql)
        self.assertNotIn("core_voucher", sql)

    def test_readonly_user_does_not_see_write_only_fee_collection_actions(self):
        user = get_user_model().objects.create_user(username="viewer_user", password="pw12345")
        _grant_module_permissions(user, "access_dashboard", "access_fee_collection", "access_students")
        readonly_group, _ = Group.objects.get_or_create(name=READONLY_GROUP)
        user.groups.add(readonly_group)
        self.client.force_login(user)

        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "New Fee Receipt")
        self.assertNotContains(response, "Daily counter receipt desk")
        self.assertNotContains(response, reverse("core:receipt_create"))
        self.assertEqual(
            [kpi["label"] for kpi in response.context["dashboard_kpis"]],
            ["Today's Collection", "Active Students"],
        )
        self.assertEqual([tile["label"] for tile in response.context["tiles"]], ["Students"])

    def test_readonly_accounts_user_keeps_reports_but_not_write_links(self):
        user = get_user_model().objects.create_user(username="accounts_viewer", password="pw12345")
        _grant_module_permissions(user, "access_dashboard", "access_accounts")
        readonly_group, _ = Group.objects.get_or_create(name=READONLY_GROUP)
        user.groups.add(readonly_group)
        self.client.force_login(user)

        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("core:expense_create"))
        self.assertNotContains(response, reverse("core:receipt_other_create"))
        self.assertContains(response, reverse("core:voucher_list"))
        self.assertContains(response, reverse("core:cash_book"))

    def test_user_with_no_module_access_is_blocked(self):
        user = get_user_model().objects.create_user(username="no_access_user", password="pw12345")
        self.client.force_login(user)

        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 403)


class PreviousCollectionDayTests(AuthenticatedClientMixin, TestCase):
    """Stage 2: safe 'previous collection day' context under Today's Collection.
    No zyada/kam delta - see dashboard() in views.py for why."""

    def setUp(self):
        super().setUp()
        self.session = AcademicSession.objects.create(name="2025-26")
        self.school_class = SchoolClass.objects.create(name="V", display_order=1)
        self.student = Student.objects.create(full_name="Prev Day Student", current_class=self.school_class)
        self.today = timezone.localdate()

    def _receipt(self, receipt_no, days_ago, amount, is_cancelled=False):
        return FeeReceipt.objects.create(
            receipt_no=receipt_no,
            student=self.student,
            session=self.session,
            receipt_date=self.today - timedelta(days=days_ago),
            received_amount=Decimal(amount),
            legacy_net_total=Decimal(amount),
            is_cancelled=is_cancelled,
        )

    def _today_kpi(self, response):
        for kpi in response.context["dashboard_kpis"]:
            if kpi["label"] == "Today's Collection":
                return kpi
        return None

    def test_no_history_hides_context(self):
        response = self.client.get(reverse("core:dashboard"))

        kpi = self._today_kpi(response)
        self.assertIsNotNone(kpi)
        self.assertIsNone(kpi["prev_date"])
        self.assertNotContains(response, "Pichhla collection day")
        self.assertNotContains(response, "din pehle hui thi")

    def test_cancelled_receipts_are_not_treated_as_collection_days(self):
        self._receipt("CANC-1", days_ago=2, amount="500.00", is_cancelled=True)

        response = self.client.get(reverse("core:dashboard"))

        kpi = self._today_kpi(response)
        self.assertIsNone(kpi["prev_date"])

    def test_zero_amount_receipts_do_not_count_as_a_collection_day(self):
        self._receipt("ZERO-1", days_ago=1, amount="0.00")

        response = self.client.get(reverse("core:dashboard"))

        kpi = self._today_kpi(response)
        self.assertIsNone(kpi["prev_date"])

    def test_most_recent_valid_day_is_picked_and_summed(self):
        self._receipt("OLD-1", days_ago=10, amount="1000.00")
        self._receipt("RECENT-1", days_ago=3, amount="300.00")
        self._receipt("RECENT-2", days_ago=3, amount="200.00")
        # A same-day zero-amount receipt shouldn't change the total.
        self._receipt("RECENT-ZERO", days_ago=3, amount="0.00")

        response = self.client.get(reverse("core:dashboard"))

        kpi = self._today_kpi(response)
        self.assertEqual(kpi["prev_date"], self.today - timedelta(days=3))
        self.assertEqual(kpi["prev_total"], Decimal("500.00"))
        self.assertContains(response, "Pichhla collection day")

    def test_13_days_ago_shows_date_and_amount(self):
        self._receipt("D13", days_ago=13, amount="750.00")

        response = self.client.get(reverse("core:dashboard"))

        kpi = self._today_kpi(response)
        self.assertEqual(kpi["prev_days_ago"], 13)
        self.assertEqual(kpi["prev_total"], Decimal("750.00"))
        self.assertContains(response, "Pichhla collection day")

    def test_14_days_ago_shows_days_ago_only_no_amount(self):
        self._receipt("D14", days_ago=14, amount="750.00")

        response = self.client.get(reverse("core:dashboard"))

        kpi = self._today_kpi(response)
        self.assertEqual(kpi["prev_days_ago"], 14)
        self.assertIsNone(kpi["prev_total"])
        self.assertContains(response, "14 din pehle hui thi")
        self.assertNotContains(response, "750")


class FeeReceiptTests(AuthenticatedClientMixin, TestCase):
    def test_payable_amount_uses_lines_late_fee_and_concession(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Test Student", current_class=school_class)
        tuition = FeeHead.objects.create(name="Tuition Fee")
        exam = FeeHead.objects.create(name="Exam Fee")
        receipt = FeeReceipt.objects.create(
            receipt_no="R-1",
            student=student,
            session=session,
            concession_amount=Decimal("20.00"),
            late_fee_amount=Decimal("5.00"),
            received_amount=Decimal("185.00"),
        )
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=tuition, amount=Decimal("150.00"))
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=exam, amount=Decimal("50.00"))

        self.assertEqual(receipt.line_total, Decimal("200.00"))
        self.assertEqual(receipt.payable_amount, Decimal("185.00"))

    def test_receipt_pages_load(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Test Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")
        receipt = FeeReceipt.objects.create(
            receipt_no="R-2",
            student=student,
            session=session,
            received_amount=Decimal("100.00"),
            legacy_fee_total=Decimal("100.00"),
            legacy_net_total=Decimal("100.00"),
        )
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=fee_head, amount=Decimal("100.00"))

        list_response = self.client.get(reverse("core:receipt_list"))
        detail_response = self.client.get(reverse("core:receipt_detail", args=[receipt.id]))
        pdf_response = self.client.get(reverse("core:receipt_pdf", args=[receipt.id]))

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertContains(detail_response, "R-2")

    def test_receipt_pdf_stays_one_page_for_dense_fee_heads(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="III", display_order=3)
        student = Student.objects.create(
            legacy_sid=2408,
            admission_no="2408",
            full_name="Dense Receipt Student",
            current_class=school_class,
        )
        fee_items = [
            ("Admission Fee", "800.00"),
            ("Building Fee", "300.00"),
            ("Development Fee", "500.00"),
            ("Exam Fee", "250.00"),
            ("Generator Fee", "100.00"),
            ("Lab Fee", "200.00"),
            ("Library Fee", "50.00"),
            ("Medical Fee", "250.00"),
            ("Science Fee", "400.00"),
            ("Sports Fee", "300.00"),
            ("Tuition Fee", "800.00"),
        ]
        receipt = FeeReceipt.objects.create(
            receipt_no="DENSE-1",
            student=student,
            session=session,
            from_month="APR",
            to_month="APR",
            received_amount=Decimal("0.00"),
            legacy_fee_total=Decimal("3950.00"),
            legacy_net_total=Decimal("3950.00"),
            legacy_due_amount=Decimal("3950.00"),
        )
        for name, amount in fee_items:
            FeeReceiptLine.objects.create(
                receipt=receipt,
                fee_head=FeeHead.objects.create(name=name),
                amount=Decimal(amount),
            )

        pdf_response = self.client.get(reverse("core:receipt_pdf", args=[receipt.id]))

        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_page_count(pdf_response.content), 1)

    def test_receipt_list_filters(self):
        session = AcademicSession.objects.create(name="2026-27")
        class_one = SchoolClass.objects.create(name="I", display_order=1)
        class_two = SchoolClass.objects.create(name="II", display_order=2)
        first_student = Student.objects.create(full_name="First Fee Student", current_class=class_one)
        second_student = Student.objects.create(full_name="Second Fee Student", current_class=class_two)
        FeeReceipt.objects.create(
            receipt_no="FILTER-1",
            student=first_student,
            session=session,
            receipt_date="2026-07-01",
            payment_mode=FeeReceipt.PaymentMode.CASH,
            received_amount=Decimal("100.00"),
            legacy_net_total=Decimal("100.00"),
        )
        FeeReceipt.objects.create(
            receipt_no="FILTER-2",
            student=second_student,
            session=session,
            receipt_date="2026-08-01",
            payment_mode=FeeReceipt.PaymentMode.ONLINE,
            received_amount=Decimal("200.00"),
            legacy_net_total=Decimal("200.00"),
        )

        response = self.client.get(
            reverse("core:receipt_list"),
            {
                "date_from": "2026-07-01",
                "date_to": "2026-07-31",
                "class": class_one.id,
                "payment_mode": FeeReceipt.PaymentMode.CASH,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FILTER-1")
        self.assertContains(response, "First Fee Student")
        self.assertNotContains(response, "FILTER-2")
        self.assertNotContains(response, "Second Fee Student")

    def test_manual_receipt_create(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        section = Section.objects.create(school_class=school_class, name="A")
        student = Student.objects.create(full_name="Test Student", current_class=school_class, current_section=section)
        fee_head = FeeHead.objects.create(name="Tuition Fee")

        get_response = self.client.get(reverse("core:receipt_create"))
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "Student Search")
        self.assertContains(get_response, "data-fee-total")

        post_response = self.client.post(
            reverse("core:receipt_create"),
            data={
                "student": student.id,
                "session": session.id,
                "receipt_date": "2026-07-01",
                "from_month": "JULY",
                "to_month": "JULY",
                "payment_mode": FeeReceipt.PaymentMode.CASH,
                "concession_amount": "10.00",
                "late_fee_amount": "0.00",
                "received_amount": "90.00",
                "remarks": "Test receipt",
                f"fee_head_{fee_head.id}": "100.00",
            },
        )

        receipt = FeeReceipt.objects.get(remarks="Test receipt")
        self.assertRedirects(post_response, reverse("core:receipt_detail", args=[receipt.id]))
        self.assertEqual(receipt.receipt_no[:3], "MR-")
        self.assertEqual(receipt.legacy_net_total, Decimal("90.00"))
        self.assertEqual(receipt.lines.count(), 1)
        self.assertEqual(receipt.student_name_snapshot, "Test Student")
        self.assertEqual(receipt.class_snapshot, "I")
        self.assertEqual(receipt.section_snapshot, "A")

        student.full_name = "Changed Student"
        student.current_class = SchoolClass.objects.create(name="II", display_order=2)
        student.current_section = Section.objects.create(school_class=student.current_class, name="B")
        student.save()

        detail_response = self.client.get(reverse("core:receipt_detail", args=[receipt.id]))
        self.assertContains(detail_response, "Test Student")
        self.assertContains(detail_response, "I-A")
        self.assertNotContains(detail_response, "Changed Student")

    def test_student_fee_defaults_api(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Test Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")
        FeeStructure.objects.create(
            session=session,
            school_class=school_class,
            fee_head=fee_head,
            amount=Decimal("500.00"),
        )

        response = self.client.get(
            reverse("core:student_fee_defaults", args=[student.id]),
            {"session": session.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["amounts"][f"fee_head_{fee_head.id}"], "500.00")

    def test_due_report_loads(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Due Student", current_class=school_class)
        FeeReceipt.objects.create(
            receipt_no="DUE-1",
            student=student,
            session=session,
            received_amount=Decimal("50.00"),
            legacy_net_total=Decimal("100.00"),
            legacy_due_amount=Decimal("50.00"),
        )

        response = self.client.get(reverse("core:due_report"))
        pdf_response = self.client.get(reverse("core:due_report_pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertContains(response, "Due Report")
        self.assertContains(response, "Due Student")

class Month2DocumentTests(AuthenticatedClientMixin, TestCase):
    def test_admission_form_pdf(self):
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Doc Student", current_class=school_class)

        response = self.client.get(reverse("core:admission_form_pdf", args=[student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_character_certificate_pdf(self):
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Doc Student", current_class=school_class)

        response = self.client.get(reverse("core:character_certificate_pdf", args=[student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_tc_create_and_pdf(self):
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Leaving Student", current_class=school_class)

        get_response = self.client.get(reverse("core:tc_detail", args=[student.id]))
        self.assertEqual(get_response.status_code, 200)

        post_response = self.client.post(
            reverse("core:tc_detail", args=[student.id]),
            data={
                "issue_date": "2026-07-01",
                "last_class_studied": school_class.id,
                "last_section": "",
                "reason_for_leaving": "Family relocation",
                "conduct": TransferCertificate.Conduct.GOOD,
                "general_progress": TransferCertificate.Conduct.GOOD,
                "qualified_for_promotion": "on",
                "promoted_to_class": "",
                "fees_paid_upto": "June 2026",
                "remarks": "",
            },
        )
        self.assertRedirects(post_response, reverse("core:tc_detail", args=[student.id]))

        tc = TransferCertificate.objects.get(student=student)
        self.assertTrue(tc.tc_number.startswith("TC-"))
        self.assertEqual(tc.sr_no, student.scholar_register_no)

        pdf_response = self.client.get(reverse("core:tc_pdf", args=[student.id]))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")

    def test_scholar_register_pdf_active_student_without_tc(self):
        """An active student who has never left should still get a Scholar
        Register PDF (it's the office's permanent record from admission,
        not a leaving document like the TC)."""
        school_class = SchoolClass.objects.create(name="III", display_order=1)
        student = Student.objects.create(
            full_name="Active Register Student",
            current_class=school_class,
            admission_date=date(2024, 6, 1),
            scholar_register_no="2402",
        )

        response = self.client.get(reverse("core:scholar_register_pdf", args=[student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_scholar_register_pdf_with_transfer_certificate(self):
        """A student who has left should have their Scholar Register row
        reflect the TC's exit class/date/reason/conduct."""
        school_class = SchoolClass.objects.create(name="V", display_order=1)
        student = Student.objects.create(
            full_name="Left Register Student",
            current_class=school_class,
            admission_date=date(2023, 4, 10),
            scholar_register_no="2199",
        )
        TransferCertificate.objects.create(
            student=student,
            tc_number="TC-TEST-0001",
            issue_date=date(2026, 7, 1),
            last_class_studied=school_class,
            reason_for_leaving="Family relocation",
            conduct=TransferCertificate.Conduct.GOOD,
            general_progress=TransferCertificate.Conduct.GOOD,
            qualified_for_promotion=True,
            fees_paid_upto="June 2026",
        )

        response = self.client.get(reverse("core:scholar_register_pdf", args=[student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_scholar_register_pdf_handles_blank_optional_fields(self):
        """No crash when DOB, admission_date, current_class, address, or
        Aadhaar are blank - common for older/legacy student records."""
        student = Student.objects.create(full_name="Bare Minimum Student")

        response = self.client.get(reverse("core:scholar_register_pdf", args=[student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_marksheet_pdf(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Marks Student", current_class=school_class)
        subject = Subject.objects.create(name="Mathematics")
        term = ExamTerm.objects.create(session=session, name="Half Yearly")
        exam_test = ExamTest.objects.create(
            term=term,
            school_class=school_class,
            subject=subject,
            max_marks=Decimal("100.00"),
        )
        ExamMark.objects.create(exam_test=exam_test, student=student, marks_obtained=Decimal("85.00"))

        select_response = self.client.get(reverse("core:marksheet_select", args=[student.id]))
        self.assertEqual(select_response.status_code, 200)
        self.assertContains(select_response, "Half Yearly")

        pdf_response = self.client.get(reverse("core:marksheet_pdf", args=[student.id, term.id]))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")

    def test_marks_report_loads_and_filters(self):
        session = AcademicSession.objects.create(name="2026-27")
        class_one = SchoolClass.objects.create(name="I", display_order=1)
        class_two = SchoolClass.objects.create(name="II", display_order=2)
        first_student = Student.objects.create(
            full_name="Marks Report Student",
            father_name="Report Father",
            current_class=class_one,
        )
        second_student = Student.objects.create(full_name="Other Report Student", current_class=class_two)
        subject = Subject.objects.create(name="Mathematics")
        term = ExamTerm.objects.create(session=session, name="Quarterly")
        first_test = ExamTest.objects.create(
            term=term,
            school_class=class_one,
            subject=subject,
            max_marks=Decimal("100.00"),
        )
        second_test = ExamTest.objects.create(
            term=term,
            school_class=class_two,
            subject=subject,
            max_marks=Decimal("100.00"),
        )
        ExamMark.objects.create(
            exam_test=first_test,
            student=first_student,
            marks_obtained=Decimal("80.00"),
        )
        ExamMark.objects.create(
            exam_test=second_test,
            student=second_student,
            marks_obtained=Decimal("70.00"),
        )

        response = self.client.get(
            reverse("core:marks_report"),
            {"term": term.id, "class": class_one.id, "q": "Marks Report"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marks Report Student")
        self.assertContains(response, "80.00")
        self.assertContains(response, "PDF")
        self.assertNotContains(response, "Other Report Student")

    def test_exam_mark_auto_grade(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Grade Student", current_class=school_class)
        subject = Subject.objects.create(name="Science")
        term = ExamTerm.objects.create(session=session, name="Annual")
        exam_test = ExamTest.objects.create(
            term=term,
            school_class=school_class,
            subject=subject,
            max_marks=Decimal("100.00"),
        )
        mark = ExamMark.objects.create(exam_test=exam_test, student=student, marks_obtained=Decimal("92.00"))

        self.assertEqual(mark.grade, "A1")

    def test_receipt_cancellation_workflow(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Cancel Student", current_class=school_class)
        receipt = FeeReceipt.objects.create(
            receipt_no="CANCEL-1",
            student=student,
            session=session,
            received_amount=Decimal("100.00"),
            legacy_net_total=Decimal("100.00"),
            legacy_due_amount=Decimal("0.00"),
        )
        
        # Test permission: Viewer cannot cancel
        viewer = get_user_model().objects.create_user(username="viewer", password="pw")
        self.client.force_login(viewer)
        cancel_response = self.client.post(reverse("core:receipt_cancel", args=[receipt.id]), {"cancel_reason": "Test"})
        self.assertEqual(cancel_response.status_code, 403)
        
        # Admin can cancel
        self.client.force_login(self.user)
        # GET should render confirm template
        get_confirm = self.client.get(reverse("core:receipt_cancel", args=[receipt.id]))
        self.assertEqual(get_confirm.status_code, 200)
        self.assertContains(get_confirm, "Cancel / Void Receipt CANCEL-1")
        
        # POST without reason should fail
        post_fail = self.client.post(reverse("core:receipt_cancel", args=[receipt.id]), {"cancel_reason": ""})
        self.assertContains(post_fail, "A cancellation reason is required.")
        
        # POST with reason should succeed
        post_success = self.client.post(reverse("core:receipt_cancel", args=[receipt.id]), {"cancel_reason": "Mistake"})
        self.assertRedirects(post_success, reverse("core:receipt_detail", args=[receipt.id]))
        
        receipt.refresh_from_db()
        self.assertTrue(receipt.is_cancelled)
        self.assertEqual(receipt.cancel_reason, "Mistake")
        self.assertEqual(receipt.cancelled_by, self.user)
        self.assertIsNotNone(receipt.cancelled_at)
        
        # PDF should still generate
        pdf_response = self.client.get(reverse("core:receipt_pdf", args=[receipt.id]))
        self.assertEqual(pdf_response.status_code, 200)

    def test_cancelled_receipts_excluded_from_reports(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Exclude Student", current_class=school_class)
        FeeReceipt.objects.create(
            receipt_no="EXCLUDE-1",
            student=student,
            session=session,
            received_amount=Decimal("200.00"),
            legacy_net_total=Decimal("200.00"),
            legacy_due_amount=Decimal("50.00"),
            is_cancelled=True,
            cancel_reason="Voided"
        )
        
        # Collection report
        col_response = self.client.get(reverse("core:collection_report"))
        self.assertNotContains(col_response, "EXCLUDE-1")
        
        # Due report shouldn't include this as due amount because the receipt query itself filters out is_cancelled=False, 
        # so this receipt won't appear. Wait, if a receipt is cancelled, it's ignored for due_report.
        # But actually, due_report in this app is driven by receipt rows holding `legacy_due_amount` > 0.
        due_response = self.client.get(reverse("core:due_report"))
        self.assertNotContains(due_response, "EXCLUDE-1")
        
        # Receipt list should still list it but not include it in totals
        list_response = self.client.get(reverse("core:receipt_list"))
        self.assertContains(list_response, "EXCLUDE-1")
        # Total received should not include the 200.00
        # If no other receipts, it should be 0 or empty depending on how it's rendered, but we know 200.00 shouldn't be there as a total.

    def test_receipt_edit_workflow(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Edit Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")
        receipt = FeeReceipt.objects.create(
            receipt_no="EDIT-1",
            student=student,
            session=session,
            received_amount=Decimal("100.00"),
            legacy_fee_total=Decimal("100.00"),
            legacy_net_total=Decimal("100.00"),
            legacy_due_amount=Decimal("0.00"),
            from_month="JAN",
            to_month="MAR"
        )
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=fee_head, amount=Decimal("100.00"))
        
        # Admin edits receipt
        self.client.force_login(self.user)
        get_edit = self.client.get(reverse("core:receipt_edit", args=[receipt.id]))
        self.assertEqual(get_edit.status_code, 200)
        self.assertContains(get_edit, "Correct Fee Receipt")
        
        post_edit = self.client.post(
            reverse("core:receipt_edit", args=[receipt.id]),
            data={
                "receipt_date": "2026-07-02",
                "payment_mode": FeeReceipt.PaymentMode.ONLINE,
                "concession_amount": "0.00",
                "late_fee_amount": "0.00",
                "received_amount": "150.00",
                "remarks": "Updated amount",
                "edit_reason": "Wrong amount entered",
                f"fee_head_{fee_head.id}": "150.00",
                "line_total": "150.00"
            },
        )
        self.assertRedirects(post_edit, reverse("core:receipt_detail", args=[receipt.id]))
        
        receipt.refresh_from_db()
        self.assertTrue(receipt.is_edited)
        self.assertEqual(receipt.edit_reason, "Wrong amount entered")
        self.assertEqual(receipt.received_amount, Decimal("150.00"))
        self.assertEqual(receipt.legacy_net_total, Decimal("150.00"))
        
        # Check audit log
        self.assertEqual(receipt.audit_logs.count(), 1)
        log = receipt.audit_logs.first()
        self.assertEqual(log.action, "edited")
        self.assertEqual(log.reason, "Wrong amount entered")
        self.assertEqual(log.changes["received_amount"]["before"], "100.00")
        self.assertEqual(log.changes["received_amount"]["after"], "150.00")
        
        
class AccountsTests(AuthenticatedClientMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.session = AcademicSession.objects.create(
            name="2026-27",
            starts_on="2026-04-01",
            ends_on="2027-03-31",
            is_active=True,
        )
        cash_group = AccountGroup.objects.create(name="Cash & Bank", group_type=AccountGroup.GroupType.ASSET)
        advance_group = AccountGroup.objects.create(name="Advance Given", group_type=AccountGroup.GroupType.ASSET)

        self.cash_ledger = LedgerAccount.objects.create(
            group=cash_group,
            name="Cash in Hand",
            is_cash_or_bank=True,
            opening_balance=Decimal("100.00"),
            opening_balance_date="2026-04-01",
        )
        self.staff_advance_ledger = LedgerAccount.objects.create(
            group=advance_group,
            name="Staff Advance",
        )
        self.staff = Staff.objects.create(full_name="RAVINDRA SINGH", designation="Driver")

    def test_staff_advance_requires_staff(self):
        form = VoucherForm(
            data={
                "voucher_date": "2026-07-06",
                "payment_mode": Voucher.PaymentMode.CASH,
                "debit_account": self.staff_advance_ledger.id,
                "credit_account": self.cash_ledger.id,
                "amount": "256.50",
                "paid_to_or_received_from": "",
                "staff": "",
                "narration": "advance",
                "physical_slip_no": "",
            },
            voucher_kind="expense",
        )

        self.assertFalse(form.is_valid())
        self.assertIn("staff", form.errors)

    def test_staff_advance_saves_staff_snapshot(self):
        form = VoucherForm(
            data={
                "voucher_date": "2026-07-06",
                "payment_mode": Voucher.PaymentMode.CASH,
                "debit_account": self.staff_advance_ledger.id,
                "credit_account": self.cash_ledger.id,
                "amount": "256.50",
                "paid_to_or_received_from": "",
                "staff": self.staff.id,
                "narration": "staff advance",
                "physical_slip_no": "",
            },
            voucher_kind="expense",
        )

        self.assertTrue(form.is_valid(), form.errors)
        voucher = form.save(commit=False)
        self.assertEqual(voucher.staff, self.staff)
        self.assertEqual(voucher.paid_to_or_received_from, "RAVINDRA SINGH")


class StaffTests(AuthenticatedClientMixin, TestCase):
    def test_staff_list_loads(self):
        Staff.objects.create(full_name="Test Teacher", designation="Teacher", basic_pay=Decimal("15000.00"))

        response = self.client.get(reverse("core:staff_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Teacher")

    def test_staff_detail_and_filters(self):
        active_staff = Staff.objects.create(
            legacy_emp_code=1,
            full_name="Active Teacher",
            designation="Teacher",
            staff_type=Staff.StaffType.TEACHING,
            phone="9999999999",
            basic_pay=Decimal("1.00"),
        )
        Staff.objects.create(
            legacy_emp_code=2,
            full_name="Left Clerk",
            staff_type=Staff.StaffType.ADMIN,
            is_active=False,
        )

        list_response = self.client.get(
            reverse("core:staff_list"),
            {"staff_type": Staff.StaffType.TEACHING, "status": "active"},
        )
        detail_response = self.client.get(reverse("core:staff_detail", args=[active_staff.id]))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Active Teacher")
        self.assertNotContains(list_response, "Left Clerk")
        self.assertContains(list_response, reverse("core:staff_detail", args=[active_staff.id]))

        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Active Teacher")
        self.assertContains(detail_response, "Salary Defaults")
        self.assertContains(detail_response, "legacy placeholder values")
        self.assertContains(detail_response, "No salary payments recorded yet.")

    def test_salary_payment_create_and_pdf(self):
        staff = Staff.objects.create(
            full_name="Pay Teacher",
            designation="Teacher",
            basic_pay=Decimal("15000.00"),
            da=Decimal("1000.00"),
            other_allowances=Decimal("500.00"),
        )

        get_response = self.client.get(reverse("core:salary_payment_create"))
        self.assertEqual(get_response.status_code, 200)

        post_response = self.client.post(
            reverse("core:salary_payment_create"),
            data={
                "staff": staff.id,
                "pay_month": "2026-07-01",
                "payment_date": "2026-07-05",
                "payment_mode": SalaryPayment.PaymentMode.CASH,
                "basic_pay": "15000.00",
                "da": "1000.00",
                "other_allowances": "500.00",
                "pf_deduction": "1200.00",
                "esi_deduction": "0.00",
                "other_deduction": "0.00",
                "advance_recovery": "0.00",
                "remarks": "July salary",
            },
        )
        if post_response.status_code == 200:
            print("Form errors:", post_response.context['form'].errors)

        payment = SalaryPayment.objects.get(staff=staff)
        self.assertRedirects(post_response, reverse("core:salary_payment_detail", args=[payment.id]))
        self.assertTrue(payment.slip_no.startswith("SAL-"))
        self.assertEqual(payment.gross_pay, Decimal("16500.00"))
        self.assertEqual(payment.net_pay, Decimal("15300.00"))

        pdf_response = self.client.get(reverse("core:salary_payslip_pdf", args=[payment.id]))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")

    def test_salary_negative_net_pay(self):
        staff = Staff.objects.create(
            full_name="Negative Pay Teacher",
            designation="Teacher",
            basic_pay=Decimal("10000.00"),
        )

        post_response = self.client.post(
            reverse("core:salary_payment_create"),
            data={
                "staff": staff.id,
                "pay_month": "2026-07-01",
                "payment_date": "2026-07-05",
                "payment_mode": SalaryPayment.PaymentMode.CASH,
                "basic_pay": "10000.00",
                "da": "0.00",
                "other_allowances": "0.00",
                "pf_deduction": "12000.00",
                "esi_deduction": "0.00",
                "other_deduction": "0.00",
                "advance_recovery": "0.00",
                "remarks": "July salary",
            },
        )
        self.assertContains(post_response, "Net pay cannot be negative")

    def test_salary_duplicate_prevention(self):
        staff = Staff.objects.create(
            full_name="Duplicate Teacher",
            designation="Teacher",
            basic_pay=Decimal("10000.00"),
        )
        SalaryPayment.objects.create(
            staff=staff,
            pay_month="2026-07-01",
            payment_date="2026-07-05",
            payment_mode=SalaryPayment.PaymentMode.CASH,
            basic_pay=Decimal("10000.00"),
        )
        
        post_response = self.client.post(
            reverse("core:salary_payment_create"),
            data={
                "staff": staff.id,
                "pay_month": "2026-07-01",
                "payment_date": "2026-07-05",
                "payment_mode": SalaryPayment.PaymentMode.CASH,
                "basic_pay": "10000.00",
                "da": "0.00",
                "other_allowances": "0.00",
                "pf_deduction": "0.00",
                "esi_deduction": "0.00",
                "other_deduction": "0.00",
                "advance_recovery": "0.00",
            },
        )
        self.assertContains(post_response, "already exists")


class TransportTests(AuthenticatedClientMixin, TestCase):
    def test_transport_list_loads(self):
        school_class = SchoolClass.objects.create(name="VIII", display_order=8)
        student = Student.objects.create(
            legacy_sid=2,
            full_name="Transport Student",
            father_name="Test Father",
            current_class=school_class,
        )
        bus = TransportBus.objects.create(name="Bus 01", vehicle_no="MARSHAL")
        route = TransportRoute.objects.create(name="Shahpur", monthly_charge=Decimal("400.00"))
        StudentTransport.objects.create(
            student=student,
            route=route,
            bus=bus,
            legacy_route_name="Shahpur",
            legacy_bus_label="MARSHAL",
            stop_name="Main Chowk",
        )
        inactive_student = Student.objects.create(
            legacy_sid=3,
            full_name="Inactive Transport Student",
            father_name="Old Father",
            current_class=school_class,
        )
        StudentTransport.objects.create(
            student=inactive_student,
            route=route,
            bus=bus,
            legacy_route_name="Shahpur",
            legacy_bus_label="MARSHAL",
            stop_name="Old Stop",
            is_active=False,
            is_transport_enabled=False,
        )

        response = self.client.get(reverse("core:transport_list"))
        search_response = self.client.get(reverse("core:transport_list"), {"q": "Transport"})
        all_status_response = self.client.get(reverse("core:transport_list"), {"status": "all"})
        route_response = self.client.get(reverse("core:transport_list"), {"route": route.id, "status": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(all_status_response.status_code, 200)
        self.assertEqual(route_response.status_code, 200)
        self.assertContains(response, "Transport Student")
        self.assertContains(response, "Shahpur")
        self.assertContains(response, "MARSHAL")
        self.assertContains(response, reverse("core:student_detail", args=[student.id]))
        self.assertContains(response, "Enabled")
        self.assertNotContains(response, "Old Stop")
        self.assertContains(all_status_response, "Old Stop")
        self.assertContains(route_response, "2")
        self.assertContains(route_response, "Legacy BUS_APPLICABLE")


class HouseAssignmentTests(AuthenticatedClientMixin, TestCase):
    def test_new_student_form_suggests_least_populated_active_house(self):
        school_class = SchoolClass.objects.create(name="II", display_order=1)
        red = House.objects.create(name="Red House", display_order=1)
        blue = House.objects.create(name="Blue House", display_order=2)
        # Red already has 2 students, Blue has 0 - Blue should be suggested.
        Student.objects.create(full_name="Existing One", current_class=school_class, house=red)
        Student.objects.create(full_name="Existing Two", current_class=school_class, house=red)

        response = self.client.get(reverse("core:student_create"))

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.fields["house"].initial, blue.pk)

    def test_inactive_house_not_suggested(self):
        school_class = SchoolClass.objects.create(name="III", display_order=1)
        House.objects.create(name="Retired House", display_order=1, is_active=False)
        active_house = House.objects.create(name="Active House", display_order=2)

        response = self.client.get(reverse("core:student_create"))

        form = response.context["form"]
        self.assertEqual(form.fields["house"].initial, active_house.pk)


class DisciplineRecordTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="admin_tester", email="admin@example.com", password="testpass123"
        )
        self.plain_user = get_user_model().objects.create_user(
            username="plain_tester", email="plain@example.com", password="testpass123"
        )
        school_class = SchoolClass.objects.create(name="IV", display_order=1)
        self.student = Student.objects.create(full_name="Discipline Student", current_class=school_class)

    def test_non_admin_blocked_from_discipline_list(self):
        self.client.force_login(self.plain_user)
        response = self.client.get(reverse("core:discipline_list", args=[self.student.id]))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Discipline Records", status_code=403)

    def test_admin_can_create_and_view_discipline_record(self):
        self.client.force_login(self.admin)

        create_response = self.client.post(
            reverse("core:discipline_create", args=[self.student.id]),
            {
                "incident_date": "2026-07-08",
                "category": DisciplineRecord.Category.LATE_COMING,
                "severity": DisciplineRecord.Severity.MINOR,
                "description": "Arrived 20 minutes late without a note.",
                "action_taken": "Verbal warning given.",
            },
        )
        self.assertRedirects(create_response, reverse("core:discipline_list", args=[self.student.id]))

        record = DisciplineRecord.objects.get(student=self.student)
        self.assertEqual(record.reported_by, self.admin)
        self.assertEqual(record.category, DisciplineRecord.Category.LATE_COMING)

        list_response = self.client.get(reverse("core:discipline_list", args=[self.student.id]))
        self.assertContains(list_response, "Late Coming")

        pdf_response = self.client.get(reverse("core:discipline_pdf", args=[self.student.id]))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")


class IdCardTests(AuthenticatedClientMixin, TestCase):
    def test_single_id_card_pdf(self):
        school_class = SchoolClass.objects.create(name="V", display_order=1)
        student = Student.objects.create(full_name="ID Card Student", current_class=school_class)

        response = self.client.get(reverse("core:id_card_pdf", args=[student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_batch_id_card_pdf_respects_class_filter(self):
        class_one = SchoolClass.objects.create(name="VI", display_order=1)
        class_two = SchoolClass.objects.create(name="VII", display_order=2)
        Student.objects.create(full_name="In Class One", current_class=class_one)
        Student.objects.create(full_name="In Class Two", current_class=class_two)

        response = self.client.get(reverse("core:id_card_batch_pdf"), {"class": class_one.id, "status": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_batch_id_card_pdf_empty_result_does_not_crash(self):
        response = self.client.get(reverse("core:id_card_batch_pdf"), {"q": "no-such-student-xyz"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")


class WhatsAppLinkTests(TestCase):
    def test_normalize_ten_digit_number(self):
        self.assertEqual(normalize_indian_mobile("9876543210"), "919876543210")

    def test_normalize_strips_spaces_and_dashes(self):
        self.assertEqual(normalize_indian_mobile("98765 43210"), "919876543210")
        self.assertEqual(normalize_indian_mobile("98765-43210"), "919876543210")

    def test_normalize_leading_zero(self):
        self.assertEqual(normalize_indian_mobile("09876543210"), "919876543210")

    def test_normalize_already_has_country_code(self):
        self.assertEqual(normalize_indian_mobile("919876543210"), "919876543210")

    def test_normalize_rejects_short_garbage(self):
        self.assertIsNone(normalize_indian_mobile("12345"))
        self.assertIsNone(normalize_indian_mobile(""))
        self.assertIsNone(normalize_indian_mobile(None))

    def test_build_wa_link_contains_number_and_message(self):
        link = build_wa_link("9876543210", "Hello there")
        self.assertIsNotNone(link)
        self.assertTrue(link.startswith("https://wa.me/919876543210?text="))
        self.assertIn("Hello", link)

    def test_build_wa_link_none_for_bad_number(self):
        self.assertIsNone(build_wa_link("123", "Hello"))

    def test_fee_due_message_includes_key_details(self):
        message = fee_due_message("Ram Prasad", "Sita Devi", "V", "A", "1234", Decimal("500.00"), "THPS")
        self.assertIn("Ram Prasad", message)
        self.assertIn("Sita Devi", message)
        self.assertIn("500.00", message)
        self.assertIn("1234", message)
        self.assertIn("THPS", message)


class WhatsAppViewIntegrationTests(AuthenticatedClientMixin, TestCase):
    def test_due_report_shows_whatsapp_link_for_student_with_mobile(self):
        school_class = SchoolClass.objects.create(name="V", display_order=1)
        session = AcademicSession.objects.create(name="2025-26", starts_on="2025-04-01", ends_on="2026-03-31")
        student = Student.objects.create(
            full_name="Due WA Student",
            current_class=school_class,
            father_name="Father Name",
            mobile_primary="9876543210",
            admission_no="ADM-WA-1",
        )
        FeeReceipt.objects.create(
            receipt_no="WA-DUE-1",
            student=student,
            session=session,
            received_amount=Decimal("50.00"),
            legacy_net_total=Decimal("100.00"),
            legacy_due_amount=Decimal("50.00"),
        )

        response = self.client.get(reverse("core:due_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "wa.me/919876543210")

    def test_student_detail_shows_fee_reminder_link_when_due(self):
        school_class = SchoolClass.objects.create(name="VI", display_order=1)
        session = AcademicSession.objects.create(name="2025-26", starts_on="2025-04-01", ends_on="2026-03-31")
        student = Student.objects.create(
            full_name="Profile WA Student",
            current_class=school_class,
            father_name="Father Name",
            mobile_primary="9876543210",
        )
        FeeReceipt.objects.create(
            receipt_no="WA-DUE-2",
            student=student,
            session=session,
            received_amount=Decimal("0.00"),
            legacy_net_total=Decimal("100.00"),
            legacy_due_amount=Decimal("100.00"),
        )

        response = self.client.get(reverse("core:student_detail", args=[student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "wa.me/919876543210")

    def test_student_detail_no_crash_without_mobile(self):
        school_class = SchoolClass.objects.create(name="VII", display_order=1)
        student = Student.objects.create(full_name="No Mobile Student", current_class=school_class)

        response = self.client.get(reverse("core:student_detail", args=[student.id]))

        self.assertEqual(response.status_code, 200)


class InventoryTests(AuthenticatedClientMixin, TestCase):
    def test_create_item_and_it_appears_in_catalog(self):
        response = self.client.post(
            reverse("core:inventory_item_create"),
            {"name": "Summer Uniform Set", "category": InventoryItem.Category.UNIFORM, "unit_price": "650.00", "is_active": "on"},
        )
        self.assertRedirects(response, reverse("core:inventory_item_list"))

        item = InventoryItem.objects.get(name="Summer Uniform Set")
        self.assertEqual(item.unit_price, Decimal("650.00"))

        list_response = self.client.get(reverse("core:inventory_item_list"))
        self.assertContains(list_response, "Summer Uniform Set")

    def test_toggle_item_active(self):
        item = InventoryItem.objects.create(name="Notebook Set", category=InventoryItem.Category.BOOK, unit_price=Decimal("120.00"))

        response = self.client.post(reverse("core:inventory_item_toggle_active", args=[item.id]))
        self.assertRedirects(response, reverse("core:inventory_item_list"))

        item.refresh_from_db()
        self.assertFalse(item.is_active)

    def test_issue_item_to_student_snapshots_price_and_supports_concession(self):
        school_class = SchoolClass.objects.create(name="IV", display_order=1)
        student = Student.objects.create(full_name="Inventory Student", current_class=school_class)
        item = InventoryItem.objects.create(name="Winter Sweater", category=InventoryItem.Category.UNIFORM, unit_price=Decimal("400.00"))

        create_response = self.client.post(
            reverse("core:inventory_issue_create", args=[student.id]),
            {
                "item": item.id,
                "issue_date": "2026-07-01",
                "quantity": 1,
                "amount_charged": "200.00",
                "remarks": "Concession - 50% for BPL family",
            },
        )
        self.assertRedirects(create_response, reverse("core:inventory_issue_list", args=[student.id]))

        issue = InventoryIssue.objects.get(student=student, item=item)
        self.assertEqual(issue.unit_price, Decimal("400.00"))
        self.assertEqual(issue.amount_charged, Decimal("200.00"))
        self.assertEqual(issue.concession_amount, Decimal("200.00"))
        self.assertFalse(issue.is_free)
        self.assertEqual(issue.issued_by, self.user)

        list_response = self.client.get(reverse("core:inventory_issue_list", args=[student.id]))
        self.assertContains(list_response, "Winter Sweater")

    def test_free_issue_shows_as_free(self):
        school_class = SchoolClass.objects.create(name="III", display_order=1)
        student = Student.objects.create(full_name="Free Issue Student", current_class=school_class)
        item = InventoryItem.objects.create(name="Shoes", category=InventoryItem.Category.SHOES, unit_price=Decimal("300.00"))

        InventoryIssue.objects.create(student=student, item=item, unit_price=item.unit_price, quantity=1, amount_charged=Decimal("0.00"))

        response = self.client.get(reverse("core:inventory_issue_list", args=[student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Free")

    def test_inventory_report_filters_by_item(self):
        school_class = SchoolClass.objects.create(name="II", display_order=1)
        student_a = Student.objects.create(full_name="Report Student A", current_class=school_class)
        student_b = Student.objects.create(full_name="Report Student B", current_class=school_class)
        book = InventoryItem.objects.create(name="Maths Textbook", category=InventoryItem.Category.BOOK, unit_price=Decimal("150.00"))
        shoes = InventoryItem.objects.create(name="School Shoes", category=InventoryItem.Category.SHOES, unit_price=Decimal("350.00"))
        InventoryIssue.objects.create(student=student_a, item=book, unit_price=book.unit_price, quantity=1, amount_charged=Decimal("150.00"))
        InventoryIssue.objects.create(student=student_b, item=shoes, unit_price=shoes.unit_price, quantity=1, amount_charged=Decimal("350.00"))

        response = self.client.get(reverse("core:inventory_report"), {"item": book.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Report Student A")
        self.assertNotContains(response, "Report Student B")

    def test_inventory_report_empty_does_not_crash(self):
        response = self.client.get(reverse("core:inventory_report"), {"q": "no-such-student-xyz"})

        self.assertEqual(response.status_code, 200)


class FamilyLedgerTests(AuthenticatedClientMixin, TestCase):
    def test_create_family_and_add_student(self):
        school_class = SchoolClass.objects.create(name="V", display_order=1)
        student = Student.objects.create(full_name="Family Student One", current_class=school_class)

        create_response = self.client.post(
            reverse("core:family_create"),
            {"name": "Verma Family", "primary_mobile": "9876543210", "secondary_mobile": "", "address": "", "notes": ""},
        )
        family = Family.objects.get(name="Verma Family")
        self.assertRedirects(create_response, reverse("core:family_detail", args=[family.id]))

        add_response = self.client.post(reverse("core:family_add_student", args=[family.id]), {"student_id": student.id})
        self.assertRedirects(add_response, reverse("core:family_detail", args=[family.id]))

        student.refresh_from_db()
        self.assertEqual(student.family, family)

        detail_response = self.client.get(reverse("core:family_detail", args=[family.id]))
        self.assertContains(detail_response, "Family Student One")

    def test_remove_student_from_family(self):
        school_class = SchoolClass.objects.create(name="VI", display_order=1)
        family = Family.objects.create(name="Singh Family", primary_mobile="9876543210")
        student = Student.objects.create(full_name="Family Student Two", current_class=school_class, family=family)

        response = self.client.post(reverse("core:family_remove_student", args=[family.id, student.id]))
        self.assertRedirects(response, reverse("core:family_detail", args=[family.id]))

        student.refresh_from_db()
        self.assertIsNone(student.family)

    def test_family_detail_shows_combined_due_and_whatsapp_link(self):
        school_class = SchoolClass.objects.create(name="VII", display_order=1)
        session = AcademicSession.objects.create(name="2025-26", starts_on="2025-04-01", ends_on="2026-03-31")
        family = Family.objects.create(name="Yadav Family", primary_mobile="9876543210")
        student_a = Student.objects.create(full_name="Sibling A", current_class=school_class, father_name="Ram Yadav", family=family)
        student_b = Student.objects.create(full_name="Sibling B", current_class=school_class, father_name="Ram Yadav", family=family)
        FeeReceipt.objects.create(
            receipt_no="FAM-DUE-1", student=student_a, session=session,
            received_amount=Decimal("0.00"), legacy_net_total=Decimal("100.00"), legacy_due_amount=Decimal("100.00"),
        )
        FeeReceipt.objects.create(
            receipt_no="FAM-DUE-2", student=student_b, session=session,
            received_amount=Decimal("0.00"), legacy_net_total=Decimal("50.00"), legacy_due_amount=Decimal("50.00"),
        )

        response = self.client.get(reverse("core:family_detail", args=[family.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sibling A")
        self.assertContains(response, "Sibling B")
        self.assertContains(response, "wa.me/919876543210")

    def test_suggestions_group_students_sharing_father_and_mobile(self):
        school_class = SchoolClass.objects.create(name="VIII", display_order=1)
        Student.objects.create(
            full_name="Suggest Sibling A", current_class=school_class,
            father_name="Suresh Kumar", mobile_primary="9999900000",
        )
        Student.objects.create(
            full_name="Suggest Sibling B", current_class=school_class,
            father_name="Suresh Kumar", mobile_primary="9999900000",
        )
        Student.objects.create(
            full_name="Unrelated Student", current_class=school_class,
            father_name="Someone Else", mobile_primary="9111100000",
        )

        response = self.client.get(reverse("core:family_suggestions"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Suggest Sibling A")
        self.assertContains(response, "Suggest Sibling B")
        self.assertNotContains(response, "Unrelated Student")

    def test_create_family_from_suggestion(self):
        school_class = SchoolClass.objects.create(name="IX", display_order=1)
        student_a = Student.objects.create(
            full_name="Suggest Create A", current_class=school_class,
            father_name="Mahesh Prasad", mobile_primary="9888800000",
        )
        student_b = Student.objects.create(
            full_name="Suggest Create B", current_class=school_class,
            father_name="Mahesh Prasad", mobile_primary="9888800000",
        )

        response = self.client.post(
            reverse("core:family_create_from_suggestion"),
            {"name": "Mahesh Prasad", "mobile": "9888800000", "student_ids": [student_a.id, student_b.id]},
        )

        family = Family.objects.get(name="Mahesh Prasad")
        self.assertRedirects(response, reverse("core:family_detail", args=[family.id]))

        student_a.refresh_from_db()
        student_b.refresh_from_db()
        self.assertEqual(student_a.family, family)
        self.assertEqual(student_b.family, family)

    def test_family_list_does_not_crash_when_empty(self):
        response = self.client.get(reverse("core:family_list"))

        self.assertEqual(response.status_code, 200)


# Create your tests here.
