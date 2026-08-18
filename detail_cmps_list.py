import os
import csv

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()
from core.models import Student, FeederSchool

addmission_path = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\ADDMISSION.csv"
csv.field_size_limit(2147483647)

sid_to_sch = {}
with open(addmission_path, encoding="utf-8-sig", errors="ignore") as f:
    for row in csv.DictReader(f):
        sid = str(row.get("sid") or "").strip()
        sch = (row.get("sch_name") or "").strip().upper()
        if sid and sch:
            sid_to_sch[sid] = sch

cmps = FeederSchool.objects.filter(name__icontains="CMPS").first()
students = cmps.students.filter(is_active=True).select_related("current_class", "current_section")

print("="*90)
print(f"{'SID':5} | {'Adm No':8} | {'Student Name':24} | {'Class/Sec':12} | {'Legacy Label':18}")
print("="*90)
for s in students.order_by("current_class__display_order", "current_section__name", "full_name"):
    sid = str(s.legacy_sid or "")
    legacy_sch = sid_to_sch.get(sid, "UNKNOWN")
    print(f"{sid:5} | {s.admission_no:8} | {s.full_name:24} | {str(s.current_class):6} {str(s.current_section):6} | {legacy_sch:18}")

print("="*90)
