import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, AcademicSession
from core.fee_engine import calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()

print("=== LIVE RECONCILED DUES VERIFICATION AFTER 2025-2026 MIGRATION ===")
sample_sids = ['9087', '8981', '8966', '9294', '9791', '9689', '9690', '9786']

print(f"{'SID':5} | {'Student Name':22} | {'Class':10} | {'Opening Due':12} | {'2026 Sched':11} | {'2026 Paid':10} | {'Concession':10} | {'FINAL DUE':12}")
print("-" * 105)

for sid in sample_sids:
    s = Student.objects.filter(legacy_sid=sid).first()
    if not s: continue
    res = calculate_student_due(student=s, session=session, through_month='AUG')
    print(f"{sid:5} | {s.full_name:22} | {str(s.current_class):10} | Rs.{res.opening_balance_amount:9,.2f} | Rs.{res.scheduled_fee_demand:8,.2f} | Rs.{res.received_amount:7,.2f} | Rs.{res.concession_amount:7,.2f} | Rs.{res.due_amount:9,.2f}")
