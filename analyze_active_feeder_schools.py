import os
import csv
from collections import Counter

csv.field_size_limit(2147483647)
addmission_35 = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\ADDMISSION.csv"

# Check active students in Django vs sch_name in ADDMISSION
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student

active_sids = set(str(s) for s in Student.objects.filter(is_active=True).values_list('legacy_sid', flat=True) if s)

feeder_counts_2026 = Counter()
section_bc_feeders = Counter()
no_sch_count = 0

with open(addmission_35, encoding="utf-8-sig", errors="ignore") as f:
    for row in csv.DictReader(f):
        sid = str(row.get('sid') or '').strip()
        if sid in active_sids:
            sch = row.get('sch_name', '').strip()
            sec = row.get('section', '').strip()
            cls = row.get('class', '').strip()
            if sch:
                feeder_counts_2026[sch] += 1
                if sec in ['B', 'C']:
                    section_bc_feeders[f"{sch} ({cls}-{sec})"] += 1
            else:
                no_sch_count += 1

print(f"Total active students with sch_name: {sum(feeder_counts_2026.values())}")
print(f"Total active students without sch_name: {no_sch_count}")

print("\n--- Feeder School distribution among Active 2026-2027 Students ---")
for sch, cnt in feeder_counts_2026.most_common(25):
    print(f"  {sch:40}: {cnt} active students")

print("\n--- Section B & C Students by Feeder School ---")
for sch_cls, cnt in section_bc_feeders.most_common(25):
    print(f"  {sch_cls:40}: {cnt} students")
