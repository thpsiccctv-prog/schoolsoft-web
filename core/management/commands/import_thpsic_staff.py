import csv
import sys
csv.field_size_limit(2147483647)
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Staff

class Command(BaseCommand):
    help = "Import legacy Emp_Mast CSV into Staff model."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=str,
            default=r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\Emp_Mast.csv",
            help="Path to exported Emp_Mast.csv.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write to the database instead of dry-run.",
        )
        parser.add_argument(
            "--confirm",
            type=str,
            help="Confirmation string 'THPSIC' to allow live apply.",
        )

    def handle(self, *args, **options):
        source_path = Path(options["source"])
        dry_run = not options["apply"]

        if not dry_run and options["confirm"] != "THPSIC":
            raise CommandError("You must provide --confirm THPSIC to run with --apply")

        if not source_path.exists():
            raise CommandError(f"Source file not found: {source_path}")

        summary = {
            "rows_read": 0,
            "staff_imported": 0,
            "placeholder_salary": 0,
            "skipped": 0,
        }

        with source_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            
            with transaction.atomic():
                for row in reader:
                    summary["rows_read"] += 1
                    
                    code_str = self.clean(row.get("CODE"))
                    if not code_str:
                        summary["skipped"] += 1
                        continue
                        
                    legacy_code = int(float(code_str))
                    
                    # Skip rows without names or empty
                    full_name = self.clean(row.get("NAME"))
                    if not full_name:
                        summary["skipped"] += 1
                        continue

                    designation = self.clean(row.get("Designation"))
                    is_active = (self.clean(row.get("SCHOOL_LEFT")) == "0")
                    
                    basic_pay = self.money(row.get("Basic"))
                    if basic_pay == Decimal("1.00"):
                        summary["placeholder_salary"] += 1
                        
                    staff_type = self.map_staff_type(designation)

                    if not dry_run:
                        Staff.objects.update_or_create(
                            legacy_emp_code=legacy_code,
                            defaults={
                                "full_name": full_name,
                                "designation": designation,
                                "staff_type": staff_type,
                                "qualification": self.clean(row.get("Qualification")),
                                "phone": self.clean(row.get("PHONE")),
                                "email": self.clean(row.get("EMAIL")) if self.looks_like_email(row.get("EMAIL")) else "",
                                "address": self.join_address(row, "ADD1", "ADD2", "ADD3"),
                                "date_of_birth": self.parse_date(row.get("BIRTH_DATE")),
                                "date_of_joining": self.parse_date(row.get("DOJ")),
                                "date_of_leaving": self.parse_date(row.get("DOL")),
                                "pf_applicable": self.clean(row.get("PF_A")) == "1",
                                "pf_account_no": self.clean_account(row.get("PF_Account")),
                                "esi_applicable": self.clean(row.get("ESI_A")) == "1",
                                "esi_account_no": self.clean_account(row.get("ESI_Account_No")),
                                "basic_pay": basic_pay,
                                "da": self.money(row.get("DA")),
                                "other_allowances": self.money(row.get("O_Allownces")),
                                "is_active": is_active,
                            }
                        )
                    summary["staff_imported"] += 1

        mode = "DRY RUN" if dry_run else "IMPORT"
        self.stdout.write(self.style.SUCCESS(f"{mode} complete."))
        self.stdout.write(f"DB: {settings.DATABASES['default']['NAME']}")
        self.stdout.write(f"Source: {source_path}")
        for key, val in summary.items():
            self.stdout.write(f"{key}: {val}")

    def clean(self, value):
        if not value:
            return ""
        return str(value).strip()

    def clean_account(self, value):
        cleaned = self.clean(value)
        return "" if cleaned == "0" else cleaned

    def join_address(self, row, *keys):
        parts = [self.clean(row.get(key)) for key in keys]
        return ", ".join(part for part in parts if part)

    def looks_like_email(self, value):
        return "@" in self.clean(value)

    def map_staff_type(self, designation):
        cleaned = self.clean(designation).upper()
        if cleaned in {"PRINCIPAL", "CLERK", "COMPUTER OPERATOR"}:
            return Staff.StaffType.ADMIN
        if cleaned in {"PEON", "GATE MAN", "BUS DRIVER"}:
            return Staff.StaffType.NON_TEACHING
        if "TEACHER" in cleaned or "LECTURER" in cleaned:
            return Staff.StaffType.TEACHING
        return Staff.StaffType.OTHER

    def parse_date(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return None
        # Try multiple formats
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                pass
        return None

    def money(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return Decimal("0.00")
        try:
            return Decimal(cleaned).quantize(Decimal("0.01"))
        except InvalidOperation:
            return Decimal("0.00")
