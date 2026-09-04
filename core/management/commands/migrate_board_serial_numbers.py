import csv
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import Student


DEFAULT_ADDMISSION_CSV = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35-new\ADDMISSION.csv"
DEFAULT_OUT_DIR = r"E:\THPSIC-INTER-COLLEGE\05-reports\board-serial-migration"

CLASS9_SERIAL_RANGES = [
    (151, 200, "SHUBHAM SIR", "C"),
    (201, 300, "SHIVPUJAN SCHOOL", "B"),
    (301, 350, "MADARSHA GAUSIYA", "C"),
    (351, 400, "MD GULAB SCHOOL", "C"),
    (401, 460, "GREEN LAND", "B"),
    (461, 500, "SAMIM SIR CMPS", "C"),
    (501, 550, "NIRAJ GIRI SIR", "B"),
    (551, 600, "CMPS", "B"),
    (601, 650, "CHHOTELAL SIR", "C"),
    (651, 690, "ENGLISH MEDIUM", ""),
    (691, 700, "MANJUR SIR", ""),
]

CLASS11_SERIAL_RANGES = [
    (301, 315, "CHHOTELAL SIR", "C"),
    (316, 320, "GREEN LAND", "C"),
    (321, 335, "MALTI DEVI", "C"),
    (336, 350, "NIRAJ GIRI", ""),
    (351, 400, "SHUBHAM SIR", "C"),
    (401, 450, "IS MUHAMMAD", "C"),
    (451, 500, "SHIVPUJAN SCHOOL", "B"),
    (501, 520, "MD GULAB", "B"),
    (521, 550, "D N SMART", "B"),
]


