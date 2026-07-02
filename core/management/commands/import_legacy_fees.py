import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    AcademicSession,
    FeeHead,
    FeeReceipt,
    FeeReceiptLine,
    LegacyImportBatch,
    SchoolClass,
    Section,
    Student,
)


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
    "FIN": "Fine",
    "DUE": "Previous Due",
    "LES": "Late/Less Fee",
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
    help = "Import legacy StuFee CSV receipts into FeeReceipt and FeeReceiptLine."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=r"D:\english medium\migration_audit\exports\StuFee.csv",
            help="Path to exported StuFee.csv.",
        )
        parser.add_argument(
            "--session",
            default="2018-19",
            help="Academic session name for imported legacy receipts.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate without writing to the database.",
        )

    def handle(self, *args, **options):
        source = Path(options["source"])
        dry_run = options["dry_run"]

        if not source.exists():
            raise CommandError(f"StuFee CSV not found: {source}")

        rows = self.read_csv(source)
        summary = {
            "receipts_seen": len(rows),
            "receipts_imported": 0,
            "receipts_skipped": 0,
            "missing_students": 0,
            "placeholder_students_created": 0,
            "lines_imported": 0,
            "sum_paid": Decimal("0.00"),
            "sum_net": Decimal("0.00"),
            "sum_due": Decimal("0.00"),
        }

        with transaction.atomic():
            session = self.get_session(options["session"], dry_run)
            fee_heads = self.get_fee_heads(dry_run)
            self.import_receipts(rows, session, fee_heads, dry_run, summary)

            if dry_run:
                transaction.set_rollback(True)

        if not dry_run:
            LegacyImportBatch.objects.create(
                source_database=str(source),
                source_table="StuFee",
                records_seen=summary["receipts_seen"],
                records_imported=summary["receipts_imported"],
                notes=(
                    f"lines imported: {summary['lines_imported']}; "
                    f"missing students: {summary['missing_students']}; "
                    f"sum paid: {summary['sum_paid']}; "
                    f"sum net: {summary['sum_net']}; "
                    f"sum due: {summary['sum_due']}"
                ),
            )

        mode = "DRY RUN" if dry_run else "IMPORT"
        self.stdout.write(self.style.SUCCESS(f"{mode} complete."))
        for key, value in summary.items():
            self.stdout.write(f"{key}: {value}")

    def read_csv(self, path):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def get_session(self, session_name, dry_run):
        if dry_run:
            return None

        return AcademicSession.objects.get_or_create(
            name=session_name,
            defaults={
                "starts_on": date(2018, 4, 1),
                "ends_on": date(2019, 3, 31),
                "is_active": False,
            },
        )[0]

    def get_fee_heads(self, dry_run):
        heads = {}
        for legacy_code, name in FEE_HEADS.items():
            if dry_run:
                heads[legacy_code] = None
                continue

            head, _ = FeeHead.objects.get_or_create(
                name=name,
                defaults={
                    "legacy_column": f"{legacy_code}_FEE",
                    "frequency": FeeHead.Frequency.MONTHLY,
                    "is_transport": legacy_code == "CON",
                },
            )
            heads[legacy_code] = head

        return heads

    def import_receipts(self, rows, session, fee_heads, dry_run, summary):
        for row in rows:
            legacy_receipt_no = self.to_int(row.get("rcpno"))
            legacy_sid = self.to_int(row.get("sid"))

            if not legacy_receipt_no or not legacy_sid:
                summary["receipts_skipped"] += 1
                continue

            student = None
            if dry_run:
                if not Student.objects.filter(legacy_sid=legacy_sid).exists():
                    summary["missing_students"] += 1
                    summary["placeholder_students_created"] += 1
            else:
                student = Student.objects.filter(legacy_sid=legacy_sid).first()
                if student is None:
                    student = self.create_placeholder_student(row, legacy_sid)
                    summary["missing_students"] += 1
                    summary["placeholder_students_created"] += 1

            receipt_no = f"SF-{legacy_receipt_no}"
            receipt_date = self.parse_date(row.get("v_date")) or date(2018, 4, 1)
            concession_total = self.money(row.get("CON_TOT"))
            paid = self.money(row.get("paid"))
            fee_total = self.money(row.get("FEE_TOT"))
            net_total = self.money(row.get("NET_TOT"))
            due_amount = self.money(row.get("due"))

            line_values = self.extract_line_values(row)
            line_total = sum(line_values.values(), Decimal("0.00"))

            summary["sum_paid"] += paid
            summary["sum_net"] += net_total
            summary["sum_due"] += due_amount

            if dry_run:
                summary["receipts_imported"] += 1
                summary["lines_imported"] += len(line_values)
                continue

            receipt, _ = FeeReceipt.objects.update_or_create(
                receipt_no=receipt_no,
                defaults={
                    "legacy_receipt_no": legacy_receipt_no,
                    "student": student,
                    "session": session,
                    "receipt_date": receipt_date,
                    "from_month": self.clean(row.get("FRMONTH")),
                    "to_month": self.clean(row.get("TOMONTH")),
                    "payment_mode": self.map_payment_mode(row.get("MODE")),
                    "concession_amount": concession_total,
                    "late_fee_amount": Decimal("0.00"),
                    "received_amount": paid,
                    "legacy_fee_total": fee_total or line_total,
                    "legacy_net_total": net_total,
                    "legacy_due_amount": due_amount,
                    "remarks": self.build_remarks(row),
                },
            )

            receipt.lines.all().delete()
            for legacy_code, amount in line_values.items():
                FeeReceiptLine.objects.create(
                    receipt=receipt,
                    fee_head=fee_heads[legacy_code],
                    amount=amount,
                )
                summary["lines_imported"] += 1

            summary["receipts_imported"] += 1

    def extract_line_values(self, row):
        values = {}
        for legacy_code in FEE_HEADS:
            amount = self.money(row.get(f"{legacy_code}_FEE"))
            if amount != Decimal("0.00"):
                values[legacy_code] = amount
        return values

    def create_placeholder_student(self, row, legacy_sid):
        class_name = self.normalize_class_name(row.get("sclass"))
        section_name = self.clean(row.get("section")) or "A"
        school_class = None
        section = None

        if class_name:
            school_class, _ = SchoolClass.objects.get_or_create(
                name=class_name,
                defaults={"display_order": 0},
            )
            section, _ = Section.objects.get_or_create(
                school_class=school_class,
                name=section_name,
            )

        return Student.objects.create(
            legacy_sid=legacy_sid,
            admission_no=self.clean(row.get("regno")),
            full_name=self.clean(row.get("sname")) or f"Legacy Student {legacy_sid}",
            father_name=self.clean(row.get("fname")),
            mobile_primary=self.clean(row.get("MOBNO")),
            current_class=school_class,
            current_section=section,
            is_active=True,
        )

    def normalize_class_name(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return ""

        return CLASS_ALIASES.get(cleaned.lower(), cleaned)

    def build_remarks(self, row):
        parts = [
            self.clean(row.get("FEE_STATUS")),
            self.clean(row.get("MONTH")),
            self.clean(row.get("REMARK")),
        ]
        return " | ".join(part for part in parts if part)[:255]

    def map_payment_mode(self, value):
        cleaned = self.clean(value).lower()
        if cleaned == "cash":
            return FeeReceipt.PaymentMode.CASH
        if "cheque" in cleaned or "chq" in cleaned:
            return FeeReceipt.PaymentMode.CHEQUE
        if "card" in cleaned:
            return FeeReceipt.PaymentMode.CARD
        if "online" in cleaned or "upi" in cleaned or "bank" in cleaned:
            return FeeReceipt.PaymentMode.ONLINE
        return FeeReceipt.PaymentMode.OTHER

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
