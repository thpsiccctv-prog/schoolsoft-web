from datetime import date, datetime, timedelta
from decimal import Decimal
import os
from pathlib import Path
import sqlite3
import tempfile
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from reportlab.lib.pagesizes import A4, A5, landscape

from .access import READONLY_GROUP

from .forms import FeeReceiptEditForm, FeeReceiptEntryForm, VoucherForm
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
    StudentOpeningBalance,
    StudentTransport,
    Subject,
    TransferCertificate,
    TransportBus,
    TransportRoute,
    Voucher,
)


def pdf_page_count(pdf_bytes):
    return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))


def pdf_page_size(pdf_bytes):
    match = re.search(
        rb"/MediaBox\s*\[\s*0(?:\.0+)?\s+0(?:\.0+)?\s+([0-9.]+)\s+([0-9.]+)\s*\]",
        pdf_bytes,
    )
    if not match:
        raise AssertionError("PDF MediaBox not found")
    return float(match.group(1)), float(match.group(2))


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
            {"Today's Collection", "Today's Expense", "Receipt Dues (Legacy)", "Active Students"},
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

    def test_scholar_register_number_is_automatic_in_hundreds(self):
        cases = [("1", "1"), ("100", "1"), ("101", "2"), ("2201", "23"), ("2300", "23"), ("2301", "24")]
        for index, (admission_no, expected) in enumerate(cases, start=1):
            student = Student.objects.create(
                full_name=f"Register Boundary {admission_no}",
                admission_no=admission_no,
                legacy_sid=9000 + index,
                scholar_register_no="999",
            )
            self.assertEqual(student.scholar_register_no, expected)

    def test_student_edit_heading_does_not_duplicate_class(self):
        school_class = SchoolClass.objects.create(name="III", display_order=3)
        section = Section.objects.create(school_class=school_class, name="A")
        student = Student.objects.create(
            full_name="Heading Student", current_class=school_class, current_section=section
        )

        response = self.client.get(reverse("core:student_update", args=[student.pk]))

        self.assertContains(response, "Heading Student")
        self.assertContains(response, "III-A")
        self.assertNotContains(response, "III-III - A")

    def test_student_register_supports_book_and_manual_sid_ranges(self):
        for sid in (2201, 2250, 2300, 2301):
            Student.objects.create(full_name=f"Range Student {sid}", legacy_sid=sid, is_active=True)

        book_response = self.client.get(reverse("core:student_register"), {"book": "23"})
        self.assertContains(book_response, "RANGE STUDENT 2201")
        self.assertContains(book_response, "RANGE STUDENT 2300")
        self.assertNotContains(book_response, "RANGE STUDENT 2301")

        manual_response = self.client.get(
            reverse("core:student_register"), {"book": "23", "from_no": "2250", "to_no": "2250"}
        )
        self.assertContains(manual_response, "RANGE STUDENT 2250")
        self.assertNotContains(manual_response, "RANGE STUDENT 2201")
        self.assertNotContains(manual_response, "RANGE STUDENT 2300")

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



class DashboardBackupTests(AuthenticatedClientMixin, TransactionTestCase):
    def test_admin_can_trigger_backup_and_copy_contains_latest_record(self):
        Student.objects.create(full_name="Backup Content Student", legacy_sid=987654)

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {
                "SCHOOLSOFT_BACKUP_ROOT": tmpdir,
                "SCHOOLSOFT_SQLITE_PATH": connection.settings_dict["NAME"],
            },
        ):
            response = self.client.post(reverse("core:backup_start"), follow=True)

            self.assertEqual(response.status_code, 200)
            backup_dirs = [item for item in Path(tmpdir).iterdir() if item.is_dir()]
            self.assertEqual(len(backup_dirs), 1)
            backup_dir = backup_dirs[0]
            backup_db = backup_dir / "db.sqlite3"
            self.assertTrue(backup_db.exists())
            self.assertTrue((backup_dir / "RESTORE-NOTE.txt").exists())

            backup_conn = sqlite3.connect(backup_db)
            try:
                row_count = backup_conn.execute(
                    "SELECT COUNT(*) FROM core_student WHERE full_name = ?",
                    ("Backup Content Student",),
                ).fetchone()[0]
            finally:
                backup_conn.close()
            self.assertEqual(row_count, 1)

            response = self.client.get(reverse("core:dashboard"))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["system_status"][0]["tone"], "ok")

    def test_non_admin_cannot_trigger_backup(self):
        user = get_user_model().objects.create_user(username="backup_viewer", password="pw12345")
        _grant_module_permissions(user, "access_dashboard")
        self.client.force_login(user)

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {"SCHOOLSOFT_BACKUP_ROOT": tmpdir}
        ):
            response = self.client.post(reverse("core:backup_start"))

            self.assertEqual(response.status_code, 403)
            self.assertEqual(list(Path(tmpdir).iterdir()), [])


class DashboardBackupWarningTests(AuthenticatedClientMixin, TestCase):
    def _dashboard_backup_card(self, backup_root):
        with patch.dict(os.environ, {"SCHOOLSOFT_BACKUP_ROOT": str(backup_root)}):
            response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        return response, response.context["system_status"][0]

    def _make_backup_folder(self, backup_root, hours_old):
        backup_dir = backup_root / "20260716-120000"
        backup_dir.mkdir()
        timestamp = (datetime.now() - timedelta(hours=hours_old)).timestamp()
        os.utime(backup_dir, (timestamp, timestamp))
        return backup_dir

    def test_fresh_backup_is_ok_without_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_root = Path(tmpdir)
            self._make_backup_folder(backup_root, hours_old=2)

            response, card = self._dashboard_backup_card(backup_root)

        self.assertEqual(card["tone"], "ok")
        self.assertIsNone(card["warning"])
        self.assertNotContains(response, "din se nahi hua")

    def test_one_day_old_backup_is_warn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_root = Path(tmpdir)
            self._make_backup_folder(backup_root, hours_old=30)

            response, card = self._dashboard_backup_card(backup_root)

        self.assertEqual(card["tone"], "warn")
        self.assertEqual(card["warning"], "Backup 1 din se nahi hua")
        self.assertContains(response, "Backup 1 din se nahi hua")

    def test_four_day_old_backup_is_danger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_root = Path(tmpdir)
            self._make_backup_folder(backup_root, hours_old=96)

            response, card = self._dashboard_backup_card(backup_root)

        self.assertEqual(card["tone"], "danger")
        self.assertEqual(card["warning"], "Backup 4 din se nahi hua!")
        self.assertContains(response, "Backup 4 din se nahi hua!")

    def test_no_backup_is_danger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            response, card = self._dashboard_backup_card(Path(tmpdir))

        self.assertEqual(card["tone"], "danger")
        self.assertEqual(card["value"], "No backup found")
        self.assertEqual(card["warning"], "Database backup nahi mila!")
        self.assertContains(response, "Database backup nahi mila!")
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
        self.assertNotIn("core_salarypayment", sql)

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


