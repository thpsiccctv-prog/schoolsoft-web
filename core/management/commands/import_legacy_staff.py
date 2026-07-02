import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import LegacyImportBatch, Staff


class Command(BaseCommand):
    help = (
        "Import legacy Emp_Mast.csv export into the Staff model. "
        "Run migration_audit/export_mdb_tables.ps1 with -Tables @('Emp_Mast') first to produce Emp_Mast.csv.\n\n"
        "NOTE: Emp_Mast.EMP_ID is 0 for every row (unused) - the real unique key is CODE. "
        "Basic/DA/O_Allownces are placeholder values in the legacy data (Basic=1.00, DA=0.00 for every "
        "staff member - never actually filled in), so they import as-is but should be corrected in Admin "
        "after import, not treated as real historical salary figures."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-dir",
            default=r"D:\english medium\migration_audit\exports",
            help="Folder containing Emp_Mast.csv.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate CSV without writing to the database.",
        )

    def handle(self, *args, **options):
        source_dir = Path(options["source_dir"])
        staff_csv = source_dir / "Emp_Mast.csv"
        dry_run = options["dry_run"]

        if not staff_csv.exists():
            raise CommandError(
                f"Emp_Mast.csv not found at {staff_csv}. Export it first with:\n"
                "  & 'C:\\Windows\\SysWOW64\\WindowsPowerShell\\v1.0\\powershell.exe' -NoProfile "
                "-ExecutionPolicy Bypass -Command \"& 'D:\\english medium\\migration_audit\\export_mdb_tables.ps1' "
                "-Tables @('Emp_Mast')\""
            )

        rows = self.read_csv(staff_csv)
        summary = {
            "rows_seen": len(rows),
            "rows_imported": 0,
            "rows_skipped_no_name": 0,
        }

        with transaction.atomic():
            for row in rows:
                self.import_row(row, dry_run, summary)

            if dry_run:
                transaction.set_rollback(True)

        if not dry_run:
            LegacyImportBatch.objects.create(
                source_database="SCHOOL7.mdb CSV export",
                source_table="Emp_Mast",
                records_seen=summary["rows_seen"],
                records_imported=summary["rows_imported"],
                notes="Basic/DA/O_Allownces imported as-is from legacy placeholder values; review in Admin.",
            )

        mode = "DRY RUN" if dry_run else "IMPORT"
        self.stdout.write(self.style.SUCCESS(f"{mode} complete."))
        for key, value in summary.items():
            self.stdout.write(f"{key}: {value}")

    def import_row(self, row, dry_run, summary):
        full_name = self.clean(row.get("NAME"))
        legacy_code = self.to_int(row.get("CODE"))

        if not full_name:
            summary["rows_skipped_no_name"] += 1
            return

        if dry_run:
            summary["rows_imported"] += 1
            return

        defaults = {
            "full_name": full_name,
            "designation": self.clean(row.get("Designation")),
            "qualification": self.clean(row.get("Qualification")),
            "phone": self.clean(row.get("PHONE")),
            "email": self.clean(row.get("EMAIL")) if self.looks_like_email(row.get("EMAIL")) else "",
            "address": self.join_address(row, "ADD1", "ADD2", "ADD3"),
            "date_of_birth": self.parse_date(row.get("BIRTH_DATE")),
            "date_of_joining": self.parse_date(row.get("DOJ")),
            "date_of_leaving": self.parse_date(row.get("DOL")),
            "pf_applicable": self.clean(row.get("PF_A")) not in {"", "0"},
            "pf_account_no": self.clean(row.get("PF_Account")),
            "esi_applicable": self.clean(row.get("ESI_A")) not in {"", "0"},
            "esi_account_no": self.clean(row.get("ESI_Account_No")),
            "basic_pay": self.to_decimal(row.get("Basic")) or Decimal("0.00"),
            "da": self.to_decimal(row.get("DA")) or Decimal("0.00"),
            "other_allowances": self.to_decimal(row.get("O_Allownces")) or Decimal("0.00"),
            "is_active": self.clean(row.get("SCHOOL_LEFT")) in {"", "0"},
        }

        if legacy_code:
            Staff.objects.update_or_create(legacy_emp_code=legacy_code, defaults=defaults)
        else:
            Staff.objects.update_or_create(full_name=full_name, defaults=defaults)

        summary["rows_imported"] += 1

    def read_csv(self, path):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def clean(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def looks_like_email(self, value):
        cleaned = self.clean(value)
        return "@" in cleaned

    def to_int(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            return None

    def to_decimal(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
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

    def join_address(self, row, *keys):
        parts = [self.clean(row.get(key)) for key in keys]
        return ", ".join(part for part in parts if part)
