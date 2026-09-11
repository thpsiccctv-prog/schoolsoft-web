"""
Django Management Command: ingest_award_sheet_scans
Processes scanned award sheet data, performs mathematical validation,
generates dry-run preview CSVs, and safely commits marks to ExamMark.
"""

import csv
from pathlib import Path
import sys

from django.core.management.base import BaseCommand, CommandError
from core.models import ExamTest, SchoolClass, Section, Student
from core.award_sheet_processor import (
    parse_sheet_token, get_expected_page_roster, validate_and_reconcile_row,
    export_preview_csv, commit_award_sheet_marks
)


class Command(BaseCommand):
    help = "Ingests teacher award sheet marks with strict arithmetic validation and audit trail."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=str,
            required=True,
            help="Path to CSV/data file containing extracted sheet marks or scan manifest.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview and validate marks without committing to the database.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Commit verified marks into the database (ExamMark).",
        )
        parser.add_argument(
            "--out-dir",
            default=r"E:\THPSIC-INTER-COLLEGE\05-reports\quarterly-exam-2026\ingestion-audits",
            help="Output folder for preview CSVs and audit manifests.",
        )

    def handle(self, *args, **options):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

        source_path = Path(options["source"])
        dry_run = not options.get("apply")
        out_dir = Path(options.get("out_dir"))
        out_dir.mkdir(parents=True, exist_ok=True)

        if not source_path.exists():
            raise CommandError(f"Source file not found at: {source_path}")

        mode_str = "DRY-RUN (PREVIEW ONLY)" if dry_run else "LIVE COMMIT (DATABASE WRITE)"
        self.stdout.write(self.style.WARNING(f"\n=== AWARD SHEET INGESTION MODE: {mode_str} ===\n"))

        # Check if source is a CSV file
        if source_path.suffix.lower() == ".csv":
            self.process_csv_source(source_path, dry_run, out_dir)
        else:
            raise CommandError(f"Unsupported file format '{source_path.suffix}'. Please provide an extracted CSV or manifest.")

    def process_csv_source(self, csv_path, dry_run, out_dir):
        """
        Parses a CSV file with columns:
        SHEET_ID, ROLL_NO, ADM_NO/SID, THEORY, PRACTICAL, TOTAL, ABSENT, REMARKS
        """
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            self.stdout.write(self.style.WARNING("Source CSV is empty."))
            return

        # Group rows by sheet_id or test_id
        grouped = {}
        for r in rows:
            token = r.get("SHEET_ID") or r.get("SHEET_TOKEN") or csv_path.stem
            grouped.setdefault(token, []).append(r)

        total_processed = 0
        total_created = 0
        total_updated = 0
        total_mismatches = 0

        for token, token_rows in grouped.items():
            parsed_token = parse_sheet_token(token)
            if parsed_token:
                test_id = parsed_token["test_id"]
                test = ExamTest.objects.select_related("term", "school_class", "subject").filter(pk=test_id).first()
            else:
                # Try finding test from first row
                test_id = token_rows[0].get("TEST_ID")
                test = ExamTest.objects.select_related("term", "school_class", "subject").filter(pk=test_id).first() if test_id else None

            if not test:
                self.stdout.write(self.style.ERROR(f"Could not identify ExamTest for sheet token: {token}"))
                continue

            self.stdout.write(self.style.SUCCESS(f"Processing Sheet: {token} -> {test.school_class.name} / {test.subject.name}"))

            verified_rows = []
            for r in token_rows:
                adm_or_sid = str(r.get("ADM_NO") or r.get("SID") or r.get("ADMISSION_NO") or "").strip()
                roll_val = str(r.get("ROLL_NO") or "").strip()

                student = None
                if adm_or_sid:
                    # Match by admission_no or legacy_sid within current class
                    student = Student.objects.filter(
                        current_class=test.school_class,
                        is_active=True
                    ).filter(admission_no=adm_or_sid).first()
                    if not student and adm_or_sid.isdigit():
                        student = Student.objects.filter(
                            current_class=test.school_class,
                            is_active=True,
                            legacy_sid=int(adm_or_sid)
                        ).first()

                if not student and roll_val and roll_val.isdigit():
                    student = Student.objects.filter(
                        current_class=test.school_class,
                        is_active=True,
                        roll_no=int(roll_val)
                    ).first()

                if not student:
                    self.stdout.write(self.style.WARNING(f"  Skipping unmatched student row: Adm={adm_or_sid}, Roll={roll_val}"))
                    continue

                raw_th = r.get("THEORY") or r.get("RAW_THEORY") or ""
                raw_pr = r.get("PRACTICAL") or r.get("RAW_PRACTICAL") or ""
                raw_tot = r.get("TOTAL") or r.get("RAW_TOTAL") or ""
                ab_val = str(r.get("ABSENT") or r.get("IS_ABSENT") or "").strip().upper()
                is_ab = ab_val in ("Y", "YES", "TRUE", "1", "AB", "ABSENT")
                remarks = r.get("REMARKS") or ""

                v_row = validate_and_reconcile_row(student, test, raw_th, raw_pr, raw_tot, is_absent=is_ab, remarks=remarks)
                verified_rows.append(v_row)

                if v_row["status"] == "ARITHMETIC_MISMATCH":
                    total_mismatches += 1
                    self.stdout.write(self.style.ERROR(
                        f"  [MISMATCH] {student.full_name} (Roll {student.roll_no or student.legacy_sid}): "
                        f"Th({raw_th}) + Pr({raw_pr}) != Total({raw_tot})"
                    ))
                elif v_row["status"] == "EXCEEDS_MAX":
                    self.stdout.write(self.style.ERROR(
                        f"  [EXCEEDS MAX] {student.full_name}: {'; '.join(v_row['flags'])}"
                    ))

            # Export preview CSV
            preview_csv = export_preview_csv(token, verified_rows, out_dir)
            self.stdout.write(f"  Audit Preview CSV saved: {preview_csv.name}")

            # Commit or dry-run
            summary = commit_award_sheet_marks(test, verified_rows, dry_run=dry_run)
            total_processed += summary["total_rows"]
            total_created += summary["created_count"]
            total_updated += summary["updated_count"]

            self.stdout.write(
                f"  Summary: Total={summary['total_rows']}, Valid={summary['valid_rows']}, "
                f"Absent={summary['absent_rows']}, Created={summary['created_count']}, "
                f"Updated={summary['updated_count']}, Skipped={summary['skipped_count']}\n"
            )

        self.stdout.write(self.style.SUCCESS(
            f"\n=== INGESTION SUMMARY ===\n"
            f"Mode: {'DRY RUN' if dry_run else 'COMMITTED'}\n"
            f"Total Processed: {total_processed}\n"
            f"Created Records: {total_created}\n"
            f"Updated Records: {total_updated}\n"
            f"Arithmetic Mismatches Flagged: {total_mismatches}\n"
            f"Audit Directory: {out_dir}\n"
        ))
