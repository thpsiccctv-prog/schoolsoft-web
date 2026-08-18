import os
import calendar
from datetime import date

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import SchoolClass, Section, Student, AcademicSession, SchoolProfile
from core.pdf import build_attendance_register_pdf

session = AcademicSession.objects.filter(is_active=True).first()
profile = SchoolProfile.objects.first()

cls_ix = SchoolClass.objects.filter(name="IX").first()
sec_a = Section.objects.filter(school_class=cls_ix, name="A").first()

students_ixa = list(Student.objects.filter(is_active=True, current_class=cls_ix, current_section=sec_a).order_by("roll_no", "full_name"))
print(f"Class IX Section A: {len(students_ixa)} active students")

pdf_bytes = build_attendance_register_pdf(
    students=students_ixa,
    school_class=cls_ix,
    section=sec_a,
    month=8,
    year=2026,
    session=session,
    school_profile=profile
)
print(f"Generated PDF for Class IX Section A ({len(students_ixa)} students): Size = {len(pdf_bytes):,} bytes")

sample_path = r"E:\THPSIC-INTER-COLLEGE\05-reports\ATTENDANCE_REGISTER_CLASS_IX_A_AUGUST_2026.pdf"
with open(sample_path, "wb") as f:
    f.write(pdf_bytes)
print(f"Saved sample printable PDF to {sample_path}")
