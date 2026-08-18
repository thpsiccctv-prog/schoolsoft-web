import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, SchoolClass, Section, AcademicSession
from core.fee_engine import calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()

print("Testing demand for Section B and C students when is_zero_fee_section is False:")

sample_students = [
    ('IX', 'B', 'AAIF RAJA'),
    ('IX', 'B', 'ABHISHEK'),
    ('IX', 'C', 'AARYA ASHIRWAD SUNIL'),
    ('IX', 'C', 'ABHAY PAL'),
    ('XI (BIO)', 'C', 'KASHIF RAJA'),
]

for cname, sec_name, sname in sample_students:
    s = Student.objects.filter(is_active=True, current_class__name=cname, current_section__name=sec_name, full_name__icontains=sname).first()
    if s:
        # Mock is_zero_fee_section to False
        s.__class__.is_zero_fee_section = property(lambda self: False)
        res = calculate_student_due(student=s, session=session, through_month='AUG')
        print(f"SID {s.legacy_sid:5} | {s.full_name:25} | Class: {str(s.current_class):10} | Sec: {sec_name} | Demand: Rs.{res.gross_demand} | Paid: Rs.{res.received_amount} | Due: Rs.{res.due_amount}")
