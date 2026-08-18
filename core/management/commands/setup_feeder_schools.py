import csv
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import AccountGroup, LedgerAccount, FeederSchool, Student

FEEDER_SCHOOL_DEFINITIONS = [
    {
        "name": "SHIVPUJAN SCHOOL",
        "code": "SCH-SHIVPUJAN",
        "contact_person": "Shivpujan Yadav",
        "phone": "",
        "village_address": "Dharmpur Parvat, Kushinagar",
        "rate": Decimal("1500.00"),
        "aliases": ["SHIVPUJAN SCHOOL"],
    },
    {
        "name": "GREEN LAND PUBLIC SCHOOL",
        "code": "SCH-GREENLAND",
        "contact_person": "Salim Ansari",
        "phone": "",
        "village_address": "Dudahi, Kushinagar",
        "rate": Decimal("1500.00"),
        "aliases": ["GREEN LAND", "GREENLAND PUBLIC SCHOOL"],
    },
    {
        "name": "CMPS SCHOOL",
        "code": "SCH-CMPS",
        "contact_person": "Director CMPS",
        "phone": "",
        "village_address": "Dudahi, Kushinagar",
        "rate": Decimal("1500.00"),
        "aliases": ["CMPS SCHOOL", "CMPS 2022"],
    },
    {
        "name": "SAMIM SIR SCHOOL",
        "code": "SCH-SAMIMSIR",
        "contact_person": "Samim Sir",
        "phone": "",
        "village_address": "Dudahi, Kushinagar",
        "rate": Decimal("1500.00"),
        "aliases": ["SAMIM SIR CMPS 2", "SAMIM SIR SCHOOL"],
    },
    {
        "name": "MD GULAB SCHOOL",
        "code": "SCH-MDGULAB",
        "contact_person": "Md Gulab",
        "phone": "",
        "village_address": "Dudahi, Kushinagar",
        "rate": Decimal("1500.00"),
        "aliases": ["MD GULAB", "GULAB ALI 2022"],
    },
    {
        "name": "NIRAJ GIRI SCHOOL",
        "code": "SCH-NIRAJGIRI",
        "contact_person": "Niraj Giri",
        "phone": "",
        "village_address": "Dudahi, Kushinagar",
        "rate": Decimal("1500.00"),
        "aliases": ["NIRAJ GIRI SCHOOL"],
    },
    {
        "name": "SHUBHAM SIR SCHOOL",
        "code": "SCH-SHUBHAMSIR",
        "contact_person": "Shubham Kumar Rauniyar",
        "phone": "",
        "village_address": "Dudahi, Kushinagar",
        "rate": Decimal("1500.00"),
        "aliases": ["SHUBHAM SIR SCHOOL", "SUBHAM KUMAR RAUNIYAR"],
    },
    {
        "name": "MADARSHA GAUSIYA",
        "code": "SCH-MADARSHAGAUSIYA",
        "contact_person": "",
        "phone": "",
        "village_address": "Uchkipatti, Kushinagar",
        "rate": Decimal("1500.00"),
        "aliases": ["MADARSHA GAUSIYA", "MADARSHA GAUSIYA FAIJUL M", "MADARSHA SHAHPUR UCHKIPATTI"],
    },
    {
        "name": "CHHOTELAL KUSHWAHA SCHOOL",
        "code": "SCH-CHHOTELAL",
        "contact_person": "Chhote Lal Kushwaha",
        "phone": "",
        "village_address": "Dudahi, Kushinagar",
        "rate": Decimal("1500.00"),
        "aliases": ["CHHOTELAL KUSHWAHA"],
    },
    {
        "name": "D.N. SMART SCHOOL",
        "code": "SCH-DNSMART",
        "contact_person": "Sandeep Kushwaha",
        "phone": "",
        "village_address": "Chaf, Kushinagar",
        "rate": Decimal("1500.00"),
        "aliases": ["D.N. SMART SCHOOL CHAF 2022"],
    },
    {
        "name": "GIRI JI TILKA PATTI",
        "code": "SCH-GIRIJI",
        "contact_person": "Giri Ji",
        "phone": "",
        "village_address": "Tilka Patti, Kushinagar",
        "rate": Decimal("1500.00"),
        "aliases": ["GIRI JI TILKA PATTI"],
    },
]


