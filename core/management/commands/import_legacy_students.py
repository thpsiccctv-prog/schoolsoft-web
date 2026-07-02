import csv
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import LegacyImportBatch, SchoolClass, Section, Student


CLASS_ALIASES = {
    "1st": "I",
    "2nd": "II",
    "3rd": "III",
    "4th": "IV",
    "5th": "V",
    "6th": "VI",
    "7th": "VII",
    "8th": "VIII",
    "9th": "IX",
    "10th": "X",
    "11th": "XI",
    "12th": "XII",
    "l.k.g": "LKG",
    "u.k.g": "UKG",
}


class Command(BaseCommand):
    help = "Import legacy CLASS and ADDMISSION CSV exports into normalized phase-1 models."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-dir",
            default=r"D:\english medium\migration_audit\exports",
            help="Folder containing CLASS.csv and ADDMISSION.csv.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate CSV files without writing to the database.",
        )

    def handle(self, *args, **options):
        source_dir = Path(options["source_dir"])
        class_csv = source_dir / "CLASS.csv"
        admission_csv = source_dir / "ADDMISSION.csv"
        dry_run = options["dry_run"]

        if not class_csv.exists():
            raise CommandError(f"CLASS.csv not found: {class_csv}")
        if not admission_csv.exists():
            raise CommandError(f"ADDMISSION.csv not found: {admission_csv}")

        class_rows = self.read_csv(class_csv)
        admission_rows = self.read_csv(admission_csv)

        summary = {
            "classes_seen": len(class_rows),
            "classes_imported": 0,
            "sections_imported": 0,
            "students_seen": len(admission_rows),
            "students_imported": 0,
            "students_skipped": 0,
        }

        with transaction.atomic():
            class_map = self.import_classes(class_rows, dry_run, summary)
            self.import_students(admission_rows, class_map, dry_run, summary)

            if dry_run:
                transaction.set_rollback(True)

        if not dry_run:
            LegacyImportBatch.objects.create(
                source_database="SCHOOL7.mdb CSV export",
                source_table="CLASS, ADDMISSION",
                records_seen=summary["students_seen"],
                records_imported=summary["students_imported"],
                notes=(
                    f"Classes imported/updated: {summary['classes_imported']}; "
                    f"sections imported/updated: {summary['sections_imported']}; "
                    f"students skipped: {summary['students_skipped']}"
                ),
            )

        mode = "DRY RUN" if dry_run else "IMPORT"
        self.stdout.write(self.style.SUCCESS(f"{mode} complete."))
        for key, value in summary.items():
            self.stdout.write(f"{key}: {value}")

    def read_csv(self, path):
        # Access text exports are often Windows-1252, ours are utf-8-sig.
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                with path.open("r", encoding=encoding, newline="") as handle:
                    return list(csv.DictReader(handle))
            except UnicodeDecodeError:
                continue
        raise CommandError(f"Could not decode {path} as utf-8 or cp1252")

    def import_classes(self, rows, dry_run, summary):
        class_map = {}
        for row in rows:
            legacy_name = self.clean(row.get("CNAME"))
            if not legacy_name:
                continue

            normalized_name = self.normalize_class_name(legacy_name)
            legacy_code = self.to_int(row.get("CCODE"))
            display_order = legacy_code or 0

            if dry_run:
                class_map[legacy_name.upper()] = None
                class_map[normalized_name.upper()] = None
                summary["classes_imported"] += 1
                continue

            school_class, _ = SchoolClass.objects.update_or_create(
                name=normalized_name,
                defaults={
                    "legacy_code": legacy_code,
                    "display_order": display_order,
                },
            )
            class_map[legacy_name.upper()] = school_class
            class_map[normalized_name.upper()] = school_class
            summary["classes_imported"] += 1

        return class_map

    def import_students(self, rows, class_map, dry_run, summary):
        for row in rows:
            legacy_sid = self.to_int(row.get("sid"))
            full_name = self.clean(row.get("sname"))

            if not legacy_sid or not full_name:
                summary["students_skipped"] += 1
                continue

            class_name = self.clean(row.get("sclass"))
            section_name = self.clean(row.get("section")) or "A"
            normalized_class_name = self.normalize_class_name(class_name)

            if dry_run:
                summary["students_imported"] += 1
                continue

            school_class = class_map.get(class_name.upper()) or class_map.get(normalized_class_name.upper())
            if school_class is None and normalized_class_name:
                school_class, _ = SchoolClass.objects.get_or_create(
                    name=normalized_class_name,
                    defaults={"display_order": 0},
                )

            section = None
            if school_class and section_name:
                section, created = Section.objects.get_or_create(
                    school_class=school_class,
                    name=section_name,
                )
                if created:
                    summary["sections_imported"] += 1

            defaults = {
                "admission_no": self.clean(row.get("admno")),
                "registration_no": self.clean(row.get("regno")),
                "roll_no": self.to_int(row.get("roll_no")),
                "full_name": full_name,
                "father_name": self.clean(row.get("fname")),
                "mother_name": self.clean(row.get("mname")),
                "gender": self.map_gender(row.get("SEX")),
                "date_of_birth": self.parse_date(row.get("dobfig")),
                "aadhaar_no": self.clean(row.get("aadhar_no")),
                "category": self.clean(row.get("CATE")) or self.clean(row.get("cast")),
                "religion": self.clean(row.get("RELIGEN")),
                "mobile_primary": self.clean(row.get("lmobile")) or self.clean(row.get("pmobile")),
                "mobile_secondary": self.clean(row.get("pphone")) or self.clean(row.get("lphone")),
                "address_permanent": self.join_address(row, "padr1", "padr2", "padr3"),
                "address_local": self.join_address(row, "ladr1", "ladr2", "ladr3"),
                "current_class": school_class,
                "current_section": section,
                "admission_date": self.parse_date(row.get("v_date")),
                "is_active": not self.is_tc_issued(row),
            }

            Student.objects.update_or_create(
                legacy_sid=legacy_sid,
                defaults=defaults,
            )
            summary["students_imported"] += 1

    def normalize_class_name(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return ""

        return CLASS_ALIASES.get(cleaned.lower(), cleaned)

    def is_tc_issued(self, row):
        # In the live Access app, blocked/unblocked matches TC_ISSUE exactly.
        # The older tc flag can be stale, so only use it when TC_ISSUE is blank.
        tc_issue = self.clean(row.get("TC_ISSUE")).upper()
        if tc_issue:
            return tc_issue in {"Y", "YES", "1", "TRUE"}
        return self.clean(row.get("tc")).upper() in {"Y", "YES", "1", "TRUE"}

    def clean(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def to_int(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            return None

    def parse_date(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return None

        for date_format in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(cleaned, date_format).date()
            except ValueError:
                continue

        return None

    def map_gender(self, value):
        cleaned = self.clean(value).upper()
        if cleaned.startswith("M"):
            return Student.Gender.MALE
        if cleaned.startswith("F"):
            return Student.Gender.FEMALE
        if cleaned:
            return Student.Gender.OTHER
        return Student.Gender.UNKNOWN

    def join_address(self, row, *keys):
        parts = [self.clean(row.get(key)) for key in keys]
        return ", ".join(part for part in parts if part)
