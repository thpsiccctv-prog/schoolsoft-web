import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeStructure, FeeHead, SchoolClass, AcademicSession
from core.fee_engine import calculate_student_due, _scheduled_structure_demand, _academic_month_cutoff, ACADEMIC_MONTHS

session = AcademicSession.objects.filter(is_active=True).first()
cutoff = _academic_month_cutoff(session, 'AUG')
target_index = ACADEMIC_MONTHS.index('AUG')

print("=== SAFETY CHECK: CLASS X AND CLASS XII FEE BREAKDOWN ===")

# Class X Sample Students
print("\n--- Class X Continuing / Promoted Students ---")
x_students = Student.objects.filter(is_active=True, current_class__name='X').order_by('admission_no')[:5]
for s in x_students:
    res = calculate_student_due(student=s, session=session, through_month='AUG')
    structures = FeeStructure.objects.filter(school_class=s.current_class, session=session).select_related('fee_head')
    applied_heads = []
    for fs in structures:
        amt = _scheduled_structure_demand(fs, is_new_student=res.is_new_student, student=s, session=session, cutoff=cutoff, target_index=target_index)
        if amt > 0:
            applied_heads.append(f"{fs.fee_head.name}: Rs.{amt}")
    print(f"SID {s.legacy_sid:5} | {s.full_name:20} | Type: {'New' if res.is_new_student else 'Old':4} | Gross Demand: Rs.{res.gross_demand} | Paid: Rs.{res.received_amount} | Due: Rs.{res.due_amount}")
    print(f"   Heads: {', '.join(applied_heads)}")

# Class XII Sample Students
print("\n--- Class XII Continuing / Promoted Students ---")
xii_students = Student.objects.filter(is_active=True, current_class__name__startswith='XII').order_by('admission_no')[:5]
for s in xii_students:
    res = calculate_student_due(student=s, session=session, through_month='AUG')
    structures = FeeStructure.objects.filter(school_class=s.current_class, session=session).select_related('fee_head')
    applied_heads = []
    for fs in structures:
        amt = _scheduled_structure_demand(fs, is_new_student=res.is_new_student, student=s, session=session, cutoff=cutoff, target_index=target_index)
        if amt > 0:
            applied_heads.append(f"{fs.fee_head.name}: Rs.{amt}")
    print(f"SID {s.legacy_sid:5} | {s.full_name:20} | Class: {str(s.current_class):10} | Type: {'New' if res.is_new_student else 'Old':4} | Gross Demand: Rs.{res.gross_demand} | Paid: Rs.{res.received_amount} | Due: Rs.{res.due_amount}")
    print(f"   Heads: {', '.join(applied_heads)}")
