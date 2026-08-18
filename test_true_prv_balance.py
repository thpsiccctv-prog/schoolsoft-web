import os
import csv
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, StudentOpeningBalance, AcademicSession
from core.fee_engine import calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()

# Read genuine PRV_AMT from FEE.csv
csv.field_size_limit(2147483647)
genuine_prv = {}
with open(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\FEE.csv", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        sid = row.get('SID', '').strip()
        prv = Decimal(row.get('PRV_AMT', '0') or '0')
        if sid and prv > 0:
            genuine_prv[sid] = prv

print(f"Total students with genuine previous year dues in FEE.csv: {len(genuine_prv)}")
for sid, amt in genuine_prv.items():
    print(f"  SID {sid}: Rs. {amt}")

# Let's test what Aashu Kumari (9791) Due will be if Opening Due is 0
s = Student.objects.filter(legacy_sid='9791').first()
ob = StudentOpeningBalance.objects.filter(student=s).first()
if ob:
    old_amt = ob.amount
    ob.amount = 0
    ob.save()
    res = calculate_student_due(student=s, session=session, through_month='AUG')
    print(f"\nAASHU KUMARI (SID 9791) WITH TRUE OPENING BALANCE (0):")
    print(f"  Gross Demand up to AUG: Rs. {res.gross_demand}")
    print(f"  Received Amount (Paid): Rs. {res.received_amount}")
    print(f"  Concession: Rs. {res.concession_amount}")
    print(f"  Final Due: Rs. {res.due_amount}")
    # Restore for now
    ob.amount = old_amt
    ob.save()
