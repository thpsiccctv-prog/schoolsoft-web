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
    help = "Import legacy StuFee CSV receipts for all years into FeeReceipt and FeeReceiptLine."

    def add_arguments(self, parser):
        parser.add_argument(
            "--exports-dir",
            default=r"D:\english medium\migration_audit\yearly_exports",
            help="Path to directory containing yearly export folders.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate without writing to the database.",
        )
        parser.add_argument(
            "--report-dir",
            default=r"D:\english medium\migration_audit\yearly_import_reports",
            help="Directory where detailed dry-run reports are written.",
        )

    def handle(self, *args, **options):
        exports_dir = Path(options["exports_dir"])
        dry_run = options["dry_run"]

        if not exports_dir.exists():
            raise CommandError(f"Exports directory not found: {exports_dir}")

        sessions = sorted([d.name for d in exports_dir.iterdir() if d.is_dir()])
        if not sessions:
            raise CommandError(f"No yearly session folders found in {exports_dir}")

        total_summary = {
            "receipts_seen": 0,
            "receipts_imported": 0,
            "receipts_skipped": 0,
            "missing_students": 0,
            "missing_students_unique": 0,
            "placeholder_students_created": 0,
            "placeholder_students_unique": 0,
            "lines_imported": 0,
            "sum_paid": Decimal("0.00"),
            "sum_net": Decimal("0.00"),
            "sum_due": Decimal("0.00"),
            "duplicates_found": 0,
            "sid_name_collisions": 0,
        }
        audit = {
            "missing_sids": set(),
            "sid_names": {},
            "receipt_collisions": [],
            "session_stats": {},
        }

        with transaction.atomic():
            fee_heads = self.get_fee_heads(dry_run)
            
            for session_name in sessions:
                session_dir = exports_dir / session_name
                stufee_csv = session_dir / "StuFee.csv"
                
                if not stufee_csv.exists():
                    self.stdout.write(self.style.WARNING(f"Skipping {session_name}: StuFee.csv not found."))
                    continue
                
                self.stdout.write(f"Processing session {session_name}...")
                rows = self.read_csv(stufee_csv)
                session_obj = self.get_session(session_name, dry_run)
                
                self.import_receipts(rows, session_obj, session_name, fee_heads, dry_run, total_summary, audit)

            if dry_run:
                transaction.set_rollback(True)

        if not dry_run:
            LegacyImportBatch.objects.create(
                source_database=str(exports_dir),
                source_table="StuFee (All Years)",
                records_seen=total_summary["receipts_seen"],
                records_imported=total_summary["receipts_imported"],
                notes=(
                    f"lines imported: {total_summary['lines_imported']}; "
                    f"missing students: {total_summary['missing_students']}; "
                    f"sum paid: {total_summary['sum_paid']}; "
                    f"sum net: {total_summary['sum_net']}; "
                    f"sum due: {total_summary['sum_due']}; "
                    f"duplicates found: {total_summary['duplicates_found']}"
                ),
            )

        mode = "DRY RUN" if dry_run else "IMPORT"
        total_summary["missing_students_unique"] = len(audit["missing_sids"])
        total_summary["placeholder_students_unique"] = len(audit["missing_sids"])
        sid_collisions = {
            sid: names
            for sid, names in audit["sid_names"].items()
            if len(names) > 1
        }
        total_summary["sid_name_collisions"] = len(sid_collisions)
        self.stdout.write(self.style.SUCCESS(f"\n{mode} complete."))
        for key, value in total_summary.items():
            self.stdout.write(f"{key}: {value}")
        self.print_session_stats(audit["session_stats"])
        if sid_collisions:
            self.stdout.write(self.style.WARNING("\nSID/name collisions (first 20):"))
            for sid, names in list(sid_collisions.items())[:20]:
                self.stdout.write(f"  SID {sid}: {', '.join(sorted(names))}")
        if audit["receipt_collisions"]:
            self.stdout.write(self.style.WARNING("\nReceipt number collisions (first 20):"))
            for receipt_no in audit["receipt_collisions"][:20]:
                self.stdout.write(f"  {receipt_no}")
        if dry_run:
            self.write_dry_run_reports(Path(options["report_dir"]), audit, sid_collisions)

    def read_csv(self, path):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def get_session(self, session_name, dry_run):
        if dry_run:
            return None
        
        start_year = int(session_name[:4])
        
        return AcademicSession.objects.get_or_create(
            name=session_name,
            defaults={
                "starts_on": date(start_year, 4, 1),
                "ends_on": date(start_year + 1, 3, 31),
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

    def import_receipts(self, rows, session_obj, session_name, fee_heads, dry_run, summary, audit):
        summary["receipts_seen"] += len(rows)
        session_stats = audit["session_stats"].setdefault(
            session_name,
            {
                "receipts": 0,
                "skipped": 0,
                "missing_unique_sids": set(),
                "lines": 0,
                "paid": Decimal("0.00"),
                "net": Decimal("0.00"),
                "due": Decimal("0.00"),
            },
        )
        for row in rows:
            legacy_receipt_no = self.to_int(row.get("rcpno"))
            legacy_sid = self.to_int(row.get("sid"))

            if not legacy_receipt_no or not legacy_sid:
                summary["receipts_skipped"] += 1
                session_stats["skipped"] += 1
                continue

            student = None
            student_name = self.clean(row.get("sname")) or f"Legacy Student {legacy_sid}"
            audit["sid_names"].setdefault(legacy_sid, set()).add(student_name.upper())
            if dry_run:
                if not Student.objects.filter(legacy_sid=legacy_sid).exists():
                    summary["missing_students"] += 1
                    summary["placeholder_students_created"] += 1
                    audit["missing_sids"].add(legacy_sid)
                    session_stats["missing_unique_sids"].add(legacy_sid)
            else:
                student = Student.objects.filter(legacy_sid=legacy_sid).first()
                if student is None:
                    student = self.create_placeholder_student(row, legacy_sid)
                    summary["missing_students"] += 1
                    summary["placeholder_students_created"] += 1
                    audit["missing_sids"].add(legacy_sid)
                    session_stats["missing_unique_sids"].add(legacy_sid)

            # Make receipt_no unique per session
            receipt_no = f"{session_name}/SF-{legacy_receipt_no}"
            
            # Use start of session as default if date parsing fails
            start_year = int(session_name[:4])
            default_date = date(start_year, 4, 1)
            receipt_date = self.parse_date(row.get("v_date")) or default_date
            
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
            session_stats["paid"] += paid
            session_stats["net"] += net_total
            session_stats["due"] += due_amount

            if dry_run:
                if FeeReceipt.objects.filter(receipt_no=receipt_no).exists():
                    summary["duplicates_found"] += 1
                    audit["receipt_collisions"].append(receipt_no)
                summary["receipts_imported"] += 1
                summary["lines_imported"] += len(line_values)
                session_stats["receipts"] += 1
                session_stats["lines"] += len(line_values)
                continue

            receipt, created = FeeReceipt.objects.update_or_create(
                receipt_no=receipt_no,
                defaults={
                    "legacy_receipt_no": legacy_receipt_no,
                    "student": student,
                    "session": session_obj,
                    "receipt_date": receipt_date,
                    "from_month": self.clean(row.get("FRMONTH")),
                    "to_month": self.clean(row.get("TOMONTH")),
                    "payment_mode": self.map_payment_mode(row.get("MODE")),
                    **self.receipt_snapshot_defaults(row),
                    "concession_amount": concession_total,
                    "late_fee_amount": Decimal("0.00"),
                    "received_amount": paid,
                    "legacy_fee_total": fee_total or line_total,
                    "legacy_net_total": net_total,
                    "legacy_due_amount": due_amount,
                    "remarks": self.build_remarks(row),
                },
            )

            if not created:
                summary["duplicates_found"] += 1

            receipt.lines.all().delete()
            for legacy_code, amount in line_values.items():
                FeeReceiptLine.objects.create(
                    receipt=receipt,
                    fee_head=fee_heads[legacy_code],
                    amount=amount,
                )
                summary["lines_imported"] += 1
                session_stats["lines"] += 1

            summary["receipts_imported"] += 1
            session_stats["receipts"] += 1

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
            is_active=False,
        )

    def receipt_snapshot_defaults(self, row):
        return {
            "student_name_snapshot": self.clean(row.get("sname"))[:120],
            "father_name_snapshot": self.clean(row.get("fname"))[:120],
            "class_snapshot": self.normalize_class_name(row.get("sclass"))[:30],
            "section_snapshot": self.clean(row.get("section"))[:10],
        }

    def print_session_stats(self, session_stats):
        self.stdout.write("\nSession-wise statistics:")
        for session_name, stats in sorted(session_stats.items()):
            self.stdout.write(
                f"  {session_name}: receipts={stats['receipts']}, "
                f"lines={stats['lines']}, missing_unique_sids={len(stats['missing_unique_sids'])}, "
                f"paid={stats['paid']}, net={stats['net']}, due={stats['due']}"
            )

    def write_dry_run_reports(self, report_dir, audit, sid_collisions):
        report_dir.mkdir(parents=True, exist_ok=True)

        with (report_dir / "session_stats.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["session", "receipts", "lines", "missing_unique_sids", "paid", "net", "due"])
            for session_name, stats in sorted(audit["session_stats"].items()):
                writer.writerow([
                    session_name,
                    stats["receipts"],
                    stats["lines"],
                    len(stats["missing_unique_sids"]),
                    stats["paid"],
                    stats["net"],
                    stats["due"],
                ])

        with (report_dir / "missing_student_sids.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["legacy_sid"])
            for legacy_sid in sorted(audit["missing_sids"]):
                writer.writerow([legacy_sid])

        with (report_dir / "sid_name_collisions.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["legacy_sid", "names"])
            for legacy_sid, names in sorted(sid_collisions.items()):
                writer.writerow([legacy_sid, " | ".join(sorted(names))])

        with (report_dir / "receipt_no_collisions.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["receipt_no"])
            for receipt_no in audit["receipt_collisions"]:
                writer.writerow([receipt_no])

        self.stdout.write(self.style.SUCCESS(f"\nDetailed dry-run reports written to: {report_dir}"))

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
