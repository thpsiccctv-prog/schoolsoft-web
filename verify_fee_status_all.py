import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeReceipt, AcademicSession
from core.fee_engine import calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()

# Check sample students across various classes
sample_sids = ['9786', '9003', '9008', '9112', '9084', '9148', '9791', '9689', '9690']

print(f"{'SID':5} | {'Student Name':20} | {'Class':8} | {'Gross':8} | {'Paid':8} | {'Due':8} | {'Status'}")
print("-" * 75)

for sid in sample_sids:
    s = Student.objects.filter(legacy_sid=sid).first()
    if not s: continue
    res = calculate_student_due(student=s, session=session, through_month='AUG')
    status = "SETTLED (0 DUE)" if res.due_amount == 0 else f"DUE Rs.{res.due_amount}"
    print(f"{sid:5} | {s.full_name[:20]:20} | {str(s.current_class)[:8]:8} | Rs.{res.gross_demand:<5} | Rs.{res.received_amount:<5} | Rs.{res.due_amount:<5} | {status}")
