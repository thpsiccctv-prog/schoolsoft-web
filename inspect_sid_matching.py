import os
import csv

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student

# Sample students from Django
print("Sample Students from Django:")
for s in Student.objects.filter(is_active=True)[:10]:
    print(f"  ID: {s.id} | Adm No: {s.admission_no} | Legacy SID: {s.legacy_sid} | Name: {s.full_name}")

# Check Manish Kumar in Django
manish = Student.objects.filter(full_name__icontains="MANISH KUMAR").all()
print("\nManish Kumar in Django:")
for m in manish:
    print(f"  ID: {m.id} | Adm No: {m.admission_no} | Legacy SID: {m.legacy_sid} | Name: {m.full_name} | Class: {m.current_class}")

# Check StuFee rows in Folder 33
csv.field_size_limit(2147483647)
stufee_33 = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp33\csv-for-analysis\StuFee.csv"
print("\nSample rows from Folder 33 StuFee.csv:")
with open(stufee_33, encoding="utf-8-sig", errors="ignore") as f:
    for r in list(csv.DictReader(f))[:10]:
        print(f"  sid: {r.get('sid')} | code: {r.get('code')} | no: {r.get('no')} | sname: {r.get('sname')}")
