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

# Now check all 85 currently mapped active students
cmps = FeederSchool.objects.filter(name__icontains="CMPS").first()
students = cmps.students.filter(is_active=True).select_related("current_class", "current_section")

by_legacy_sch = {}
for s in students:
    sid = str(s.legacy_sid or "")
    legacy_sch = sid_to_sch.get(sid, "UNKNOWN")
    by_legacy_sch.setdefault(legacy_sch, []).append(s)

print("=" * 80)
print(f"BREAKDOWN OF 85 STUDENTS CURRENTLY UNDER '{cmps.name}':")
print("=" * 80)
for l_sch, s_list in by_legacy_sch.items():
    print(f"\nLegacy Label: '{l_sch}' -> {len(s_list)} active students")
    for s in s_list[:5]:
        print(f"  SID {s.legacy_sid:5} | Adm: {s.admission_no:8} | {s.full_name:25} | {s.current_class} {s.current_section}")

print("=" * 80)
