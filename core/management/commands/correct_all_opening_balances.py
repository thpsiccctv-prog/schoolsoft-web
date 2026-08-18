import csv
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Student, StudentOpeningBalance, AcademicSession

class Command(BaseCommand):
    help = "Correct all student opening balances to genuine previous year dues (PRV_AMT only)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply fixes to live database")
        parser.add_argument("--confirm", type=str, help="Confirm keyword THPSIC")

    def handle(self, *args, **options):
        apply_mode = options.get("apply")
        confirm = options.get("confirm")

        session = AcademicSession.objects.filter(is_active=True).first()
        if not session:
            self.stdout.write(self.style.ERROR("No active session found"))
            return

        # Read genuine PRV_AMT from FEE.csv
        csv.field_size_limit(2147483647)
        genuine_prv = {}
        with open(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\FEE.csv", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                sid = row.get('SID', '').strip()
                prv = Decimal(row.get('PRV_AMT', '0') or '0')
                if sid and prv > 0:
                    genuine_prv[sid] = prv

        self.stdout.write(self.style.WARNING(f"Genuine previous year dues in FEE.csv: {len(genuine_prv)} students"))
        for sid, amt in genuine_prv.items():
            self.stdout.write(f"  SID {sid}: Rs. {amt}")

        all_obs = StudentOpeningBalance.objects.filter(session=session)
        updated_count = 0
        cleared_count = 0

        if apply_mode and confirm == "THPSIC":
            with transaction.atomic():
                for ob in all_obs:
                    sid = ob.student.legacy_sid or ""
                    correct_amt = genuine_prv.get(sid, Decimal('0.00'))
                    if ob.amount != correct_amt:
                        ob.amount = correct_amt
                        ob.save(update_fields=["amount"])
                        updated_count += 1
                        if correct_amt == Decimal('0.00'):
                            cleared_count += 1

            self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] Corrected {updated_count} opening balances on live DB! ({cleared_count} artificial balances cleared to Rs. 0)."))
        else:
            self.stdout.write(self.style.NOTICE("\n[DRY RUN] Pass '--apply --confirm THPSIC' to execute."))
