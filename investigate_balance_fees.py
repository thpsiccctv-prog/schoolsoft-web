import os
import csv

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, StudentOpeningBalance, FeeReceipt

for sid in ['9786', '9003', '9008']:
    s = Student.objects.filter(legacy_sid=sid).first()
    if s:
        ob = StudentOpeningBalance.objects.filter(student=s).first()
        rcps = list(FeeReceipt.objects.filter(student=s).values('receipt_no', 'receipt_date', 'received_amount', 'carried_forward', 'remarks'))
        print(f"SID: {sid} | Name: {s.full_name} | Class: {s.current_class} {s.current_section} | Opening Bal: {ob.amount if ob else 0}")
        for r in rcps:
            print(f"   Receipt: {r['receipt_no']} | Date: {r['receipt_date']} | Amount: ₹{r['received_amount']} | Carried: {r['carried_forward']} | Remarks: {r['remarks']}")

print("\n--- Investigating StuFee.csv for all Balance Fee receipts ---")
csv.field_size_limit(2147483647)
with open(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\StuFee.csv", mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    balance_receipts = []
    for r in reader:
        month = r.get('month', '').upper()
        if 'BALANCE' in month or 'PRV' in month or 'OLD' in month:
            balance_receipts.append(r)

print(f"Total Receipts in StuFee with 'BALANCE' in month field: {len(balance_receipts)}")
for r in balance_receipts[:15]:
    print(f"  SID: {r.get('sid')} | Rcp: {r.get('rcpno')} | Date: {r.get('rdate')} | Paid: ₹{r.get('paid')} | Due: {r.get('due')} | Month: {r.get('month')}")
