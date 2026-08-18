import os
from decimal import Decimal
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import FeederSchool, LedgerAccount, AcademicSession, Voucher, VoucherCounter

# Verified Feeder School Payments from Khatabook Statement (April-July 2026)
KHATABOOK_FEEDER_PAYMENTS = [
    {
        "school_code": "SCH-SHIVPUJAN",
        "date": date(2026, 7, 27),
        "amount": Decimal("50000.00"),
        "mode": Voucher.PaymentMode.CASH,
        "ref": "Khatabook Pg 1",
        "narration": "Shivpujan School JK Singh ko mila (Khatabook)",
    },
    {
        "school_code": "SCH-CHHOTELAL",
        "date": date(2026, 7, 27),
        "amount": Decimal("19200.00"),
        "mode": Voucher.PaymentMode.CASH,
        "ref": "Khatabook Pg 1",
        "narration": "Chhote Lal Attacher payment (Khatabook)",
    },
    {
        "school_code": "SCH-SHUBHAMSIR",
        "date": date(2026, 7, 27),
        "amount": Decimal("50400.00"),
        "mode": Voucher.PaymentMode.CASH,
        "ref": "Khatabook Pg 1",
        "narration": "Shubham Sir attached school payment (Khatabook)",
    },
    {
        "school_code": "SCH-DNSMART",
        "date": date(2026, 7, 26),
        "amount": Decimal("50000.00"),
        "mode": Voucher.PaymentMode.CASH,
        "ref": "Khatabook Pg 2",
        "narration": "D N Smart School Sandeep Kushwaha (Khatabook)",
    },
    {
        "school_code": "SCH-GREENLAND",
        "date": date(2026, 7, 25),
        "amount": Decimal("15000.00"),
        "mode": Voucher.PaymentMode.CASH,
        "ref": "Khatabook Pg 3",
        "narration": "Salim Ansari Green Land School installment 1 (Khatabook)",
    },
    {
        "school_code": "SCH-GREENLAND",
        "date": date(2026, 7, 25),
        "amount": Decimal("32000.00"),
        "mode": Voucher.PaymentMode.CASH,
        "ref": "Khatabook Pg 3",
        "narration": "Salim Ansari Green Land School installment 2 (Khatabook)",
    },
    {
        "school_code": "SCH-NIRAJGIRI",
        "date": date(2026, 7, 25),
        "amount": Decimal("31500.00"),  # Note: 21 students * 1500 = 31,500
        "mode": Voucher.PaymentMode.CASH,
        "ref": "Khatabook Pg 3",
        "narration": "School Niraj Giri payment (Khatabook)",
    },
    {
        "school_code": "SCH-CMPS",
        "date": date(2026, 7, 24),
        "amount": Decimal("18000.00"),
        "mode": Voucher.PaymentMode.CASH,
        "ref": "Khatabook Pg 3",
        "narration": "CMPS School Samim Sir installment 1 (Khatabook)",
    },
    {
        "school_code": "SCH-CMPS",
        "date": date(2026, 7, 23),
        "amount": Decimal("20000.00"),
        "mode": Voucher.PaymentMode.CASH,
        "ref": "Khatabook Pg 4",
        "narration": "CMPS School Samim Sir installment 2 (Khatabook)",
    },
]


class Command(BaseCommand):
    help = "Import historical payments from Khatabook for Feeder Schools."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply changes to the database.")

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        self.stdout.write(self.style.MIGRATE_HEADING("=== IMPORTING KHATABOOK FEEDER SCHOOL PAYMENTS ==="))

        if not apply_changes:
            self.stdout.write(self.style.WARNING("DRY RUN MODE: Pass --apply to persist changes.\n"))

        session = AcademicSession.objects.filter(is_active=True).first() or AcademicSession.objects.first()
        cash_ledger = LedgerAccount.objects.filter(is_cash_or_bank=True, name__icontains="Cash").first()
        if not cash_ledger:
            cash_ledger = LedgerAccount.objects.filter(is_cash_or_bank=True).first()

        total_amount = Decimal("0.00")
        imported_vouchers = 0

        for p in KHATABOOK_FEEDER_PAYMENTS:
            school = FeederSchool.objects.filter(code=p["school_code"]).first()
            if not school or not school.ledger_account:
                self.stdout.write(self.style.ERROR(f"School not found for code: {p['school_code']}"))
                continue

            total_amount += p["amount"]
            imported_vouchers += 1

            self.stdout.write(
                f"  [{p['date']}] {school.name:28} | Amount: Rs.{p['amount']:8,.2f} | Ref: {p['ref']}"
            )

            if apply_changes:
                # Check if duplicate already exists
                existing = Voucher.objects.filter(
                    credit_account=school.ledger_account,
                    voucher_date=p["date"],
                    amount=p["amount"],
                    is_cancelled=False
                ).first()

                if not existing:
                    with transaction.atomic():
                        v_type = Voucher.VoucherType.CASH_RECEIPT
                        counter, _ = VoucherCounter.objects.select_for_update().get_or_create(
                            session=session, voucher_type=v_type
                        )
                        counter.last_number += 1
                        counter.save()
                        v_num_str = f"{v_type}-{session.name[:4] if session else '2026'}-{counter.last_number:04d}"

                        Voucher.objects.create(
                            voucher_no=v_num_str,
                            voucher_type=v_type,
                            session=session,
                            voucher_date=p["date"],
                            debit_account=cash_ledger,
                            credit_account=school.ledger_account,
                            amount=p["amount"],
                            paid_to_or_received_from=school.name,
                            narration=p["narration"],
                            payment_mode=p["mode"],
                            physical_slip_no=p["ref"],
                        )

        self.stdout.write(self.style.SUCCESS(
            f"\nProcessed {imported_vouchers} payments totaling Rs. {total_amount:,.2f}"
        ))
