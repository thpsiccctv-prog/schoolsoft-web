import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeStructure, SchoolClass, Section, AcademicSession
from core.fee_engine import _fee_structure_queryset_for_student, calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()

print("=== INSPECTING FEE STRUCTURES AND SECTIONS ===")
print("\nAll Sections in DB:")
for sec in Section.objects.all().select_related('school_class').order_by('school_class__display_order', 'name'):
    print(f"  Section ID {sec.id:2}: Class {sec.school_class.name} - Section {sec.name}")

# Let's inspect IX-B and IX-C sample students
for cname, sname in [('IX', 'B'), ('IX', 'C'), ('XI (BIO)', 'C')]:
    st = Student.objects.filter(is_active=True, current_class__name=cname, current_section__name=sname).first()
    if st:
        qs = _fee_structure_queryset_for_student(student=st, session=session)
        print(f"\nStudent: {st.full_name} | Class: {st.current_class} | Section: {st.current_section}")
        print(f"  Fee Structures Count: {qs.count()}")
        for fs in qs:
            print(f"    FS {fs.id}: {fs.fee_head.name} = Rs.{fs.amount} (Active: {fs.is_active})")
        res = calculate_student_due(student=st, session=session, through_month='AUG')
        print(f"  Result -> Gross Demand: Rs.{res.gross_demand} | Scheduled: Rs.{res.scheduled_fee_demand} | Due: Rs.{res.due_amount}")
