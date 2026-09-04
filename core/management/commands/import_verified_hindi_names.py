import csv
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from core.models import Student


class Command(BaseCommand):
    help = "Safely import verified Hindi names from verified Excel/CSV into live database."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to verified .csv or .xlsx file.")
        parser.add_argument("--apply", action="store_true", help="Apply changes to database after dry-run review.")
        parser.add_argument("--confirm", help="Must be THPSIC when --apply is used.")
        parser.add_argument(
            "--backup-out-dir",
            default=r"E:\THPSIC-INTER-COLLEGE\04-backups\daily_backups",
            help="Backup directory used before apply.",
        )

    def handle(self, *args, **options):
        if options["apply"] and options.get("confirm") != "THPSIC":
            raise CommandError("Apply blocked. Use --apply --confirm THPSIC after reviewing dry-run.")

        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        self.stdout.write(self.style.MIGRATE_HEADING("=== VERIFIED HINDI NAMES IMPORT ==="))
        self.stdout.write(f"Mode: {'APPLY LIVE' if options['apply'] else 'DRY-RUN ONLY'}")
        self.stdout.write(f"Source: {file_path}")

        rows = self._read_file(file_path)
        if not rows:
            raise CommandError(f"No valid rows found in {file_path}")

        if options["apply"]:
            call_command("safe_sqlite_backup", out_dir=options["backup_out_dir"], label="before-hindi-names-import")

        students_by_sid = {
            int(s.legacy_sid): s for s in Student.objects.filter(legacy_sid__isnull=False)
        }
        students_by_adm = {
            str(s.admission_no).strip(): s for s in Student.objects.all() if s.admission_no
        }

        updated_count = 0
        unchanged_count = 0
        skipped_count = 0
        preview = []

        for row in rows:
            sid_raw = str(row.get("legacy_sid", "")).strip()
            adm_raw = str(row.get("admission_no", "")).strip()

            student = None
            if sid_raw.isdigit() and int(sid_raw) in students_by_sid:
                student = students_by_sid[int(sid_raw)]
            elif adm_raw and adm_raw in students_by_adm:
                student = students_by_adm[adm_raw]

            if not student:
                skipped_count += 1
                preview.append(
                    {
                        "status": "NOT_FOUND",
                        "sid": sid_raw,
                        "admno": adm_raw,
                        "name_en": row.get("student_name_english", ""),
                        "reason": "Student not found in DB",
                    }
                )
                continue

            v_student = str(row.get("verified_student_hindi", "")).strip()
            v_father = str(row.get("verified_father_hindi", "")).strip()
            v_mother = str(row.get("verified_mother_hindi", "")).strip()

            changed = False
            updates = {}
            if v_student and student.full_name_hindi != v_student:
                updates["full_name_hindi"] = v_student
                changed = True
            if v_father and student.father_name_hindi != v_father:
                updates["father_name_hindi"] = v_father
                changed = True
            if v_mother and student.mother_name_hindi != v_mother:
                updates["mother_name_hindi"] = v_mother
                changed = True

            if changed:
                updated_count += 1
                preview.append(
                    {
                        "status": "UPDATE",
                        "sid": student.legacy_sid,
                        "admno": student.admission_no,
                        "name_en": student.full_name,
                        "student_hindi": v_student or student.full_name_hindi,
                        "father_hindi": v_father or student.father_name_hindi,
                        "mother_hindi": v_mother or student.mother_name_hindi,
                    }
                )
                if options["apply"]:
                    for field, val in updates.items():
                        setattr(student, field, val)
                    student.save(update_fields=list(updates.keys()))
            else:
                unchanged_count += 1

        self.stdout.write(self.style.SUCCESS(f"Import Summary:"))
        self.stdout.write(f"- Total rows processed: {len(rows)}")
        self.stdout.write(f"- To update / Updated: {updated_count}")
        self.stdout.write(f"- Unchanged (already matching/blank): {unchanged_count}")
        self.stdout.write(f"- Skipped (not found): {skipped_count}")

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Dry-run only. Live DB not modified."))

    def _read_file(self, path):
        suffix = path.suffix.lower()
        if suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
                return list(csv.DictReader(handle))
        elif suffix in (".xlsx", ".xlsm"):
            import openpyxl

            wb = openpyxl.load_workbook(path, data_only=True)
            sheet = wb.active
            headers = [str(cell.value or "").strip() for cell in sheet[1]]
            rows = []
            for row_cells in sheet.iter_rows(min_row=2, values_only=True):
                row_dict = {
                    headers[idx]: (str(val).strip() if val is not None else "")
                    for idx, val in enumerate(row_cells)
                    if idx < len(headers) and headers[idx]
                }
                if any(row_dict.values()):
                    rows.append(row_dict)
            return rows
        else:
            raise CommandError(f"Unsupported file format: {suffix}. Must be .csv or .xlsx")
