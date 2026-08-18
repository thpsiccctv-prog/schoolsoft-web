import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, StudentOpeningBalance, FeeReceipt
from django.db.models import Sum

print("=== DEEP AUDIT OF ALL 513 OPENING BALANCE STUDENTS ===")
obs = StudentOpeningBalance.objects.filter(amount__gt=0).select_related('student', 'student__current_class', 'student__current_section')
print(f"Total students with Opening Balance > 0: {obs.count()}")

exact_balance_paid = []
partial_balance_paid = []
tuition_paid = []
no_receipts = []

for ob in obs:
    s = ob.student
    rcps = list(FeeReceipt.objects.filter(student=s))
    if not rcps:
        no_receipts.append(ob)
        continue
    
    # Check for balance receipts
    bal_rcps = [r for r in rcps if 'BALANCE' in (r.remarks or '').upper()]
    other_rcps = [r for r in rcps if 'BALANCE' not in (r.remarks or '').upper()]
    
    bal_paid_sum = sum(r.received_amount for r in bal_rcps)
    other_paid_sum = sum(r.received_amount for r in other_rcps)
    
    if bal_rcps and bal_paid_sum == ob.amount:
        exact_balance_paid.append((ob, bal_rcps))
    elif bal_rcps and bal_paid_sum > 0:
        partial_balance_paid.append((ob, bal_rcps, bal_paid_sum))
    elif other_paid_sum > 0:
        tuition_paid.append((ob, other_rcps, other_paid_sum))
    else:
        no_receipts.append(ob)

print(f"\n1. Exact Balance Fee Match (100% Double-Charge Confirmed): {len(exact_balance_paid)}")
for ob, r_list in exact_balance_paid:
    r_details = ", ".join([f"{r.receipt_no}: ₹{r.received_amount} ({r.receipt_date})" for r in r_list])
    print(f"   SID {ob.student.legacy_sid} | {ob.student.full_name} | Class: {ob.student.current_class} | Opening Bal: ₹{ob.amount} | Receipts: {r_details}")

print(f"\n2. Partial / Different Balance Fee Receipts: {len(partial_balance_paid)}")
for ob, r_list, total_bal in partial_balance_paid:
    r_details = ", ".join([f"{r.receipt_no}: ₹{r.received_amount} ({r.receipt_date})" for r in r_list])
    print(f"   SID {ob.student.legacy_sid} | {ob.student.full_name} | Opening Bal: ₹{ob.amount} | Balance Paid: ₹{total_bal} | Receipts: {r_details}")

print(f"\n3. Other Receipts (Tuition/Monthly/etc.): {len(tuition_paid)}")
print(f"4. No Payments / ₹0 Paid: {len(no_receipts)}")