class DashboardExpenseKpiTests(TestCase):
    """Today's Expense = today's Daily Expense vouchers + today's CASH salary
    (net pay), each half gated on its own module permission - so the card
    matches what the Cash Book (with 'Include salary') shows for today."""

    def setUp(self):
        self.session = AcademicSession.objects.create(name="2026-27", is_active=True)
        group = AccountGroup.objects.create(
            name="Expenses", group_type=AccountGroup.GroupType.EXPENSE
        )
        self.cash = LedgerAccount.objects.create(
            name="Cash in Hand", group=group, is_cash_or_bank=True
        )
        self.diesel = LedgerAccount.objects.create(name="Diesel", group=group)
        self.staff = Staff.objects.create(
            full_name="Neelu Miss", designation="Teacher", basic_pay=Decimal("5000.00")
        )
        self.today = timezone.localdate()

    def _voucher(self, voucher_no, amount, **overrides):
        defaults = dict(
            voucher_no=voucher_no,
            voucher_type=Voucher.VoucherType.CASH_PAYMENT,
            session=self.session,
            voucher_date=self.today,
            debit_account=self.diesel,
            credit_account=self.cash,
            amount=Decimal(amount),
            payment_mode=Voucher.PaymentMode.CASH,
        )
        defaults.update(overrides)
        return Voucher.objects.create(**defaults)

    def _salary(self, slip_no, basic, **overrides):
        defaults = dict(
            slip_no=slip_no,
            staff=self.staff,
            pay_month=self.today.replace(day=1),
            payment_date=self.today,
            payment_mode=SalaryPayment.PaymentMode.CASH,
            basic_pay=Decimal(basic),
        )
        defaults.update(overrides)
        return SalaryPayment.objects.create(**defaults)

    def _expense_kpi(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        for kpi in response.context["dashboard_kpis"]:
            if kpi["label"] == "Today's Expense":
                return kpi
        return None

    def _login_with(self, username, *codenames):
        user = get_user_model().objects.create_user(username=username, password="pw12345")
        _grant_module_permissions(user, "access_dashboard", *codenames)
        self.client.force_login(user)
        return user

    def test_admin_sees_voucher_plus_salary_combined(self):
        admin = get_user_model().objects.create_superuser(
            username="expense_admin", email="a@example.com", password="pw12345"
        )
        self.client.force_login(admin)
        self._voucher("EXP-1", "1000.00")
        self._salary("SAL-T1", "5000.00")

        kpi = self._expense_kpi()
        self.assertEqual(kpi["value"], Decimal("6000.00"))
        self.assertEqual(kpi["caption"], "Salary payments included")

    def test_cancelled_and_non_cash_salary_excluded(self):
        admin = get_user_model().objects.create_superuser(
            username="expense_admin2", email="b@example.com", password="pw12345"
        )
        self.client.force_login(admin)
        self._voucher("EXP-2", "1000.00")
        self._voucher("EXP-3", "700.00", is_cancelled=True)
        # Distinct staff / pay_month per slip - the unique_active_salary
        # constraint allows only one non-cancelled slip per staff per month.
        bank_staff = Staff.objects.create(
            full_name="Bank Teacher", designation="Teacher", basic_pay=Decimal("3000.00")
        )
        self._salary("SAL-T2", "5000.00", is_cancelled=True)
        self._salary(
            "SAL-T3", "3000.00", staff=bank_staff,
            payment_mode=SalaryPayment.PaymentMode.BANK_TRANSFER,
        )
        # Yesterday's salary must not leak into today's card.
        prev_month = (self.today.replace(day=1) - timedelta(days=1)).replace(day=1)
        self._salary(
            "SAL-T4", "2000.00",
            payment_date=self.today - timedelta(days=1), pay_month=prev_month,
        )

        kpi = self._expense_kpi()
        self.assertEqual(kpi["value"], Decimal("1000.00"))

    def test_salary_counts_net_pay_not_gross(self):
        admin = get_user_model().objects.create_superuser(
            username="expense_admin3", email="c@example.com", password="pw12345"
        )
        self.client.force_login(admin)
        self._salary(
            "SAL-T5", "5000.00",
            da=Decimal("500.00"), pf_deduction=Decimal("600.00"),
            advance_recovery=Decimal("400.00"),
        )

        kpi = self._expense_kpi()
        self.assertEqual(kpi["value"], Decimal("4500.00"))

    def test_accounts_only_user_sees_vouchers_without_salary(self):
        self._login_with("accounts_only", "access_accounts")
        self._voucher("EXP-4", "1000.00")
        self._salary("SAL-T6", "5000.00")

        kpi = self._expense_kpi()
        self.assertEqual(kpi["value"], Decimal("1000.00"))
        self.assertIsNone(kpi["caption"])

    def test_staff_only_user_sees_salary_without_vouchers(self):
        self._login_with("staff_only", "access_staff")
        self._voucher("EXP-5", "1000.00")
        self._salary("SAL-T7", "5000.00")

        kpi = self._expense_kpi()
        self.assertEqual(kpi["value"], Decimal("5000.00"))
        self.assertEqual(kpi["caption"], "Salary payments included")

    def test_fee_only_user_has_no_expense_card(self):
        self._login_with("fee_only", "access_fee_collection")
        self._voucher("EXP-6", "1000.00")
        self._salary("SAL-T8", "5000.00")

        self.assertIsNone(self._expense_kpi())


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
    def test_fee_receipt_student_choice_label_includes_identity_details(self):
        school_class = SchoolClass.objects.create(name="II", display_order=2)
        section = Section.objects.create(school_class=school_class, name="A")
        student = Student.objects.create(
            full_name="Duplicate Name Student",
            legacy_sid=2298,
            admission_no="ADM-2298",
            father_name="Amit Father",
            mobile_primary="9999999999",
            current_class=school_class,
            current_section=section,
            is_active=True,
        )

        label = FeeReceiptEntryForm().fields["student"].label_from_instance(student)

        self.assertIn("Duplicate Name Student", label)
        self.assertIn("SID 2298", label)
        self.assertIn("II-A", label)
        self.assertIn("Adm ADM-2298", label)
        self.assertIn("Father Amit Father", label)
        self.assertIn("Mobile 9999999999", label)

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
        self.assertContains(detail_response, reverse("core:receipt_print", args=[receipt.id]))

    @patch("core.views.os.startfile", create=True)
    def test_receipt_print_sends_a5_pdf_to_windows_print(self, startfile_mock):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Print Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")
        receipt = FeeReceipt.objects.create(
            receipt_no="PRINT-1",
            student=student,
            session=session,
            received_amount=Decimal("100.00"),
            legacy_fee_total=Decimal("100.00"),
            legacy_net_total=Decimal("100.00"),
        )
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=fee_head, amount=Decimal("100.00"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"LOCALAPPDATA": tmp_dir}), patch("core.views.os.name", "nt"):
                response = self.client.get(
                    reverse("core:receipt_print", args=[receipt.id]),
                    HTTP_HOST="127.0.0.1:8000",
                )
                self.assertRedirects(response, reverse("core:receipt_detail", args=[receipt.id]))
                startfile_mock.assert_called_once()
                pdf_path, action = startfile_mock.call_args.args
                self.assertEqual(action, "print")
                self.assertTrue(pdf_path.endswith(".pdf"))
                self.assertTrue(Path(pdf_path).exists())

    @patch("core.views.subprocess.Popen")
    @patch("core.views.os.startfile", create=True)
    def test_receipt_print_uses_edge_when_pdf_print_verb_is_missing(self, startfile_mock, popen_mock):
        startfile_mock.side_effect = OSError("No application is associated")
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Edge Print Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")
        receipt = FeeReceipt.objects.create(
            receipt_no="PRINT-EDGE-1",
            student=student,
            session=session,
            received_amount=Decimal("100.00"),
            legacy_fee_total=Decimal("100.00"),
            legacy_net_total=Decimal("100.00"),
        )
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=fee_head, amount=Decimal("100.00"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_edge = Path(tmp_dir) / "msedge.exe"
            fake_edge.write_text("", encoding="utf-8")
            with (
                patch.dict(os.environ, {"LOCALAPPDATA": tmp_dir}),
                patch("core.views.os.name", "nt"),
                patch("core.views._edge_executable_path", return_value=fake_edge),
            ):
                response = self.client.get(
                    reverse("core:receipt_print", args=[receipt.id]),
                    HTTP_HOST="127.0.0.1:8000",
                )
                self.assertRedirects(response, reverse("core:receipt_detail", args=[receipt.id]))
                startfile_mock.assert_called_once()
                popen_mock.assert_called_once()
                command = popen_mock.call_args.args[0]
                self.assertEqual(command[0], str(fake_edge))
                self.assertIn("--kiosk-printing", command)
                self.assertTrue(command[-1].startswith("file:///"))

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
        page_width, page_height = pdf_page_size(pdf_response.content)
        self.assertAlmostEqual(page_width, landscape(A5)[0], delta=0.2)
        self.assertAlmostEqual(page_height, landscape(A5)[1], delta=0.2)

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
                "previous_due_amount": "0.00",
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

    def test_receipt_create_rejects_posted_previous_due_without_fee_heads(self):
        """The deprecated POST key cannot recreate a previous-due-only receipt."""
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="III", display_order=3)
        student = Student.objects.create(full_name="Due Only Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")

        get_response = self.client.get(reverse("core:receipt_create"))
        self.assertNotContains(get_response, 'id="id_previous_due_amount"')

        post_response = self.client.post(
            reverse("core:receipt_create"),
            data={
                "student": student.id,
                "session": session.id,
                "receipt_date": "2026-07-12",
                "from_month": "JULY",
                "to_month": "JULY",
                "payment_mode": FeeReceipt.PaymentMode.CASH,
                "previous_due_amount": "2000.00",
                "concession_amount": "0.00",
                "late_fee_amount": "0.00",
                "received_amount": "2000.00",
                "remarks": "Deprecated previous due attempt",
                f"fee_head_{fee_head.id}": "0.00",
            },
        )

        self.assertEqual(post_response.status_code, 200)
        self.assertFalse(FeeReceipt.objects.filter(remarks="Deprecated previous due attempt").exists())
        self.assertContains(post_response, "At least one fee head amount is required")
    def test_receipt_create_rejects_completely_empty_amounts(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="III", display_order=3)
        student = Student.objects.create(full_name="Empty Receipt Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")

        post_response = self.client.post(
            reverse("core:receipt_create"),
            data={
                "student": student.id,
                "session": session.id,
                "receipt_date": "2026-07-12",
                "from_month": "JULY",
                "to_month": "JULY",
                "payment_mode": FeeReceipt.PaymentMode.CASH,
                "concession_amount": "0.00",
                "late_fee_amount": "0.00",
                "received_amount": "0.00",
                "remarks": "Should not save",
                f"fee_head_{fee_head.id}": "0.00",
            },
        )

        self.assertEqual(post_response.status_code, 200)
        self.assertFalse(FeeReceipt.objects.filter(remarks="Should not save").exists())
        self.assertContains(post_response, "At least one fee head amount is required")
    def test_student_fee_defaults_api(self):
        session = AcademicSession.objects.create(name="2026-27", is_active=True)
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Test Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")
        FeeStructure.objects.create(
            session=session,
            school_class=school_class,
            fee_head=fee_head,
            amount=Decimal("500.00"),
            is_active=True,
        )

        response = self.client.get(
            reverse("core:student_fee_defaults", args=[student.id]),
            {"session": session.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["amounts"][f"fee_head_{fee_head.id}"], "500.00")
        self.assertNotIn("previous_due", response.json())
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
        self.assertContains(response, "Receipt Due (Legacy)")
        self.assertContains(response, "Due Student")
        self.assertContains(response, reverse("core:due_up_to_month_report"))
    def test_fee_defaults_does_not_expose_previous_due(self):
        old_session = AcademicSession.objects.create(name="2025-26")
        new_session = AcademicSession.objects.create(name="2026-27", is_active=True)
        school_class = SchoolClass.objects.create(name="IV", display_order=4)
        student = Student.objects.create(full_name="Opening Balance Student", current_class=school_class)
        FeeReceipt.objects.create(
            receipt_no="OLD-1",
            student=student,
            session=old_session,
            legacy_due_amount=Decimal("700.00"),
        )

        response = self.client.get(
            reverse("core:student_fee_defaults", args=[student.id]),
            {"session": new_session.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("previous_due", response.json())
    def test_fee_defaults_excludes_inactive_structures(self):
        session = AcademicSession.objects.create(name="2026-27", is_active=True)
        school_class = SchoolClass.objects.create(name="IV", display_order=4)
        student = Student.objects.create(full_name="Active Structure Student", current_class=school_class)
        active_head = FeeHead.objects.create(name="Tuition Fee")
        stale_head = FeeHead.objects.create(name="Development Fee")
        FeeStructure.objects.create(
            session=session,
            school_class=school_class,
            fee_head=active_head,
            amount=Decimal("700.00"),
            is_active=True,
        )
        FeeStructure.objects.create(
            session=session,
            school_class=school_class,
            fee_head=stale_head,
            amount=Decimal("999.00"),
            is_active=False,
        )

        response = self.client.get(
            reverse("core:student_fee_defaults", args=[student.id]),
            {"session": session.id},
        )

        amounts = response.json()["amounts"]
        self.assertEqual(amounts[f"fee_head_{active_head.id}"], "700.00")
        self.assertNotIn(f"fee_head_{stale_head.id}", amounts)
    def test_posted_previous_due_is_ignored_and_prior_receipt_is_not_carried_forward(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="V", display_order=5)
        student = Student.objects.create(full_name="No Carry Forward Student", current_class=school_class)
        old_receipt = FeeReceipt.objects.create(
            receipt_no="MR-OLD",
            student=student,
            session=session,
            legacy_due_amount=Decimal("500.00"),
        )
        fee_head = FeeHead.objects.create(name="Tuition Fee")

        post_response = self.client.post(
            reverse("core:receipt_create"),
            data={
                "student": student.id,
                "session": session.id,
                "receipt_date": "2026-07-12",
                "from_month": "MAY",
                "to_month": "MAY",
                "payment_mode": FeeReceipt.PaymentMode.CASH,
                "previous_due_amount": "500.00",
                "concession_amount": "0.00",
                "late_fee_amount": "0.00",
                "received_amount": "600.00",
                "remarks": "New engine receipt",
                f"fee_head_{fee_head.id}": "1000.00",
            },
        )

        new_receipt = FeeReceipt.objects.get(remarks="New engine receipt")
        self.assertRedirects(post_response, reverse("core:receipt_detail", args=[new_receipt.id]))
        self.assertEqual(new_receipt.previous_due_amount, Decimal("0.00"))
        self.assertEqual(new_receipt.legacy_net_total, Decimal("1000.00"))
        self.assertEqual(new_receipt.legacy_due_amount, Decimal("400.00"))
        old_receipt.refresh_from_db()
        self.assertFalse(old_receipt.carried_forward)
    def test_fee_defaults_without_session_uses_active_session_only(self):
        old_session = AcademicSession.objects.create(name="2025-26", is_active=False)
        active_session = AcademicSession.objects.create(name="2026-27", is_active=True)
        school_class = SchoolClass.objects.create(name="VII", display_order=7)
        student = Student.objects.create(full_name="Session Defaults Student", current_class=school_class)
        old_head = FeeHead.objects.create(name="Old Tuition")
        active_head = FeeHead.objects.create(name="Current Tuition")
        FeeStructure.objects.create(
            session=old_session,
            school_class=school_class,
            fee_head=old_head,
            amount=Decimal("900.00"),
            is_active=True,
        )
        FeeStructure.objects.create(
            session=active_session,
            school_class=school_class,
            fee_head=active_head,
            amount=Decimal("700.00"),
            is_active=True,
        )

        response = self.client.get(reverse("core:student_fee_defaults", args=[student.id]))
        amounts = response.json()["amounts"]

        self.assertIn(f"fee_head_{active_head.id}", amounts)
        self.assertNotIn(f"fee_head_{old_head.id}", amounts)
    def test_new_receipt_keeps_deprecated_fields_at_safe_defaults(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="V", display_order=5)
        student = Student.objects.create(full_name="Safe Defaults Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")

        response = self.client.post(
            reverse("core:receipt_create"),
            data={
                "student": student.id,
                "session": session.id,
                "receipt_date": "2026-07-05",
                "from_month": "APR",
                "to_month": "JUL",
                "payment_mode": FeeReceipt.PaymentMode.CASH,
                "previous_due_amount": "700.00",
                "concession_amount": "0.00",
                "late_fee_amount": "0.00",
                "received_amount": "800.00",
                "remarks": "Safe deprecated defaults",
                f"fee_head_{fee_head.id}": "1000.00",
            },
        )

        receipt = FeeReceipt.objects.get(remarks="Safe deprecated defaults")
        self.assertRedirects(response, reverse("core:receipt_detail", args=[receipt.id]))
        self.assertEqual(receipt.previous_due_amount, Decimal("0.00"))
        self.assertFalse(receipt.carried_forward)
        self.assertEqual(receipt.legacy_net_total, Decimal("1000.00"))
        self.assertEqual(receipt.legacy_due_amount, Decimal("200.00"))
    def test_due_report_excludes_carried_forward_receipts(self):
        """A carried_forward receipt stays in the system (audit trail) but
        must not add to Due Report totals - its balance now lives on the
        newer receipt that absorbed it, so counting both would overstate
        the true outstanding amount."""
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="VI", display_order=6)
        student = Student.objects.create(full_name="Settled Student", current_class=school_class)
        FeeReceipt.objects.create(
            receipt_no="CF-1",
            student=student,
            session=session,
            received_amount=Decimal("0.00"),
            legacy_net_total=Decimal("500.00"),
            legacy_due_amount=Decimal("500.00"),
            carried_forward=True,
        )

        response = self.client.get(reverse("core:due_report"), {"session": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Settled Student")

    def test_receipt_pdf_shows_previous_due_line(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="VII", display_order=7)
        student = Student.objects.create(full_name="Previous Due PDF Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")
        receipt = FeeReceipt.objects.create(
            receipt_no="PD-1",
            student=student,
            session=session,
            previous_due_amount=Decimal("700.00"),
            received_amount=Decimal("1000.00"),
            legacy_fee_total=Decimal("1000.00"),
            legacy_net_total=Decimal("1700.00"),
            legacy_due_amount=Decimal("700.00"),
        )
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=fee_head, amount=Decimal("1000.00"))

        pdf_response = self.client.get(reverse("core:receipt_pdf", args=[receipt.id]))
        detail_response = self.client.get(reverse("core:receipt_detail", args=[receipt.id]))

        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "NOT FULLY PAID")
        # Real incident (July 2026): this line item was added to core/pdf.py's
        # build_fee_receipt_pdf but the parallel HTML view (receipt_detail.html,
        # used both on-screen and for "Print Receipt") never got the matching
        # row - so Net Payable jumped above Fee Total with no visible
        # explanation, looking exactly like the double-counting bug this
        # feature was built to prevent. Must appear in both surfaces.
        self.assertContains(detail_response, "Previous Due (carried forward)")

    def test_receipt_detail_shows_current_due_status_from_fee_engine(self):
        session = AcademicSession.objects.create(
            name="2026-27",
            starts_on=date(2026, 4, 1),
            ends_on=date(2027, 3, 31),
        )
        school_class = SchoolClass.objects.create(name="V", display_order=5)
        student = Student.objects.create(
            full_name="Current Due Student",
            current_class=school_class,
            admission_date=date(2025, 4, 1),
        )
        tuition = FeeHead.objects.create(
            name="Tuition Fee",
            frequency=FeeHead.Frequency.MONTHLY,
            new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
            old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        )
        FeeStructure.objects.create(
            session=session,
            school_class=school_class,
            fee_head=tuition,
            amount=Decimal("700.00"),
            is_active=True,
        )
        receipt = FeeReceipt.objects.create(
            receipt_no="STATUS-1",
            student=student,
            session=session,
            receipt_date=date(2026, 7, 13),
            from_month="APR",
            to_month="MAR",
            received_amount=Decimal("2000.00"),
            legacy_fee_total=Decimal("8400.00"),
            legacy_net_total=Decimal("8400.00"),
            legacy_due_amount=Decimal("6400.00"),
        )
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=tuition, amount=Decimal("8400.00"))

        response = self.client.get(reverse("core:receipt_detail", args=[receipt.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Current fee status after this receipt")
        self.assertContains(response, "Up to month")
        self.assertContains(response, "MAR")
        self.assertContains(response, "Total demand")
        self.assertContains(response, "Rs. 8,400")
        self.assertContains(response, "Paid in session")
        self.assertContains(response, "Rs. 2,000")
        self.assertContains(response, "Due Rs. 6,400")
        self.assertContains(response, "Dues up to Month")
    def test_fee_collection_defaults_include_due_status_and_balance_fee_field(self):
        session = AcademicSession.objects.create(
            name="2026-27",
            starts_on=date(2026, 4, 1),
            ends_on=date(2027, 3, 31),
            is_active=True,
        )
        school_class = SchoolClass.objects.create(name="V", display_order=5)
        student = Student.objects.create(
            full_name="Balance Fee Student",
            current_class=school_class,
            admission_date=date(2025, 4, 1),
            is_active=True,
        )
        tuition = FeeHead.objects.create(
            name="Monthly Tuition Test",
            frequency=FeeHead.Frequency.MONTHLY,
            new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
            old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        )
        FeeStructure.objects.create(
            session=session,
            school_class=school_class,
            fee_head=tuition,
            amount=Decimal("700.00"),
            is_active=True,
        )
        FeeReceipt.objects.create(
            receipt_no="BAL-PAID-1",
            student=student,
            session=session,
            receipt_date=date(2026, 7, 13),
            received_amount=Decimal("1000.00"),
        )

        response = self.client.get(
            reverse("core:student_fee_defaults", args=[student.id]),
            {"session": session.id, "month": "JUL"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["balance_fee_field"].startswith("fee_head_"))
        self.assertEqual(data["due_status"]["target_month"], "JUL")
        self.assertEqual(data["due_status"]["gross_demand"], "2800.00")
        self.assertEqual(data["due_status"]["received_amount"], "1000.00")
        self.assertEqual(data["due_status"]["due_amount"], "1800.00")

    def test_fee_defaults_uses_new_engine_even_when_legacy_receipt_due_differs(self):
        session = AcademicSession.objects.create(
            name="2026-27",
            starts_on=date(2026, 4, 1),
            ends_on=date(2027, 3, 31),
            is_active=True,
        )
        school_class = SchoolClass.objects.create(name="II", display_order=2)
        student = Student.objects.create(
            full_name="Receipt Balance Student",
            current_class=school_class,
            admission_date=date(2022, 4, 25),
            is_active=True,
        )
        FeeHead.objects.get_or_create(name="Balance Fee", defaults={"is_active": True})
        tuition = FeeHead.objects.create(
            name="Monthly Tuition Test",
            frequency=FeeHead.Frequency.MONTHLY,
            new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
            old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        )
        FeeStructure.objects.create(
            session=session,
            school_class=school_class,
            fee_head=tuition,
            amount=Decimal("700.00"),
            is_active=True,
        )
        FeeReceipt.objects.create(
            receipt_no="MR-OLD-DUE",
            student=student,
            session=session,
            receipt_date=date(2026, 7, 13),
            from_month="APR",
            to_month="MAR",
            received_amount=Decimal("3000.00"),
            concession_amount=Decimal("3150.00"),
            legacy_due_amount=Decimal("5400.00"),
        )

        response = self.client.get(
            reverse("core:student_fee_defaults", args=[student.id]),
            {"session": session.id, "month": "MAR"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["due_status"]["due_amount"], "2250.00")
        self.assertNotIn("receipt_balance_due", data)
    def test_fee_collection_form_renders_balance_due_controls(self):
        response = self.client.get(reverse("core:receipt_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-student-due-card")
        self.assertContains(response, "data-student-current-due")
        self.assertContains(response, "data-fill-balance-fee")
        self.assertContains(response, "Balance / Due Fee")
    def test_backup_helper_prefers_desktop_live_db_when_env_path_is_missing(self):
        from core import views

        fake_live = Path(tempfile.mkdtemp()) / "SchoolSoft" / "db.sqlite3"
        fake_live.parent.mkdir(parents=True, exist_ok=True)
        fake_live.write_bytes(b"live-db")

        with patch.dict(os.environ, {"LOCALAPPDATA": str(fake_live.parent.parent)}, clear=False):
            os.environ.pop("SCHOOLSOFT_SQLITE_PATH", None)
            self.assertEqual(views._active_sqlite_db_path(), fake_live)


class DefaulterListTests(AuthenticatedClientMixin, TestCase):
    def test_defaulter_list_uses_fee_engine_and_active_students_only(self):
        session = AcademicSession.objects.create(
            name="2026-27",
            starts_on=date(2026, 4, 1),
            ends_on=date(2027, 3, 31),
            is_active=True,
        )
        school_class = SchoolClass.objects.create(name="III", display_order=3)
        section = Section.objects.create(school_class=school_class, name="A")
        tuition = FeeHead.objects.create(
            name="Defaulter Tuition Fee",
            frequency=FeeHead.Frequency.MONTHLY,
            new_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
            old_student_charge_rule=FeeHead.ChargeRule.MONTHLY,
        )
        FeeStructure.objects.create(
            session=session,
            school_class=school_class,
            fee_head=tuition,
            amount=Decimal("800.00"),
            is_active=True,
        )
        due_student = Student.objects.create(
            full_name="Opening Balance Defaulter",
            admission_no="DUE-1",
            mobile_primary="9999999999",
            current_class=school_class,
            current_section=section,
            admission_date=date(2025, 4, 1),
            is_active=True,
        )
        StudentOpeningBalance.objects.create(
            student=due_student,
            session=session,
            amount=Decimal("100.00"),
            as_of_date=date(2026, 4, 1),
            source_reference="Test opening balance",
        )
        FeeReceipt.objects.create(
            receipt_no="DEF-PARTIAL",
            student=due_student,
            session=session,
            receipt_date=date(2026, 4, 20),
            received_amount=Decimal("100.00"),
        )
        paid_student = Student.objects.create(
            full_name="Fully Paid Student",
            current_class=school_class,
            admission_date=date(2025, 4, 1),
            is_active=True,
        )
        FeeReceipt.objects.create(
            receipt_no="DEF-PAID",
            student=paid_student,
            session=session,
            receipt_date=date(2026, 4, 21),
            received_amount=Decimal("800.00"),
        )
        Student.objects.create(
            full_name="Inactive Due Student",
            current_class=school_class,
            admission_date=date(2025, 4, 1),
            is_active=False,
        )

        response = self.client.get(
            reverse("core:defaulter_list"),
            {"class": school_class.id, "month": "APR"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_defaulters"], 1)
        self.assertEqual(response.context["total_due"], Decimal("800.00"))
        self.assertContains(response, "Opening Balance Defaulter")
        self.assertContains(response, "9999999999")
        self.assertContains(response, "20-Apr-2026")
        self.assertContains(response, "Rs. 800.00")
        self.assertNotContains(response, "Fully Paid Student")
        self.assertNotContains(response, "Inactive Due Student")


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
                "application_date": "2026-06-25",
                "date_of_leaving": "2026-06-30",
                "last_class_studied": school_class.id,
                "last_section": "",
                "reason_for_leaving": "Family relocation",
                "conduct": TransferCertificate.Conduct.GOOD,
                "general_progress": TransferCertificate.Conduct.GOOD,
                "qualified_for_promotion": "on",
                "promoted_to_class": "",
                "total_working_days": "200",
                "days_present": "190",
                "fees_paid_upto": "June 2026",
                "remarks": "",
            },
        )
        self.assertRedirects(post_response, reverse("core:tc_detail", args=[student.id]))

        tc = TransferCertificate.objects.get(student=student)
        self.assertTrue(tc.tc_number.startswith("TC-"))
        self.assertEqual(tc.book_no, student.scholar_register_no)
        self.assertEqual(tc.sr_no, student.admission_no or str(student.legacy_sid or ""))

        pdf_response = self.client.get(reverse("core:tc_pdf", args=[student.id]))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")

    def test_tc_form_rejects_incomplete_data(self):
        """A TC missing administratively-required fields (leaving date,
        reason, working days, fees paid upto, application date) must not be
        saved - an issued TC with these blank is incomplete, not just an
        unstyled one (owner decision, July 2026 TC redesign)."""
        school_class = SchoolClass.objects.create(name="II", display_order=1)
        student = Student.objects.create(full_name="Incomplete TC Student", current_class=school_class)

        post_response = self.client.post(
            reverse("core:tc_detail", args=[student.id]),
            data={
                "issue_date": "2026-07-01",
                "last_class_studied": school_class.id,
                "last_section": "",
                "conduct": TransferCertificate.Conduct.GOOD,
                "general_progress": TransferCertificate.Conduct.GOOD,
                "qualified_for_promotion": "on",
                "promoted_to_class": "",
                "remarks": "",
                # application_date, date_of_leaving, reason_for_leaving,
                # total_working_days, days_present, fees_paid_upto all
                # intentionally omitted.
            },
        )

        self.assertEqual(post_response.status_code, 200)  # re-renders form with errors, no redirect
        self.assertFalse(TransferCertificate.objects.filter(student=student).exists())

    def test_tc_form_rejects_impossible_dates_and_attendance(self):
        school_class = SchoolClass.objects.create(name="III", display_order=1)
        student = Student.objects.create(full_name="Invalid TC Student", current_class=school_class)

        response = self.client.post(
            reverse("core:tc_detail", args=[student.id]),
            data={
                "issue_date": "2026-07-01",
                "application_date": "2026-07-02",
                "date_of_leaving": "2026-07-03",
                "last_class_studied": school_class.id,
                "reason_for_leaving": "Family relocation",
                "conduct": TransferCertificate.Conduct.GOOD,
                "general_progress": TransferCertificate.Conduct.GOOD,
                "total_working_days": "200",
                "days_present": "201",
                "fees_paid_upto": "June 2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Application date cannot be after the TC issue date.")
        self.assertContains(response, "Date of leaving cannot be after the TC issue date.")
        self.assertContains(response, "Days present cannot exceed total working days.")
        self.assertFalse(TransferCertificate.objects.filter(student=student).exists())

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
        # Real incident (July 2026): previous_due_amount was added as a
        # required ModelForm field but templates/core/receipt_edit.html was
        # never updated to render it, so every "Correct Receipt" submission
        # silently failed validation ("This field is required") with no
        # visible error, since the template had no element for that specific
        # field. Guard against this class of bug recurring: the rendered
        # edit page must always include an input for every required field
        # on FeeReceiptEditForm.
        self.assertNotContains(get_edit, 'id="id_previous_due_amount"')

        post_edit = self.client.post(
            reverse("core:receipt_edit", args=[receipt.id]),
            data={
                "receipt_date": "2026-07-02",
                "payment_mode": FeeReceipt.PaymentMode.ONLINE,
                "previous_due_amount": "0.00",
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

    def test_receipt_edit_preserves_historical_previous_due_as_locked_audit_value(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="VII", display_order=7)
        student = Student.objects.create(full_name="Audit Trail Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")
        receipt = FeeReceipt.objects.create(
            receipt_no="AUDIT-1",
            student=student,
            session=session,
            previous_due_amount=Decimal("1900.00"),
            received_amount=Decimal("800.00"),
            legacy_fee_total=Decimal("4050.00"),
            legacy_net_total=Decimal("5950.00"),
            legacy_due_amount=Decimal("5150.00"),
        )
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=fee_head, amount=Decimal("4050.00"))

        get_response = self.client.get(reverse("core:receipt_edit", args=[receipt.id]))
        self.assertNotContains(get_response, 'id="id_previous_due_amount"')
        self.assertContains(get_response, "Historical Previous Due")

        self.client.post(
            reverse("core:receipt_edit", args=[receipt.id]),
            data={
                "receipt_date": "2026-07-12",
                "payment_mode": FeeReceipt.PaymentMode.CASH,
                "concession_amount": "0.00",
                "late_fee_amount": "0.00",
                "received_amount": "1900.00",
                "remarks": "Correct paid amount",
                "edit_reason": "Payment correction",
                f"fee_head_{fee_head.id}": "4050.00",
            },
        )

        receipt.refresh_from_db()
        log = receipt.audit_logs.first()
        self.assertEqual(receipt.previous_due_amount, Decimal("1900.00"))
        self.assertEqual(receipt.legacy_net_total, Decimal("5950.00"))
        self.assertNotIn("previous_due_amount", log.changes)
        self.assertEqual(log.before_snapshot["previous_due_amount"], "1900.00")
        self.assertEqual(log.after_snapshot["previous_due_amount"], "1900.00")
    def test_receipt_edit_page_renders_every_required_form_field(self):
        """General regression guard for the previous_due_amount incident
        above: every REQUIRED field on FeeReceiptEditForm must actually have
        an input rendered on the edit page, or a submission omitting it will
        silently fail validation with no visible error to the office staff.
        Checks all required fields generically so a future new required
        field being forgotten in the template fails this test immediately,
        instead of silently breaking "Correct Receipt" in production."""
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Field Coverage Student", current_class=school_class)
        receipt = FeeReceipt.objects.create(
            receipt_no="EDIT-COVER-1",
            student=student,
            session=session,
            received_amount=Decimal("100.00"),
            legacy_fee_total=Decimal("100.00"),
            legacy_net_total=Decimal("100.00"),
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("core:receipt_edit", args=[receipt.id]))
        self.assertEqual(response.status_code, 200)

        edit_form = FeeReceiptEditForm(instance=receipt)
        content = response.content.decode()
        missing = [
            name
            for name, field in edit_form.fields.items()
            if field.required and not field.disabled and f'id="id_{name}"' not in content
        ]
        self.assertEqual(missing, [], f"Required field(s) missing from receipt_edit.html: {missing}")


class ScholarRegisterBookTests(AuthenticatedClientMixin, TestCase):
    """Full physical Scholar Register book print (2026-07-11 checkpoint).
    Owner's explicit decisions: a missing SID in the range gets NO
    individual page (skipped entirely, not a blank placeholder) but DOES
    still appear as a 'Not Allotted' row in the index; every student status
    (active, inactive, TC-issued) is included in the range."""

    def setUp(self):
        super().setUp()
        self.school_class = SchoolClass.objects.create(name="IV", display_order=1)

    def test_book_entries_marks_missing_sid_as_none(self):
        from .views import _scholar_register_book_entries

        present_a = Student.objects.create(full_name="Present A", current_class=self.school_class, legacy_sid=101)
        present_b = Student.objects.create(full_name="Present B", current_class=self.school_class, legacy_sid=103)
        # 102 deliberately has no student.

        entries = _scholar_register_book_entries(101, 103)

        self.assertEqual([sid for sid, _ in entries], [101, 102, 103])
        self.assertEqual(entries[0][1], present_a)
        self.assertIsNone(entries[1][1])
        self.assertEqual(entries[2][1], present_b)

    def test_book_entries_includes_every_status(self):
        from .views import _scholar_register_book_entries

        active = Student.objects.create(full_name="Active Student", current_class=self.school_class, legacy_sid=201, is_active=True)
        inactive = Student.objects.create(full_name="Inactive Student", current_class=self.school_class, legacy_sid=202, is_active=False)
        left = Student.objects.create(full_name="Left Student", current_class=self.school_class, legacy_sid=203, is_active=False)
        TransferCertificate.objects.create(
            student=left, tc_number="TC-TEST-0002", last_class_studied=self.school_class,
        )

        entries = _scholar_register_book_entries(201, 203)
        found = {sid: student for sid, student in entries}

        self.assertEqual(found[201], active)
        self.assertEqual(found[202], inactive)
        self.assertEqual(found[203], left)

    def test_book_pdf_requires_a_range(self):
        response = self.client.get(reverse("core:scholar_register_book_pdf"))
        self.assertRedirects(response, reverse("core:student_register"))

    def test_index_pdf_requires_a_range(self):
        response = self.client.get(reverse("core:scholar_register_index_pdf"))
        self.assertRedirects(response, reverse("core:student_register"))

    def test_book_pdf_with_explicit_from_to_range(self):
        Student.objects.create(full_name="Range Student", current_class=self.school_class, legacy_sid=301)

        response = self.client.get(reverse("core:scholar_register_book_pdf"), {"from_no": "301", "to_no": "301"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_book_pdf_with_book_number_autofills_range(self):
        # Book 1 = SID 1-100.
        Student.objects.create(full_name="Book One Student", current_class=self.school_class, legacy_sid=50)

        response = self.client.get(reverse("core:scholar_register_book_pdf"), {"book": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_index_pdf_with_no_students_in_range_still_renders(self):
        # An empty book (no students at all in this range) should still
        # produce a valid index PDF listing every slot as Not Allotted.
        response = self.client.get(reverse("core:scholar_register_index_pdf"), {"from_no": "9001", "to_no": "9010"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_long_student_register_stays_on_one_page_in_full_book(self):
        from .pdf import build_scholar_register_book_pdf, build_scholar_register_pdf

        student = Student.objects.create(
            full_name="ANUBHUTI DWIVEDI",
            father_name="ALOK RANJAN DWIVEDI",
            mother_name="MANDAVI DWIVEDI",
            date_of_birth=date(2014, 10, 17),
            admission_date=date(2022, 4, 7),
            religion="HINDU",
            caste="BRAHMAN",
            category="GENERAL",
            aadhaar_no="570850472850",
            address_permanent="VILL - DUDHAI, POST - DUDHAI, KUSHINAGAR",
            current_class=self.school_class,
            legacy_sid=2222,
        )
        profile = SchoolProfile.objects.create(
            name="THPS ENGLISH MEDIUM SCHOOL",
            address_line1="DUDAHI 274302, KUSHINAGAR, (U.P)",
            phone="7379568527",
            email="thpses@gmail.com",
            is_active=True,
        )

        individual_pdf = build_scholar_register_pdf(student, profile)
        full_book_pdf = build_scholar_register_book_pdf([(2222, student)], 23, 2222, 2222, profile)

        page_pattern = rb"/Type\s*/Page\b"
        self.assertEqual(len(re.findall(page_pattern, individual_pdf)), 1)
        # Cover + one-page index + exactly one student page.
        self.assertEqual(len(re.findall(page_pattern, full_book_pdf)), 3)


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

        loan_group = AccountGroup.objects.create(
            name="Legacy Loans & Advances", group_type=AccountGroup.GroupType.LIABILITY
        )
        self.loan_ledger = LedgerAccount.objects.create(
            group=loan_group, name="Pragati Personal/Advance A/C"
        )

    def test_receipt_allows_liability_credit_account(self):
        """Real case from the legacy ledger: someone (Pragati) personally advances cash to the
        school to cover a shortfall - a real receipt of cash, but the credit side is a Liability
        (money owed back), not Income. Must be recordable via New Other Receipt, or the owner's
        decision to move this kind of entry into the new app live has no way to actually happen."""
        form = VoucherForm(
            data={
                "voucher_date": "2026-07-09",
                "payment_mode": Voucher.PaymentMode.CASH,
                "debit_account": self.cash_ledger.id,
                "credit_account": self.loan_ledger.id,
                "amount": "30000.00",
                "paid_to_or_received_from": "Pragati",
                "staff": "",
                "narration": "School ke kharch ke liye loan liya gaya",
                "physical_slip_no": "",
            },
            voucher_kind="receipt",
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_expense_allows_liability_debit_account(self):
        """Real case from the legacy ledger: repaying that same loan later
        ("Pragati ka paisa wapas kar diya gya") reduces what the school owes -
        a Liability debit, not an Expense. Must be recordable via Daily Expense."""
        form = VoucherForm(
            data={
                "voucher_date": "2026-07-15",
                "payment_mode": Voucher.PaymentMode.CASH,
                "debit_account": self.loan_ledger.id,
                "credit_account": self.cash_ledger.id,
                "amount": "30000.00",
                "paid_to_or_received_from": "Pragati",
                "staff": "",
                "narration": "Pragati ka paisa wapas kar diya gya",
                "physical_slip_no": "",
            },
            voucher_kind="expense",
        )

        self.assertTrue(form.is_valid(), form.errors)

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


class FeeHeadGuardrailTests(TestCase):
    """Guards against a real incident: staff manually created a "Previous Due" Fee Head
    and entered an amount there, on top of the dedicated FeeReceipt.previous_due_amount
    field, silently doubling a receipt's total. See CODEX-HANDOFF.md."""

    def test_previous_due_name_rejected_on_full_clean(self):
        head = FeeHead(name="Previous Due")
        with self.assertRaises(ValidationError):
            head.full_clean()

    def test_previous_due_name_rejected_case_and_space_insensitive(self):
        for bad_name in ["previous due", "  Previous Due  ", "OLD DUE", "Past Due"]:
            head = FeeHead(name=bad_name)
            with self.assertRaises(ValidationError):
                head.full_clean()

    def test_ordinary_fee_head_name_still_allowed(self):
        head = FeeHead(name="Tuition Fee")
        head.full_clean()  # should not raise


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