class Command(BaseCommand):
    help = "Dry-run/apply old SchoolSOFT fedu board SerialNumber into Student.board_sr_number."

    def add_arguments(self, parser):
        parser.add_argument("--admission-csv", default=DEFAULT_ADDMISSION_CSV, help="Old ADDMISSION.csv export path.")
        parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Report output directory.")
        parser.add_argument("--apply", action="store_true", help="Apply clean rows to live DB.")
        parser.add_argument("--confirm", help="Must be THPSIC when --apply is used.")

    def handle(self, *args, **options):
        if options["apply"] and options.get("confirm") != "THPSIC":
            raise CommandError("Apply blocked. Use --apply --confirm THPSIC after dry-run review.")

        source_path = Path(options["admission_csv"])
        if not source_path.exists():
            raise CommandError(f"ADDMISSION CSV not found: {source_path}")

        out_dir = Path(options["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        source_by_sid = self._load_source(source_path)
        students = [
            student
            for student in Student.objects.filter(is_active=True)
            .select_related("current_class", "current_section")
            .order_by("current_class__name", "current_section__name", "legacy_sid", "admission_no")
            if student.current_class
            and (student.current_class.name == "IX" or student.current_class.name.startswith("XI "))
        ]

        rows = []
        proposed_by_group = defaultdict(list)
        for student in students:
            sid = str(student.legacy_sid or "").strip()
            source = source_by_sid.get(sid)
            fedu_raw = (source or {}).get("fedu", "")
            proposed, flag, leading_zero_ok = self._propose(fedu_raw)
            group = "CLASS9" if (student.current_class and student.current_class.name == "IX") else "CLASS11"
            if proposed:
                proposed_by_group[group].append(proposed)
            range_bucket, range_school, range_section, range_flag = self._range_info(
                group,
                proposed,
                student.current_section.name if student.current_section else "",
            )
            rows.append(
                {
                    "action": "",
                    "legacy_sid": sid,
                    "admission_no": student.admission_no or "",
                    "student_name": student.full_name or "",
                    "father_name": student.father_name or "",
                    "class": student.current_class.name if student.current_class else "",
                    "section": student.current_section.name if student.current_section else "",
                    "fedu_raw": fedu_raw,
                    "board_registration_no_current": student.board_sr_number or "",
                    "board_registration_no_proposed": proposed,
                    "leading_zero_ok": leading_zero_ok,
                    "fedu_type_flag": flag,
                    "duplicate_flag": "",
                    "range_bucket": range_bucket,
                    "range_school_expected": range_school,
                    "board_registration_section_expected": range_section,
                    "range_audit_flag": range_flag,
                    "source_status": "FOUND" if source else "MISSING_SOURCE_ROW",
                }
            )

        duplicate_values = {
            group: {value for value, count in Counter(values).items() if count > 1}
            for group, values in proposed_by_group.items()
        }

        apply_count = skip_count = review_count = 0
        for row in rows:
            group = "CLASS9" if row["class"] == "IX" else "CLASS11"
            if row["board_registration_no_proposed"] in duplicate_values[group]:
                row["duplicate_flag"] = f"DUPLICATE_WITHIN_{group}"
            clean = (
                row["source_status"] == "FOUND"
                and row["fedu_type_flag"] == "NUMERIC_OK"
                and not row["duplicate_flag"]
                and bool(row["board_registration_no_proposed"])
            )
            if clean:
                if row["board_registration_no_current"] == row["board_registration_no_proposed"]:
                    row["action"] = "UNCHANGED"
                    skip_count += 1
                else:
                    row["action"] = "UPDATE"
                    apply_count += 1
            else:
                row["action"] = "REVIEW_SKIP"
                review_count += 1

        if options["apply"]:
            source_students = {str(s.legacy_sid or "").strip(): s for s in students}
            for row in rows:
                if row["action"] != "UPDATE":
                    continue
                student = source_students[row["legacy_sid"]]
                student.board_sr_number = row["board_registration_no_proposed"]
                student.save(update_fields=["board_sr_number"])

        report_path = out_dir / "BOARD_SERIAL_NUMBER_MIGRATION_PREVIEW.csv"
        self._write_csv(report_path, rows)
        self._write_summary(out_dir / "BOARD_SERIAL_NUMBER_MIGRATION_SUMMARY.md", rows, options["apply"])

        self.stdout.write(self.style.SUCCESS("Board serial migration report generated."))
        self.stdout.write(f"Mode: {'APPLY LIVE' if options['apply'] else 'DRY-RUN ONLY'}")
        self.stdout.write(f"Students checked: {len(rows)}")
        self.stdout.write(f"Updates eligible: {apply_count}")
        self.stdout.write(f"Unchanged clean rows: {skip_count}")
        self.stdout.write(f"Review/skip rows: {review_count}")
        self.stdout.write(f"Report: {report_path}")
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Dry-run only. Live DB not changed."))

    def _load_source(self, path):
        csv.field_size_limit(2147483647)
        data = {}
        with path.open("r", encoding="latin-1", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                sid = str(row.get("sid", "")).strip()
                if sid:
                    data[sid] = row
        return data

    def _propose(self, raw):
        value = str(raw or "").strip()
        if not value:
            return "", "BLANK", "NO"
        if not value.isdigit():
            return "", "NON_NUMERIC_REVIEW", "NO"
        if len(value) > 6:
            return "", "TOO_LONG_REVIEW", "NO"
        proposed = value.zfill(4) if len(value) < 4 else value
        leading_zero_ok = "YES" if len(proposed) == 4 else "REVIEW_LENGTH"
        return proposed, "NUMERIC_OK", leading_zero_ok

    def _range_info(self, group, proposed, section_name):
        if not proposed or not proposed.isdigit():
            return "", "", "", ""
        serial = int(proposed)
        ranges = CLASS9_SERIAL_RANGES if group == "CLASS9" else CLASS11_SERIAL_RANGES
        section_letter = str(section_name or "").replace("Section", "").strip().upper()
        for start, end, school, expected_section in ranges:
            if start <= serial <= end:
                bucket = f"{start:04d}-{end:04d}"
                if expected_section and section_letter and section_letter != expected_section:
                    return bucket, school, expected_section, "BOARD_SECTION_DIFFERS_FROM_CURRENT_SECTION"
                return bucket, school, expected_section, "MATCH" if expected_section else "RANGE_ONLY"
        return "", "", "", "OUTSIDE_KNOWN_RANGE"

    def _write_csv(self, path, rows):
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def _write_summary(self, path, rows, applied):
        counts = Counter(row["action"] for row in rows)
        flag_counts = Counter(row["fedu_type_flag"] for row in rows)
        duplicate_count = sum(1 for row in rows if row["duplicate_flag"])
        lines = [
            "# Board Serial Number Migration Summary",
            "",
            f"Mode: {'APPLY LIVE' if applied else 'DRY-RUN ONLY'}",
            f"Total active Class IX/XI students checked: {len(rows)}",
            "",
            "## Action Counts",
            *[f"- {key}: {value}" for key, value in sorted(counts.items())],
            "",
            "## fedu Type Flags",
            *[f"- {key}: {value}" for key, value in sorted(flag_counts.items())],
            "",
            f"Duplicate serial rows: {duplicate_count}",
            "",
            "## Mandatory Samples",
        ]
        for sid in ("10400", "10401", "10402", "10021", "10022"):
            row = next((item for item in rows if item["legacy_sid"] == sid), None)
            if row:
                lines.append(
                    f"- SID {sid}: {row['student_name']} | fedu_raw={row['fedu_raw']} | proposed={row['board_registration_no_proposed']} | action={row['action']}"
                )
        path.write_text("\n".join(lines), encoding="utf-8")
