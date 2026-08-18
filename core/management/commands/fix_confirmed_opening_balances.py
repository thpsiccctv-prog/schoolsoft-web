from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Student, StudentOpeningBalance, FeeReceipt

class Command(BaseCommand):
    help = "Fix confirmed double-charged opening balances for SID 9786, 9003, 9008"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply fixes to live database")
        parser.add_argument("--confirm", type=str, help="Confirm keyword THPSIC")

    def handle(self, *args, **options):
        apply_mode = options.get("apply")
        confirm = options.get("confirm")

        confirmed_sids = [
            ("9786", "ABHISHEK KUMAR GUPTA", "SF-116", 5000),
            ("9003", "RANJANA SHARMA", "SF-583", 4500),
            ("9008", "MERAJ", "SF-276", 10000),
        ]

        self.stdout.write(self.style.WARNING("=== Confirmed Double-Charge Opening Balance Fix ==="))
        
        for sid, name, rcp, amt in confirmed_sids:
            s = Student.objects.filter(legacy_sid=sid).first()
            if not s:
                self.stdout.write(self.style.ERROR(f"Student SID {sid} not found"))
                continue
            
            ob = StudentOpeningBalance.objects.filter(student=s).first()
            current_amt = ob.amount if ob else 0
            self.stdout.write(f"SID: {sid} | Name: {name} | Current Opening Bal: Rs. {current_amt} | Paid via {rcp}: Rs. {amt} -> New Opening Bal: Rs. 0")

        if apply_mode and confirm == "THPSIC":
            with transaction.atomic():
                for sid, name, rcp, amt in confirmed_sids:
                    s = Student.objects.filter(legacy_sid=sid).first()
                    if s:
                        ob = StudentOpeningBalance.objects.filter(student=s).first()
                        if ob:
                            ob.amount = 0
                            ob.save(update_fields=["amount"])
                        else:
                            StudentOpeningBalance.objects.create(student=s, amount=0)
            self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Applied fixes to live database! Opening balances for 3 students set to Rs. 0."))
        else:
            self.stdout.write(self.style.NOTICE("\n[DRY RUN] No changes made. Pass '--apply --confirm THPSIC' to execute."))
