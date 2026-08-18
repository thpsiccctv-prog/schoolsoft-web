import os
import csv
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeReceipt, AcademicSession, StudentOpeningBalance
from core.fee_engine import calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()

csv.field_size_limit(2147483647)
stu33 = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp33\csv-for-analysis\StuFee.csv"
stu35 = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\StuFee.csv"

for sid in ['9101', '9090']:
    print(f"\n==================== DEEP CHECK: SID {sid} ====================")
    s = Student.objects.filter(legacy_sid=sid).first()
    if s:
        print(f"Student: {s.full_name} | Class: {s.current_class} | Sec: {s.current_section}")
    
    print("\n--- Receipts in 2025-2026 (Folder 33) ---")
    with open(stu33, encoding="utf-8-sig", errors="ignore") as f:
        for r in csv.DictReader(f):
            if r.get('sid') == sid:
                print(f"  Rcp {r.get('rcpno'):4} | Date: {r.get('v_date')[:10]} | Month: {r.get('MONTH'):25} | Paid: Rs.{r.get('paid'):6} | Due: Rs.{r.get('due'):6}")
                
    print("\n--- Receipts in 2026-2027 (Folder 35) ---")
    with open(stu35, encoding="utf-8-sig", errors="ignore") as f:
        for r in csv.DictReader(f):
            if r.get('sid') == sid:
                print(f"  Rcp {r.get('rcpno'):4} | Date: {r.get('v_date')[:10]} | Month: {r.get('MONTH'):25} | Paid: Rs.{r.get('paid'):6} | Due: Rs.{r.get('due'):6}")
                
    if s:
        res = calculate_student_due(student=s, session=session, through_month='AUG')
        print("\n--- Current Calculation in New Software ---")
        print(f"  Opening Due: Rs. {res.opening_balance_amount}")
        print(f"  2026-27 Sched Demand: Rs. {res.scheduled_fee_demand}")
        print(f"  2026-27 Paid (StuFee): Rs. {res.received_amount}")
        print(f"  Concession: Rs. {res.concession_amount}")
        print(f"  Final Due Amount: Rs. {res.due_amount}")
