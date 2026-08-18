import os
import csv
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()
from django.db import transaction
from core.models import FeederSchool, Student, AccountGroup, LedgerAccount, Voucher

addmission_path = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\ADDMISSION.csv"
csv.field_size_limit(2147483647)

sid_to_sch = {}
with open(addmission_path, encoding="utf-8-sig", errors="ignore") as f:
    for row in csv.DictReader(f):
        sid = str(row.get("sid") or "").strip()
        sch = (row.get("sch_name") or "").strip().upper()
        if sid and sch:
            sid_to_sch[sid] = sch

debtors_group, _ = AccountGroup.objects.get_or_create(
    name="Sundry Debtors",
    defaults={"group_type": AccountGroup.GroupType.ASSET, "display_order": 15}
)

with transaction.atomic():
    # 1. Get or create SAMIM SIR SCHOOL
    samim_ledger, _ = LedgerAccount.objects.get_or_create(
        name="SAMIM SIR SCHOOL A/C",
        defaults={"group": debtors_group, "opening_balance": Decimal("0.00")}
    )
    samim_school, _ = FeederSchool.objects.get_or_create(
        code="SCH-SAMIMSIR",
        defaults={
            "name": "SAMIM SIR SCHOOL",
            "contact_person": "Samim Sir",
            "phone": "",
            "village_address": "Dudahi, Kushinagar",
            "package_rate_per_student": Decimal("1500.00"),
            "ledger_account": samim_ledger,
            "is_active": True,
        }
    )
    if samim_school.name != "SAMIM SIR SCHOOL":
        samim_school.name = "SAMIM SIR SCHOOL"
        samim_school.save(update_fields=["name"])

    # 2. Rename existing CMPS SCHOOL (SAMIM SIR) to CMPS SCHOOL
    cmps_school = FeederSchool.objects.filter(code="SCH-CMPS").first()
    if not cmps_school:
        cmps_school = FeederSchool.objects.filter(name__icontains="CMPS").first()
    
    if cmps_school:
        cmps_school.name = "CMPS SCHOOL"
        cmps_school.contact_person = "Director CMPS"
        cmps_school.save(update_fields=["name", "contact_person"])
        if cmps_school.ledger_account:
            cmps_school.ledger_account.name = "CMPS SCHOOL A/C"
            cmps_school.ledger_account.save(update_fields=["name"])

    # 3. Re-assign students based on exact legacy label
    samim_count = 0
    cmps_count = 0
    
    for s in Student.objects.filter(is_active=True):
        sid = str(s.legacy_sid or "")
        legacy_sch = sid_to_sch.get(sid, "")
        
        if legacy_sch == "SAMIM SIR CMPS 2":
            s.feeder_school = samim_school
            s.save(update_fields=["feeder_school"])
            samim_count += 1
        elif legacy_sch in ["CMPS SCHOOL", "CMPS 2022"]:
            s.feeder_school = cmps_school
            s.save(update_fields=["feeder_school"])
            cmps_count += 1

print(f"Split completed successfully!")
print(f"  -> SAMIM SIR SCHOOL: {samim_school.total_enrolled_students} students (Demand: Rs. {samim_school.total_demand:,.2f})")
print(f"  -> CMPS SCHOOL: {cmps_school.total_enrolled_students} students (Demand: Rs. {cmps_school.total_demand:,.2f}, Paid: Rs. {cmps_school.total_received:,.2f}, Balance: Rs. {cmps_school.balance_due:,.2f})")
