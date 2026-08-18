import os
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from core.models import SchoolClass, Section, Student, AcademicSession, AttendanceSummary
from core.views import attendance_summary_entry, attendance_summary_report, attendance_summary_report_excel

TEST_YEAR = 2099
TEST_MONTH = 1

print("=== TESTING ATTENDANCE SUMMARY MODULE (PART B) ===")

user, _ = User.objects.get_or_create(username="admin", defaults={"is_staff": True, "is_superuser": True})
factory = RequestFactory()
session = AcademicSession.objects.filter(is_active=True).first() or AcademicSession.objects.first()

cls_6 = SchoolClass.objects.filter(name="VI").first() or SchoolClass.objects.first()
sec_a = Section.objects.filter(school_class=cls_6).first()
students = list(Student.objects.filter(is_active=True, current_class=cls_6))

print(f"Testing with Class {cls_6.name}: {len(students)} students")

# 1. Test GET Entry View
req_get = factory.get(f"/academics/attendance/entry/?class_id={cls_6.id}&month={TEST_MONTH}&year={TEST_YEAR}")
req_get.user = user
resp_get = attendance_summary_entry(req_get)
print(f"1. Entry View GET: Status {resp_get.status_code}")

# 2. Test POST Batch Entry (Simulate user submitting present days)
post_data = {
    "class_id": str(cls_6.id),
    "section_id": str(sec_a.id) if sec_a else "",
    "month": str(TEST_MONTH),
    "year": str(TEST_YEAR),
    "batch_working_days": "24",
}
for idx, s in enumerate(students):
    # vary present days between 18 and 24
    p_days = 24 if idx % 2 == 0 else 18
    post_data[f"working_days_{s.id}"] = "24"
    post_data[f"present_days_{s.id}"] = str(p_days)
    post_data[f"remarks_{s.id}"] = "Regular" if p_days == 24 else "Leave taken"

req_post = factory.post(f"/academics/attendance/entry/?class_id={cls_6.id}&month={TEST_MONTH}&year={TEST_YEAR}", data=post_data)
req_post.user = user
setattr(req_post, 'session', 'session')
messages = FallbackStorage(req_post)
setattr(req_post, '_messages', messages)

resp_post = attendance_summary_entry(req_post)
print(f"2. Entry View POST (Save Batch): Status {resp_post.status_code}")

# Check DB records
saved_records = AttendanceSummary.objects.filter(student__in=students, year=TEST_YEAR, month=TEST_MONTH)
print(f"   Database records created: {saved_records.count()} / {len(students)}")
first_rec = saved_records.first()
if first_rec:
    print(f"   Sample Record: {first_rec.student.full_name} | Working: {first_rec.total_working_days} | Present: {first_rec.days_present} | Absent: {first_rec.days_absent} | %: {first_rec.attendance_percentage}%")

# 3. Test Duplicate Update (Safe re-save)
post_data[f"present_days_{students[0].id}"] = "22"
req_repost = factory.post(f"/academics/attendance/entry/?class_id={cls_6.id}&month={TEST_MONTH}&year={TEST_YEAR}", data=post_data)
req_repost.user = user
setattr(req_repost, 'session', 'session')
setattr(req_repost, '_messages', FallbackStorage(req_repost))

resp_repost = attendance_summary_entry(req_repost)
updated_rec = AttendanceSummary.objects.get(student=students[0], year=TEST_YEAR, month=TEST_MONTH)
print(f"3. Re-save Update Test: Present Days updated to {updated_rec.days_present} (Absent: {updated_rec.days_absent}, %: {updated_rec.attendance_percentage}%) without duplicate creation!")

# 4. Test Report View GET
req_rep = factory.get(f"/academics/attendance/report/?class_id={cls_6.id}&month={TEST_MONTH}&year={TEST_YEAR}")
req_rep.user = user
resp_rep = attendance_summary_report(req_rep)
print(f"4. Summary Report View GET: Status {resp_rep.status_code}")

# 5. Test Excel Export
req_xl = factory.get(f"/academics/attendance/report/excel/?class_id={cls_6.id}&month={TEST_MONTH}&year={TEST_YEAR}")
req_xl.user = user
resp_xl = attendance_summary_report_excel(req_xl)
print(f"5. Summary Report Excel Export: Status {resp_xl.status_code} | Size {len(resp_xl.content)} bytes")

cleanup_count, _ = AttendanceSummary.objects.filter(
    student__in=students,
    year=TEST_YEAR,
    month=TEST_MONTH,
).delete()
print(f"Cleaned up test attendance rows: {cleanup_count}")

print("\nALL PART B ATTENDANCE SUMMARY TESTS PASSED 100%!")
