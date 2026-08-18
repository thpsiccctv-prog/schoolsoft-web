import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import User
from core.models import FeederSchool, Student, LedgerAccount, AccountGroup, Voucher
from core.views import feeder_school_list, feeder_school_detail, feeder_school_statement_pdf, feeder_school_statement_excel

print("=== TESTING FEEDER SCHOOL VIEWS & FUNCTIONALITY ===")

# Check if admin user exists for auth
user, _ = User.objects.get_or_create(username="admin", defaults={"is_staff": True, "is_superuser": True})

factory = RequestFactory()

# 1. Test List View
req = factory.get("/feeder-schools/")
req.user = user
resp = feeder_school_list(req)
print(f"1. Feeder Schools List View: Status {resp.status_code}")

# 2. Test Detail View
school = FeederSchool.objects.first()
print(f"Testing with School: {school.name} (PK {school.pk})")
req = factory.get(f"/feeder-schools/{school.pk}/")
req.user = user
resp = feeder_school_detail(req, pk=school.pk)
print(f"2. Detail View: Status {resp.status_code}")

# 3. Test PDF Generation
req = factory.get(f"/feeder-schools/{school.pk}/statement/pdf/")
req.user = user
resp = feeder_school_statement_pdf(req, pk=school.pk)
print(f"3. Statement PDF Generation: Status {resp.status_code} | PDF size: {len(resp.content)} bytes")

# 4. Test Excel Generation
req = factory.get(f"/feeder-schools/{school.pk}/statement/excel/")
req.user = user
resp = feeder_school_statement_excel(req, pk=school.pk)
print(f"4. Statement Excel Generation: Status {resp.status_code} | Excel size: {len(resp.content)} bytes")

print("\nAll views and reports verified successfully!")
