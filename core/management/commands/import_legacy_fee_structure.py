import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import AcademicSession, FeeHead, FeeStructure, SchoolClass


FEE_HEADS = {
    "ADM": "Admission Fee",
    "DEV": "Development Fee",
    "TUT": "Tuition Fee",
    "COM": "Computer Fee",
    "LIB": "Library Fee",
    "CON": "Conveyance Fee",
    "SCI": "Science Fee",
    "ELE": "Electricity Fee",
    "SPO": "Sports Fee",
    "GEN": "Generator Fee",
    "MED": "Medical Fee",
    "EXA": "Exam Fee",
    "HOS": "Hostel Fee",
    "ANU": "Annual Fee",
    "OTH": "Other Fee",
    "BULD": "Building Fee",
    "HAND": "Handbook Fee",
    "LAB": "Lab Fee",
    "NCONS": "Non-concession Fee",
    "ANUA": "Annual Activity Fee",
    "MAGI": "Magazine Fee",
}

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
    help = "Import class-wise fee structure from legacy Cfee.csv."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=r"D:\english medium\migration_audit\exports\Cfee.csv",
            help="Path to exported Cfee.csv.",
        )
        parser.add_argument(
            "--session",
            default="2026-27",
            help="Session to update with the imported fee structure.",
        )

    def handle(self, *args, **options):
        source = Path(options["source"])
        if not source.exists():
            raise CommandError(f"Cfee CSV not found: {source}")

        rows = self.read_csv(source)
        session = AcademicSession.objects.get_or_create(name=options["session"], defaults={"is_active": True})[0]
        imported = 0
        skipped = 0

        for row in rows:
            if self.clean(row.get("OLD_APP")).upper() == "YES":
                skipped += 1
                continue

            class_name = self.normalize_class_name(row.get("CNAME"))
            if not class_name:
                skipped += 1
                continue

            school_class = SchoolClass.objects.filter(name__iexact=class_name).first()
            if school_class is None:
                school_class = SchoolClass.objects.create(name=class_name, display_order=self.to_int(row.get("CCODE")) or 0)

            for code, head_name in FEE_HEADS.items():
                amount = self.money(row.get(f"{code}_FEE"))
                if amount <= Decimal("0.00"):
                    continue

                fee_head = FeeHead.objects.get_or_create(
                    name=head_name,
                    defaults={"legacy_column": f"{code}_FEE"},
                )[0]
                FeeStructure.objects.update_or_create(
                    session=session,
                    school_class=school_class,
                    fee_head=fee_head,
                    defaults={"amount": amount},
                )
                imported += 1

        self.stdout.write(self.style.SUCCESS("Legacy fee structure import complete."))
        self.stdout.write(f"rows_seen: {len(rows)}")
        self.stdout.write(f"rows_skipped: {skipped}")
        self.stdout.write(f"structures_imported_or_updated: {imported}")

    def read_csv(self, path):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def normalize_class_name(self, value):
        cleaned = self.clean(value)
        return CLASS_ALIASES.get(cleaned.lower(), cleaned)

    def money(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return Decimal("0.00")
        try:
            return Decimal(cleaned).quantize(Decimal("0.01"))
        except InvalidOperation:
            return Decimal("0.00")

    def to_int(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            return None

    def clean(self, value):
        if value is None:
            return ""
        return str(value).strip()
