import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.commands.import_legacy_students import CLASS_ALIASES
from core.models import AcademicSession, ExamMark, ExamTerm, ExamTest, LegacyImportBatch, SchoolClass, Student, Subject


class Command(BaseCommand):
    help = (
        "Import legacy Testmark2.csv export into normalized Subject/ExamTerm/ExamTest/ExamMark models. "
        "Run migration_audit/export_mdb_tables.ps1 with -Tables @('Testmark2') first to produce Testmark2.csv.\n\n"
        "NOTE: an earlier version of this command used Marks.csv, matching on StudentID == legacy_sid. "
        "That table's StudentID range (5016-6070) turned out to be a completely different ID space from "
        "ADDMISSION.sid (1-1911) - 0% matched. Testmark2.csv uses a plain 'sid' column that matches "
        "ADDMISSION.sid at 100% (verified against all 10,036 rows), so it is used here instead."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-dir",
            default=r"D:\english medium\migration_audit\exports",
            help="Folder containing Testmark2.csv.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate CSV without writing to the database.",
        )

    def handle(self, *args, **options):
        source_dir = Path(options["source_dir"])
        marks_csv = source_dir / "Testmark2.csv"
        dry_run = options["dry_run"]

        if not marks_csv.exists():
            raise CommandError(
                f"Testmark2.csv not found at {marks_csv}. Export it first with:\n"
                "  & 'C:\\Windows\\SysWOW64\\WindowsPowerShell\\v1.0\\powershell.exe' -NoProfile "
                "-ExecutionPolicy Bypass -Command \"& 'D:\\english medium\\migration_audit\\export_mdb_tables.ps1' "
                "-Tables @('Testmark2')\""
            )

        rows = self.read_csv(marks_csv)
        summary = {
            "rows_seen": len(rows),
            "rows_imported": 0,
            "rows_skipped_no_student": 0,
            "rows_skipped_no_class": 0,
            "sessions_created": 0,
            "terms_created": 0,
            "subjects_created": 0,
            "exam_tests_created": 0,
        }

        class_cache = {c.name.upper(): c for c in SchoolClass.objects.all()}
        student_cache = {
            s.legacy_sid: s for s in Student.objects.filter(legacy_sid__isnull=False)
        }

        with transaction.atomic():
            for row in rows:
                self.import_row(row, class_cache, student_cache, dry_run, summary)

            if dry_run:
                transaction.set_rollback(True)

        if not dry_run:
            LegacyImportBatch.objects.create(
                source_database="SCHOOL7.mdb CSV export",
                source_table="Testmark2",
                records_seen=summary["rows_seen"],
                records_imported=summary["rows_imported"],
                notes=(
                    f"Skipped (no student match): {summary['rows_skipped_no_student']}; "
                    f"skipped (no class match): {summary['rows_skipped_no_class']}"
                ),
            )

        mode = "DRY RUN" if dry_run else "IMPORT"
        self.stdout.write(self.style.SUCCESS(f"{mode} complete."))
        for key, value in summary.items():
            self.stdout.write(f"{key}: {value}")

    def import_row(self, row, class_cache, student_cache, dry_run, summary):
        legacy_sid = self.to_int(row.get("sid"))
        student = student_cache.get(legacy_sid) if legacy_sid else None
        if student is None:
            summary["rows_skipped_no_student"] += 1
            return

        class_name = self.clean(row.get("Class"))
        normalized_class_name = self.normalize_class_name(class_name)
        school_class = class_cache.get(class_name.upper()) or class_cache.get(normalized_class_name.upper())
        if school_class is None:
            summary["rows_skipped_no_class"] += 1
            return

        subject_name = self.clean(row.get("Subject"))
        term_name = self.title_case(self.clean(row.get("Test_type")))
        session_name = self.derive_session_name(row.get("V_DATE"))

        if not subject_name or not term_name:
            summary["rows_skipped_no_class"] += 1
            return

        max_marks = self.to_decimal(row.get("M_MAX")) or Decimal("100.00")
        marks_obtained = self.to_decimal(row.get("M_OBT"))
        is_absent = self.clean(row.get("ATT")).upper() == "A" or marks_obtained is None
        grade = self.clean(row.get("GRADE"))

        if dry_run:
            summary["rows_imported"] += 1
            return

        session, session_created = AcademicSession.objects.get_or_create(name=session_name)
        if session_created:
            summary["sessions_created"] += 1

        term, term_created = ExamTerm.objects.get_or_create(session=session, name=term_name)
        if term_created:
            summary["terms_created"] += 1

        subject, subject_created = Subject.objects.get_or_create(name=subject_name)
        if subject_created:
            summary["subjects_created"] += 1

        exam_test, test_created = ExamTest.objects.get_or_create(
            term=term,
            school_class=school_class,
            subject=subject,
            defaults={"max_marks": max_marks},
        )
        if test_created:
            summary["exam_tests_created"] += 1

        ExamMark.objects.update_or_create(
            exam_test=exam_test,
            student=student,
            defaults={
                "marks_obtained": marks_obtained,
                "is_absent": is_absent,
                "grade": grade,
            },
        )
        summary["rows_imported"] += 1

    def derive_session_name(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return "Legacy"
        for date_format in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(cleaned, date_format)
                break
            except ValueError:
                continue
        else:
            return "Legacy"

        # Indian academic year: April to March.
        if parsed.month >= 4:
            start_year = parsed.year
        else:
            start_year = parsed.year - 1
        return f"{start_year}-{(start_year + 1) % 100:02d}"

    def normalize_class_name(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return ""
        return CLASS_ALIASES.get(cleaned.lower(), cleaned)

    def title_case(self, value):
        return " ".join(word.capitalize() for word in value.split())

    def read_csv(self, path):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

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

    def to_decimal(self, value):
        cleaned = self.clean(value)
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
