import csv
import os
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    AcademicSession,
    FeeHead,
    FeeStructure,
    SchoolClass,
    Student,
    StudentOpeningBalance,
)


ZERO = Decimal("0.00")
REPORT_DIR = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports")

FEE_MAPPING = {
    "ADM_FEE": ("Admission Fee", FeeHead.Frequency.ONE_TIME),
    "DEV_FEE": ("Development Fee", FeeHead.Frequency.ANNUAL),
    "TUT_FEE": ("Tuition Fee", FeeHead.Frequency.MONTHLY),
    "COM_FEE": ("Computer Fee", FeeHead.Frequency.MONTHLY),
    "LIB_FEE": ("Library Fee", FeeHead.Frequency.ANNUAL),
    "CON_FEE": ("Conveyance Fee", FeeHead.Frequency.MONTHLY),
    "SCI_FEE": ("Science Fee", FeeHead.Frequency.MONTHLY),
    "ELE_FEE": ("Electricity Fee", FeeHead.Frequency.ANNUAL),
    "SPO_FEE": ("Sports Fee", FeeHead.Frequency.ANNUAL),
    "GEN_FEE": ("Generator Fee", FeeHead.Frequency.ANNUAL),
    "MED_FEE": ("Medical Fee", FeeHead.Frequency.ANNUAL),
    "EXA_FEE": ("Exam Fee", FeeHead.Frequency.ANNUAL),
    "HOS_FEE": ("Hostel Fee", FeeHead.Frequency.MONTHLY),
    "ANU_FEE": ("Annual Fee", FeeHead.Frequency.ANNUAL),
    "OTH_FEE": ("Other Fee", FeeHead.Frequency.ANNUAL),
    "BULD_FEE": ("Building Fee", FeeHead.Frequency.ANNUAL),
    "HAND_FEE": ("Handicraft Fee", FeeHead.Frequency.ANNUAL),
    "LAB_FEE": ("Lab Fee", FeeHead.Frequency.MONTHLY),
    "NCONS_FEE": ("NCC/Scout Fee", FeeHead.Frequency.ANNUAL),
    "ANUA_FEE": ("Annual Function Fee", FeeHead.Frequency.ANNUAL),
    "MAGI_FEE": ("Magazine Fee", FeeHead.Frequency.ANNUAL),
}

CLASS_NAME_MAP = {
    "XII MATHS": "XII (MATHS)",
    "XII BIO": "XII (BIO)",
    "XII ART": "XII (ART)",
    "XII COM": "XII (COM)",
    "XI MATHS": "XI (MATHS)",
    "XI BIO": "XI (BIO)",
    "XI ART": "XI (ART)",
    "XI COM": "XI (COM)",
}

COPY_STRUCTURES = {}


