import csv
from decimal import Decimal
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import date
from core.models import Student, StudentOpeningBalance, AcademicSession

class Command(BaseCommand):
    help = "Migrate 2025-2026 session closing dues from Folder 33 StuFee into StudentOpeningBalance"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply changes to the live database")
        parser.add_argument("--confirm", type=str, help="Confirmation keyword THPSIC")

    def handle(self, *args, **options):
        apply_mode = options.get("apply")
        confirm = options.get("confirm")

        session = AcademicSession.objects.filter(is_active=True).first()
        if not session:
            self.stdout.write(self.style.ERROR("No active academic session found."))
            return

        stufee_path = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp33\csv-for-analysis\StuFee.csv")
        if not stufee_path.exists():
            self.stdout.write(self.style.ERROR(f"StuFee.csv not found at {stufee_path}"))
            return

        csv.field_size_limit(2147483647)
        students_2025_dues = {}

        with open(stufee_path, encoding="utf-8-sig", errors="ignore") as f:
            for r in csv.DictReader(f):
                sid = str(r.get('sid') or '').strip()
                if not sid:
                    continue
                try:
                    rcp_no = int(float(r.get('rcpno') or 0))
                    due_amt = Decimal(str(r.get('due') or '0').strip())
                except (ValueError, TypeError):
                    continue

                v_date = r.get('v_date', '')
                sname = r.get('sname', '')
                sclass = r.get('sclass', '')

                if sid not in students_2025_dues or rcp_no > students_2025_dues[sid]['last_rcp_no']:
                    students_2025_dues[sid] = {
                        'sid': sid,
                        'name': sname,
                        'class_2025': sclass,
                        'last_rcp_no': rcp_no,
                        'last_date': v_date[:10],
                        'closing_due_2025': due_amt,
                    }

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(students_2025_dues)} students from 2025-2026 session."))

        active_students = Student.objects.filter(is_active=True)
        updated_count = 0
        total_carryover = Decimal('0.00')

        if apply_mode and confirm == "THPSIC":
            with transaction.atomic():
                as_of = session.starts_on or date(2026, 4, 1)
                for s in active_students:
                    sid = str(s.legacy_sid or s.admission_no or "").strip()
                    history = students_2025_dues.get(sid)
                    closing_2025 = history['closing_due_2025'] if history else Decimal('0.00')

                    ob, created = StudentOpeningBalance.objects.get_or_create(
                        student=s,
                        session=session,
                        defaults={
                            "amount": closing_2025,
                            "as_of_date": as_of,
                            "source_reference": f"Session 2025-2026 Last Rcp {history['last_rcp_no']}" if history else "Session 2025-2026 Migration",
                            "note": f"Carried forward from 2025-2026 closing due (Last receipt: {history['last_rcp_no']} on {history['last_date']})" if history else "Zero balance"
                        }
                    )
                    if not created and ob.amount != closing_2025:
                        ob.amount = closing_2025
                        if history:
                            ob.source_reference = f"Session 2025-2026 Last Rcp {history['last_rcp_no']}"
                            ob.note = f"Carried forward from 2025-2026 closing due (Last receipt: {history['last_rcp_no']} on {history['last_date']})"
                        ob.save(update_fields=["amount", "source_reference", "note"])

                    if closing_2025 > Decimal('0.00'):
                        updated_count += 1
                        total_carryover += closing_2025

            self.stdout.write(self.style.SUCCESS(
                f"\n[SUCCESS] Successfully migrated 2025-2026 opening balances to live DB!\n"
                f"  Students with non-zero 2025 carryover: {updated_count}\n"
                f"  Total Carryover Amount: Rs. {total_carryover:,.2f}"
            ))
        else:
            for s in active_students:
                sid = str(s.legacy_sid or s.admission_no or "").strip()
                history = students_2025_dues.get(sid)
                closing_2025 = history['closing_due_2025'] if history else Decimal('0.00')
                if closing_2025 > Decimal('0.00'):
                    updated_count += 1
                    total_carryover += closing_2025

            self.stdout.write(self.style.WARNING(
                f"\n[DRY RUN] Would update {updated_count} students with 2025-2026 carryover (Total: Rs. {total_carryover:,.2f}).\n"
                f"Pass '--apply --confirm THPSIC' to execute on live database."
            ))
