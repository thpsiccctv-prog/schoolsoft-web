import os
import csv
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, StudentOpeningBalance, FeeReceipt

csv.field_size_limit(2147483647)

# Read FEE.csv
fee_initial = {}
with open(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\FEE.csv", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        sid = row.get('SID', '').strip()
        if not sid: continue
        curr = Decimal(row.get('CURR_AMT', '0') or '0')
        prv = Decimal(row.get('PRV_AMT', '0') or '0')
        tot = curr + prv
        if tot > 0:
            fee_initial[sid] = tot

# Read StuFee.csv balance payments
balance_paid = {}
with open(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\StuFee.csv", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        sid = row.get('sid', '').strip()
        if not sid: continue
        month = (row.get('MONTH', '') or '').upper()
        due_fee = Decimal(row.get('DUE_FEE', '0') or '0')
        paid = Decimal(row.get('paid', '0') or '0')
        
        # Check if receipt is for balance
        if 'BALANCE' in month or due_fee > 0:
            balance_paid[sid] = balance_paid.get(sid, Decimal('0')) + paid

print(f"Total students in FEE.csv with balance > 0: {len(fee_initial)}")
print(f"Total students who paid Balance receipts in StuFee.csv: {len(balance_paid)}")

fully_cleared = []
partially_cleared = []
zero_paid_remaining = []

for sid, initial_due in fee_initial.items():
    paid = balance_paid.get(sid, Decimal('0'))
    rem = initial_due - paid
    if paid >= initial_due:
        fully_cleared.append((sid, initial_due, paid, rem))
    elif paid > 0:
        partially_cleared.append((sid, initial_due, paid, rem))
    else:
        zero_paid_remaining.append((sid, initial_due, paid, rem))

print(f"\n1. Fully Cleared Balance Students (Opening Due was Paid): {len(fully_cleared)} students")
tot_cleared = sum(x[1] for x in fully_cleared)
print(f"   Total Amount Cleared: ₹{tot_cleared}")
for sid, initial, p, r in fully_cleared[:10]:
    s = Student.objects.filter(legacy_sid=sid).first()
    name = s.full_name if s else "Unknown"
    print(f"   SID: {sid:5} | {name:22} | Initial: ₹{initial:6} | Paid: ₹{p:6} | Remaining Due: ₹{r:6}")

print(f"\n2. Partially Cleared Balance Students: {len(partially_cleared)} students")
for sid, initial, p, r in partially_cleared[:10]:
    s = Student.objects.filter(legacy_sid=sid).first()
    name = s.full_name if s else "Unknown"
    print(f"   SID: {sid:5} | {name:22} | Initial: ₹{initial:6} | Paid: ₹{p:6} | Remaining Due: ₹{r:6}")

print(f"\n3. Genuine Unpaid Opening Balance Students: {len(zero_paid_remaining)} students")
tot_unpaid = sum(x[1] for x in zero_paid_remaining)
print(f"   Total Unpaid Amount: ₹{tot_unpaid}")