class Command(BaseCommand):
    help = "Dry-run or import THPSIC fee structures and opening balances from Cfee.csv/FEE.csv."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write fee structures and opening balances.")
        parser.add_argument("--confirm", default="", help="Required as --confirm THPSIC when using --apply.")
        parser.add_argument(
            "--csv-dir",
            default=r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis",
            help="Folder containing Cfee.csv and FEE.csv.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        if apply_changes and options["confirm"] != "THPSIC":
            raise CommandError("Live apply requires --confirm THPSIC.")

        csv_dir = Path(options["csv_dir"])
        cfee_path = csv_dir / "Cfee.csv"
        fee_path = csv_dir / "FEE.csv"
        if not cfee_path.exists():
            raise CommandError(f"Cfee.csv not found: {cfee_path}")
        if not fee_path.exists():
            raise CommandError(f"FEE.csv not found: {fee_path}")

        session = AcademicSession.objects.filter(is_active=True).first()
        if not session:
            raise CommandError("No active AcademicSession found.")

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        fee_columns, cfee_rows = self.read_cfee(cfee_path)
        structures, structure_exceptions, summary_rows = self.build_fee_structures(fee_columns, cfee_rows)
        balance_rows, balance_summary = self.build_opening_balances(fee_path, session)

        self.write_previews(structures, structure_exceptions, summary_rows, balance_rows, balance_summary)

        if apply_changes:
            with transaction.atomic():
                self.apply_fee_structures(session, structures)
                self.apply_opening_balances(session, balance_rows)

        self.print_summary(apply_changes, structures, structure_exceptions, balance_summary)

    def read_cfee(self, path):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fee_columns = [col for col in reader.fieldnames if col.endswith("_FEE") and col != "TOT_FEE"]
            rows = []
            for line_no, row in enumerate(reader, start=2):
                row["_line_no"] = line_no
                row["_class_name"] = self.normalize_class(row.get("CNAME", ""))
                row["_old_app"] = (row.get("OLD_APP", "") or "").strip().upper()
                rows.append(row)
        return fee_columns, rows

    def build_fee_structures(self, fee_columns, rows):
        by_class = defaultdict(list)
        for row in rows:
            by_class[row["_class_name"]].append(row)

        structures = {}
        exceptions = []
        summary_rows = []
        class_names = set(SchoolClass.objects.values_list("name", flat=True))

        for class_name in sorted(by_class, key=self.class_sort_key):
            if class_name not in class_names:
                exceptions.append(self.exception_row("CLASS_NOT_FOUND", class_name, "", "", "", "", "Skipped: class not in new DB"))
                continue

            class_rows = by_class[class_name]
            yes_row = self.choose_row(class_rows, "YES")
            no_row = self.choose_row(class_rows, "NO")
            base_row = yes_row or no_row

            if not base_row:
                continue

            source_note = f"Cfee line {base_row['_line_no']} OLD_APP={base_row['_old_app']}"
            continuing_total = ZERO
            new_only_total = ZERO

            if not yes_row and no_row:
                exceptions.append(self.exception_row("NO_YES_ROW", class_name, "NO", "", "", no_row["_line_no"], "Used OLD_APP=NO as fallback base"))

            for col in fee_columns:
                if col == "ADM_FEE":
                    continue
                amount = self.decimal(base_row.get(col))
                if amount <= ZERO:
                    continue
                structures[(class_name, col)] = {
                    "class": class_name,
                    "cohort": "Both/Regular",
                    "head_name": FEE_MAPPING[col][0],
                    "legacy_column": col,
                    "amount": amount,
                    "frequency": FEE_MAPPING[col][1],
                    "source": source_note,
                    "note": "Base from OLD_APP=YES continuing row" if yes_row else "Fallback from OLD_APP=NO row",
                }
                continuing_total += amount

            if no_row and self.is_suspicious_direct_admission_row(no_row):
                for col in fee_columns:
                    amount = self.decimal(no_row.get(col))
                    if amount > ZERO:
                        exceptions.append(self.exception_row("SUSPICIOUS_NO_ROW", class_name, "NO", col, amount, no_row["_line_no"], "Skipped; manual direct-admission package decision needed"))
            elif no_row:
                admission_amount = self.decimal(no_row.get("ADM_FEE"))
                if admission_amount > ZERO:
                    structures[(class_name, "ADM_FEE")] = {
                        "class": class_name,
                        "cohort": "New admission only",
                        "head_name": FEE_MAPPING["ADM_FEE"][0],
                        "legacy_column": "ADM_FEE",
                        "amount": admission_amount,
                        "frequency": FEE_MAPPING["ADM_FEE"][1],
                        "source": f"Cfee line {no_row['_line_no']} OLD_APP=NO",
                        "note": "One-time admission fee; non-ADM columns from OLD_APP=NO ignored",
                    }
                    new_only_total += admission_amount

            summary_rows.append({
                "class": class_name,
                "continuing_total": continuing_total,
                "new_admission_fee": new_only_total,
                "new_student_total": continuing_total + new_only_total,
                "source": source_note,
                "note": "",
            })

        for target_class, source_class in COPY_STRUCTURES.items():
            if target_class in class_names and not any(key[0] == target_class for key in structures):
                copied_total = ZERO
                for (class_name, col), data in list(structures.items()):
                    if class_name != source_class or col == "ADM_FEE":
                        continue
                    copied = dict(data)
                    copied["class"] = target_class
                    copied["source"] = f"Copied from {source_class}"
                    copied["note"] = f"No Cfee row found for {target_class}; copied {source_class} structure for dry-run review"
                    structures[(target_class, col)] = copied
                    copied_total += copied["amount"]
                source_adm = structures.get((source_class, "ADM_FEE"))
                if source_adm:
                    copied = dict(source_adm)
                    copied["class"] = target_class
                    copied["source"] = f"Copied from {source_class}"
                    copied["note"] = f"No Cfee row found for {target_class}; copied admission fee from {source_class}"
                    structures[(target_class, "ADM_FEE")] = copied
                exceptions.append(self.exception_row("MISSING_COM_STRUCTURE", target_class, "", "", "", "", f"Copied {source_class}; verify manually"))
                summary_rows.append({
                    "class": target_class,
                    "continuing_total": copied_total,
                    "new_admission_fee": source_adm["amount"] if source_adm else ZERO,
                    "new_student_total": copied_total + (source_adm["amount"] if source_adm else ZERO),
                    "source": f"Copied from {source_class}",
                    "note": "Manual approval required",
                })

        return list(structures.values()), exceptions, summary_rows

    def build_opening_balances(self, fee_path, session):
        active_students = Student.objects.filter(is_active=True, transfer_certificate__isnull=True).select_related("current_class")
        active_sid_map = {str(student.legacy_sid): student for student in active_students if student.legacy_sid}
        rows = []
        missing_students = 0
        total_amount = ZERO

        with fee_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for source_row, row in enumerate(reader, start=2):
                sid = (row.get("SID") or "").strip()
                curr_amt = self.decimal(row.get("CURR_AMT"))
                prv_amt = self.decimal(row.get("PRV_AMT"))
                total_due = curr_amt + prv_amt
                if total_due <= ZERO:
                    continue

                student = active_sid_map.get(sid)
                if not student:
                    missing_students += 1
                    continue

                rows.append({
                    "sid": sid,
                    "student": student,
                    "student_name": student.full_name,
                    "class": student.current_class.name if student.current_class else "",
                    "curr_amt": curr_amt,
                    "prv_amt": prv_amt,
                    "amount": total_due,
                    "source_row": source_row,
                    "source_reference": f"FEE.csv line {source_row} SID {sid}",
                })
                total_amount += total_due

        return rows, {"count": len(rows), "total": total_amount, "missing_students": missing_students}

    def write_previews(self, structures, exceptions, summary_rows, balance_rows, balance_summary):
        struct_path = REPORT_DIR / "FEE_STRUCTURE_PREVIEW.csv"
        summary_path = REPORT_DIR / "FEE_STRUCTURE_CLASS_SUMMARY.csv"
        exception_path = REPORT_DIR / "FEE_STRUCTURE_EXCEPTIONS.csv"
        balance_path = REPORT_DIR / "FEE_IMPORT_PREVIEW.csv"
        summary_md_path = REPORT_DIR / "FEE_IMPORT_DRYRUN_SUMMARY.md"

        with struct_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Class", "Cohort", "Fee Head", "Legacy Column", "Amount", "Frequency", "Source", "Note"])
            for row in sorted(structures, key=lambda item: (self.class_sort_key(item["class"]), item["cohort"], item["head_name"])):
                writer.writerow([row["class"], row["cohort"], row["head_name"], row["legacy_column"], row["amount"], row["frequency"], row["source"], row["note"]])

        with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Class", "Continuing Total", "New Admission Fee", "New Student Total", "Source", "Note"])
            for row in sorted(summary_rows, key=lambda item: self.class_sort_key(item["class"])):
                writer.writerow([row["class"], row["continuing_total"], row["new_admission_fee"], row["new_student_total"], row["source"], row["note"]])

        with exception_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Issue", "Class", "OLD_APP", "Legacy Column", "Amount", "Source Row", "Decision"])
            writer.writerows(exceptions)

        with balance_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["SID", "Student Name", "Class", "CURR_AMT", "PRV_AMT", "Opening Balance", "Source"])
            for row in balance_rows:
                writer.writerow([row["sid"], row["student_name"], row["class"], row["curr_amt"], row["prv_amt"], row["amount"], row["source_reference"]])

        total_structures = len(structures)
        summary_md_path.write_text(
            "\n".join([
                "# THPSIC Fee Import Dry-Run Summary",
                "",
                f"- Fee structure rows: {total_structures}",
                f"- Fee structure exceptions: {len(exceptions)}",
                f"- Opening balance students: {balance_summary['count']}",
                f"- Opening balance total: Rs {balance_summary['total']}",
                f"- Students with dues but not active in new DB: {balance_summary['missing_students']}",
                "",
                "Generated files:",
                f"- {struct_path}",
                f"- {summary_path}",
                f"- {exception_path}",
                f"- {balance_path}",
            ]),
            encoding="utf-8",
        )

    def apply_fee_structures(self, session, structures):
        for row in structures:
            school_class = SchoolClass.objects.get(name=row["class"])
            head = self.get_or_update_fee_head(row)
            FeeStructure.objects.update_or_create(
                session=session,
                school_class=school_class,
                fee_head=head,
                defaults={
                    "amount": row["amount"],
                    "is_active": True,
                    "source": FeeStructure.Source.LEGACY,
                    "source_reference": row["source"][:120],
                },
            )

    def apply_opening_balances(self, session, balance_rows):
        as_of_date = session.starts_on
        for row in balance_rows:
            StudentOpeningBalance.objects.update_or_create(
                session=session,
                student=row["student"],
                defaults={
                    "amount": row["amount"],
                    "as_of_date": as_of_date,
                    "source_reference": row["source_reference"][:120],
                    "note": f"Imported legacy dues: CURR_AMT={row['curr_amt']}, PRV_AMT={row['prv_amt']}",
                },
            )

    def get_or_update_fee_head(self, row):
        defaults = {
            "legacy_column": row["legacy_column"],
            "frequency": row["frequency"],
            "is_transport": False,
        }
        if row["legacy_column"] == "ADM_FEE":
            defaults.update({
                "applies_to": FeeHead.AppliesTo.NEW,
                "new_student_charge_rule": FeeHead.ChargeRule.ADMISSION_MONTH,
                "old_student_charge_rule": FeeHead.ChargeRule.NOT_APPLICABLE,
            })
        head, _created = FeeHead.objects.update_or_create(name=row["head_name"], defaults=defaults)
        return head

    def print_summary(self, apply_changes, structures, exceptions, balance_summary):
        mode = "APPLY" if apply_changes else "DRY RUN"
        self.stdout.write(self.style.SUCCESS(f"{mode} SUMMARY"))
        self.stdout.write(f"Fee structure rows: {len(structures)}")
        self.stdout.write(f"Fee structure exceptions: {len(exceptions)}")
        self.stdout.write(f"Opening balances: {balance_summary['count']} students / Rs {balance_summary['total']}")
        self.stdout.write(f"Students with dues but not active in new DB: {balance_summary['missing_students']}")
        self.stdout.write(f"Reports written in: {REPORT_DIR}")
        if not apply_changes:
            self.stdout.write("Live DB was not changed. Use --apply --confirm THPSIC only after review.")

    def choose_row(self, rows, old_app):
        matches = [row for row in rows if row["_old_app"] == old_app]
        if not matches:
            return None
        return sorted(matches, key=lambda row: row["_line_no"])[-1]

    def normalize_class(self, value):
        name = (value or "").strip().upper()
        return CLASS_NAME_MAP.get(name, name)

    def decimal(self, value):
        try:
            return Decimal(str(value or "0").strip() or "0").quantize(Decimal("0.01"))
        except (InvalidOperation, AttributeError):
            return ZERO

    def is_suspicious_direct_admission_row(self, row):
        class_name = row["_class_name"]
        if row["_old_app"] != "NO":
            return False
        if class_name != "X" and not class_name.startswith("XII"):
            return False
        return self.decimal(row.get("TUT_FEE")) >= Decimal("10000.00")

    def exception_row(self, issue, class_name, old_app, col, amount, source_row, decision):
        return [issue, class_name, old_app, col, amount, source_row, decision]

    def class_sort_key(self, class_name):
        order = {
            "VI": 6,
            "VII": 7,
            "VIII": 8,
            "IX": 9,
            "X": 10,
            "XI (ART)": 11.1,
            "XI (BIO)": 11.2,
            "XI (COM)": 11.3,
            "XI (MATHS)": 11.4,
            "XII (ART)": 12.1,
            "XII (BIO)": 12.2,
            "XII (COM)": 12.3,
            "XII (MATHS)": 12.4,
        }
        return order.get(class_name, 99)
