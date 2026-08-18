import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeReceipt, AcademicSession
from core.fee_engine import calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()

print(f"Active Session: {session}")

for sid in ['9786', '9003', '9008', '9112', '9084']:
    s = Student.objects.filter(legacy_sid=sid).first()
    if not s: continue
    
    # Receipts
    rcps = FeeReceipt.objects.filter(student=s, session=session, is_cancelled=False)
    tot_paid_all = sum(r.received_amount for r in rcps)
    tot_paid_non_carried = sum(r.received_amount for r in rcps.filter(carried_forward=False))
    
    print(f"\nStudent SID {sid}: {s.full_name} ({s.current_class} {s.current_section})")
    print(f"  Total Paid in all receipts for 2026-27: Rs. {tot_paid_all}")
    print(f"  Total Paid (excluding carried_forward): Rs. {tot_paid_non_carried}")
    for r in rcps:
        print(f"    Receipt {r.receipt_no}: Rs. {r.received_amount} on {r.receipt_date} (Carried: {r.carried_forward}, Remarks: {r.remarks})")
