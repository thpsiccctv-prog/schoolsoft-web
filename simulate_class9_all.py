import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeStructure, FeeHead, SchoolClass, AcademicSession
from core.fee_engine import calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()
cls_9 = SchoolClass.objects.filter(name='IX').first()

print("Testing Fee Structure adjustment where Class IX Registration/Admission applies to ALL (Both New and Old):")

# Let's inspect current FeeStructures for IX
for fs in FeeStructure.objects.filter(school_class=cls_9, session=session).select_related('fee_head'):
    print(f"  {fs.fee_head.name:25} | Rs.{fs.amount} | Applies to: {fs.fee_head.applies_to}")

# Let's test if we set Admission Fee / Reg Fee to apply to both for Class IX
head_adm = FeeHead.objects.filter(name='Admission Fee').first()
# Temporarily set to both to simulate
orig_applies = head_adm.applies_to if head_adm else 'new'
if head_adm:
    head_adm.applies_to = 'both'
    head_adm.old_student_charge_rule = 'fixed_months'
    head_adm.old_student_charge_months = ['APR']
    head_adm.save()

print("\n--- SIMULATION RESULTS WITH STARTER FEE FOR ALL CLASS IX STUDENTS ---")
for sid in ['9791', '9689', '9690']:
    s = Student.objects.filter(legacy_sid=sid).first()
    res = calculate_student_due(student=s, session=session, through_month='AUG')
    print(f"SID {sid:5} | {s.full_name:20} | Demand up to AUG: Rs.{res.gross_demand} | Paid: Rs.{res.received_amount} | Concession: Rs.{res.concession_amount} | Final Due: Rs.{res.due_amount}")

# Restore
if head_adm:
    head_adm.applies_to = orig_applies
    head_adm.save()
