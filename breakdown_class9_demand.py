import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeStructure, FeeHead, SchoolClass, AcademicSession
from core.fee_engine import _scheduled_structure_demand, _academic_month_cutoff, ACADEMIC_MONTHS

session = AcademicSession.objects.filter(is_active=True).first()
cls_9 = SchoolClass.objects.filter(name='IX').first()
structures = list(FeeStructure.objects.filter(school_class=cls_9, session=session).select_related('fee_head'))

cutoff = _academic_month_cutoff(session, 'AUG')
target_index = ACADEMIC_MONTHS.index('AUG')

print("=== BREAKDOWN FOR NEW STUDENT (e.g. AASHU 9791) ===")
s_new = Student.objects.filter(legacy_sid='9791').first()
tot_new = 0
for fs in structures:
    d = _scheduled_structure_demand(fs, is_new_student=True, student=s_new, session=session, cutoff=cutoff, target_index=target_index)
    if d > 0:
        print(f"  {fs.fee_head.name:25} | Rs. {d}")
        tot_new += d
print(f"Total Scheduled Demand for NEW student up to AUG: Rs. {tot_new}")

print("\n=== BREAKDOWN FOR OLD/PROMOTED STUDENT (e.g. ABHINANDAN 9689) ===")
s_old = Student.objects.filter(legacy_sid='9689').first()
tot_old = 0
for fs in structures:
    d = _scheduled_structure_demand(fs, is_new_student=False, student=s_old, session=session, cutoff=cutoff, target_index=target_index)
    if d > 0:
        print(f"  {fs.fee_head.name:25} | Rs. {d}")
        tot_old += d
print(f"Total Scheduled Demand for OLD student up to AUG: Rs. {tot_old}")
