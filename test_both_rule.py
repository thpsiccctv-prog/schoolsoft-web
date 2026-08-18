import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeHead, SchoolClass, AcademicSession
from core.fee_engine import calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()

# Apply the change
fh = FeeHead.objects.get(id=16) # Admission / Reg Fee
fh.applies_to = 'both'
fh.old_student_charge_rule = 'fixed_months'
fh.old_student_charge_months = ['APR']
fh.save()

print("Testing Class IX sample students with Admission / Reg Fee (Rs. 2000) applied to BOTH (New + Old):")
sample_sids = ['9791', '9689', '9690', '9786']

for sid in sample_sids:
    s = Student.objects.filter(legacy_sid=sid).first()
    res = calculate_student_due(student=s, session=session, through_month='AUG')
    print(f"SID {sid:5} | {s.full_name:20} | Type: {'New' if res.is_new_student else 'Old':4} | Gross Demand: Rs.{res.gross_demand} | Paid: Rs.{res.received_amount} | Concession: Rs.{res.concession_amount} | Due: Rs.{res.due_amount}")

print("\nTesting Class XI sample students:")
xi_students = Student.objects.filter(is_active=True, current_class__name__startswith='XI').order_by('admission_no')[:5]
for s in xi_students:
    res = calculate_student_due(student=s, session=session, through_month='AUG')
    print(f"SID {s.legacy_sid:5} | {s.full_name:20} | Class: {str(s.current_class):10} | Type: {'New' if res.is_new_student else 'Old':4} | Gross Demand: Rs.{res.gross_demand} | Paid: Rs.{res.received_amount} | Due: Rs.{res.due_amount}")
