import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeReceipt, AcademicSession, StudentOpeningBalance
from core.fee_engine import calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()

sample_sids = ['9791', '9689', '9690', '9786', '9003', '9008', '9112', '9084', '9148']

print("SIMULATING TRUE RECONCILED DUES (WHERE OPENING BALANCE = GENUINE PREVIOUS DUE ONLY):")
print("-" * 85)

for sid in sample_sids:
    s = Student.objects.filter(legacy_sid=sid).first()
    if not s: continue
    
    # Check receipts
    rcps = FeeReceipt.objects.filter(student=s, session=session, is_cancelled=False)
    tot_paid = sum(r.received_amount for r in rcps)
    tot_con = sum(r.concession_amount for r in rcps)
    
    # Calculate with current opening balance
    res_current = calculate_student_due(student=s, session=session, through_month='AUG')
    
    print(f"SID {sid:5} | {s.full_name:20} | Class {str(s.current_class):8} | Sched Fee: Rs.{res_current.scheduled_fee_demand} | Paid: Rs.{tot_paid} | Concession: Rs.{tot_con} | Current Due: Rs.{res_current.due_amount}")
