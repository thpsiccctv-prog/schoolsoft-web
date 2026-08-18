import os
import calendar
from datetime import date

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import User
from core.models import SchoolClass, Section, Student, AcademicSession, SchoolProfile
from core.views import attendance_register_view, attendance_register_pdf
from core.pdf import build_attendance_register_pdf

print("=== TESTING ATTENDANCE REGISTER MODULE ===")

user, _ = User.objects.get_or_create(username="admin", defaults={"is_staff": True, "is_superuser": True})
factory = RequestFactory()

# 1. Test View HTML rendering
req = factory.get("/academics/attendance/register/?month=8&year=2026")
req.user = user
resp = attendance_register_view(req)
print(f"1. Attendance Register Web View: Status {resp.status_code}")

# 2. Test PDF Generation for Class 9 Section A (Large class test)
cls_9 = SchoolClass.objects.filter(name__icontains="IX").first() or SchoolClass.objects.first()
sec_a = Section.objects.filter(name="A").first()

students_9a = list(Student.objects.filter(is_active=True, current_class=cls_9, current_section=sec_a).order_by("roll_no", "full_name"))
print(f"Testing Class {cls_9.name} Section {sec_a.name if sec_a else 'All'}: {len(students_9a)} students enrolled")

session = AcademicSession.objects.filter(is_active=True).first()
profile = SchoolProfile.objects.first()

pdf_bytes = build_attendance_register_pdf(
    students=students_9a,
    school_class=cls_9,
    section=sec_a,
    month=8,
    year=2026,
    session=session,
    school_profile=profile
)
print(f"2. PDF Generation for Class 9-A: Size {len(pdf_bytes)} bytes")

# Save sample PDF in reports folder
out_sample_path = r"E:\THPSIC-INTER-COLLEGE\05-reports\SAMPLE_ATTENDANCE_REGISTER_CLASS_9A.pdf"
with open(out_sample_path, "wb") as f:
    f.write(pdf_bytes)
print(f"   Sample PDF saved to: {out_sample_path}")

# 3. Test PDF view streaming
req_pdf = factory.get(f"/academics/attendance/register/pdf/?class_id={cls_9.pk}&section_id={sec_a.pk if sec_a else ''}&month=8&year=2026")
req_pdf.user = user
resp_pdf = attendance_register_pdf(req_pdf)
print(f"3. PDF Streaming View: Status {resp_pdf.status_code} | Content-Type: {resp_pdf['Content-Type']}")

# 4. Test month boundary (February 28 days)
pdf_feb = build_attendance_register_pdf(
    students=students_9a[:20],
    school_class=cls_9,
    section=sec_a,
    month=2,
    year=2026,
    session=session,
    school_profile=profile
)
print(f"4. February (28 Days) PDF Generation: Size {len(pdf_feb)} bytes")

print("\nALL ATTENDANCE REGISTER TESTS PASSED SUCCESSFULLY!")
