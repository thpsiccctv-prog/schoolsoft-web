from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from core.models import AccountGroup, LedgerAccount, Voucher, VoucherCounter, AcademicSession, User


class AccountsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.session = AcademicSession.objects.create(
            name="2026-27",
            starts_on="2026-04-01",
            ends_on="2027-03-31",
            is_active=True,
        )
        self.group_asset = AccountGroup.objects.create(name="Cash & Bank", group_type="asset")
        self.group_expense = AccountGroup.objects.create(name="Expense", group_type="expense")
        self.group_income = AccountGroup.objects.create(name="Income", group_type="income")

        self.cash_ledger = LedgerAccount.objects.create(
            group=self.group_asset,
            name="Cash in Hand",
            is_cash_or_bank=True,
            opening_balance=Decimal("100.00"),
            opening_balance_date="2026-04-01",
        )
        self.expense_ledger = LedgerAccount.objects.create(
            group=self.group_expense,
            name="Stationery",
        )
        self.income_ledger = LedgerAccount.objects.create(
            group=self.group_income,
            name="Other Income",
        )

    def test_expense_voucher_creation(self):
        voucher = Voucher.objects.create(
            voucher_no="CPMT-2026-27-0001",
            voucher_type=Voucher.VoucherType.CASH_PAYMENT,
            session=self.session,
            debit_account=self.expense_ledger,
            credit_account=self.cash_ledger,
            amount=Decimal("50.00"),
            created_by=self.user,
            narration="Bought pens",
        )
        self.assertEqual(voucher.amount, Decimal("50.00"))
        self.assertFalse(voucher.is_cancelled)

    def test_voucher_cancel(self):
        voucher = Voucher.objects.create(
            voucher_no="CPMT-2026-27-0002",
            voucher_type=Voucher.VoucherType.CASH_PAYMENT,
            session=self.session,
            debit_account=self.expense_ledger,
            credit_account=self.cash_ledger,
            amount=Decimal("20.00"),
        )
        voucher.is_cancelled = True
        voucher.cancelled_at = timezone.now()
        voucher.cancel_reason = "Mistake"
        voucher.save()
        self.assertTrue(voucher.is_cancelled)
        
    def test_voucher_counter(self):
        from core.views import _generate_voucher_no
        v1 = _generate_voucher_no(self.session, Voucher.VoucherType.CASH_PAYMENT)
        v2 = _generate_voucher_no(self.session, Voucher.VoucherType.CASH_PAYMENT)
        self.assertEqual(v1, "CPMT-2026-27-0001")
        self.assertEqual(v2, "CPMT-2026-27-0002")