class Command(BaseCommand):
    help = "Setup Feeder Schools, Sundry Debtors ledger accounts, and backfill active students."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply changes to the database.")

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        self.stdout.write(self.style.MIGRATE_HEADING("=== SETTING UP FEEDER / ATTACHED SCHOOLS ==="))

        if not apply_changes:
            self.stdout.write(self.style.WARNING("DRY RUN MODE: Pass --apply to persist changes.\n"))

        # 1. Ensure Sundry Debtors group
        debtors_group, created = AccountGroup.objects.get_or_create(
            name="Sundry Debtors",
            defaults={"group_type": AccountGroup.GroupType.ASSET, "display_order": 15},
        )
        if created and apply_changes:
            self.stdout.write(self.style.SUCCESS("Created AccountGroup: 'Sundry Debtors'"))

        # 2. Create Feeder Schools & Ledgers
        alias_to_school = {}
        for f_def in FEEDER_SCHOOL_DEFINITIONS:
            ledger_name = f"{f_def['name']} A/C"
            ledger, l_created = LedgerAccount.objects.get_or_create(
                name=ledger_name,
                defaults={"group": debtors_group, "opening_balance": Decimal("0.00")},
            )
            
            feeder, f_created = FeederSchool.objects.get_or_create(
                name=f_def["name"],
                defaults={
                    "code": f_def["code"],
                    "contact_person": f_def["contact_person"],
                    "phone": f_def["phone"],
                    "village_address": f_def["village_address"],
                    "package_rate_per_student": f_def["rate"],
                    "ledger_account": ledger,
                    "is_active": True,
                },
            )
            if not feeder.ledger_account and apply_changes:
                feeder.ledger_account = ledger
                feeder.save(update_fields=["ledger_account"])

            for alias in f_def["aliases"]:
                alias_to_school[alias.upper()] = feeder

        self.stdout.write(f"Configured {len(FEEDER_SCHOOL_DEFINITIONS)} Feeder Schools with Sundry Debtors Ledgers.")

        # 3. Backfill active students from ADDMISSION.csv
        csv.field_size_limit(2147483647)
        addmission_path = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\ADDMISSION.csv"

        active_students = {
            str(s.legacy_sid): s
            for s in Student.objects.filter(is_active=True).select_related("current_class", "current_section")
            if s.legacy_sid
        }

        updated_count = 0
        assigned_by_school = {f["name"]: 0 for f in FEEDER_SCHOOL_DEFINITIONS}
        unmapped_students = []

        with open(addmission_path, encoding="utf-8-sig", errors="ignore") as f:
            for row in csv.DictReader(f):
                sid = str(row.get("sid") or "").strip()
                if sid in active_students:
                    student = active_students[sid]
                    sch_name = row.get("sch_name", "").strip().upper()
                    target_school = alias_to_school.get(sch_name)

                    if target_school:
                        if student.feeder_school_id != target_school.id:
                            if apply_changes:
                                student.feeder_school = target_school
                                student.save(update_fields=["feeder_school"])
                            updated_count += 1
                        assigned_by_school[target_school.name] += 1
                    else:
                        sec_name = student.current_section.name if student.current_section else ""
                        if sec_name in ["B", "C"]:
                            unmapped_students.append((student, sch_name))

        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully mapped {updated_count} students to Feeder Schools."))
        
        self.stdout.write("\n--- Summary by Feeder School ---")
        total_students = 0
        total_demand = Decimal("0.00")
        for f_def in FEEDER_SCHOOL_DEFINITIONS:
            name = f_def["name"]
            cnt = assigned_by_school[name]
            rate = f_def["rate"]
            demand = cnt * rate
            total_students += cnt
            total_demand += demand
            self.stdout.write(f"  {name:30} | {cnt:3} students | Rate: Rs.{rate:5.0f} | Demand: Rs.{demand:10,.2f}")

        self.stdout.write(self.style.MIGRATE_LABEL(f"\nTotal Attached Students: {total_students} | Total Demand: Rs. {total_demand:,.2f}"))

        if unmapped_students:
            self.stdout.write(self.style.WARNING(f"\nUnmapped Section B/C students ({len(unmapped_students)}):"))
            for s, orig_sch in unmapped_students[:10]:
                self.stdout.write(f"  SID: {s.legacy_sid} | {s.full_name} | Sec: {s.current_section} | Legacy Sch: '{orig_sch}'")
