import csv
import sys
import random

csv.field_size_limit(2147483647)
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Student

class Command(BaseCommand):
    help = "Backfill address and caste fields from legacy ADDMISSION.csv"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=str,
            default=r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\ADDMISSION.csv",
        )
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm", type=str)

    def handle(self, *args, **options):
        source_path = Path(options["source"])
        dry_run = not options["apply"]

        if not dry_run and options["confirm"] != "THPSIC":
            raise CommandError("You must provide --confirm THPSIC to run with --apply")

        preview_csv_path = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports\STUDENT_ADDRESS_CASTE_BACKFILL_PREVIEW.csv")
        report_path = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports\STUDENT_ADDRESS_CASTE_BACKFILL_REPORT.md")

        caste_map = {
            "SC": "1",
            "ST": "2",
            "OBC": "3",
            "GENERAL": "4",
            "EWS": "5",
        }

        def normalize_district(d):
            d = d.strip().upper()
            if not d:
                return ""
            if "KUSHINAGAR" in d:
                return "Kushinagar"
            return d.title()

        matched = 0
        unmatched = 0
        exceptions = []
        preview_data = []
        non_kushinagar = {}

        # Before stats
        before_counts = {
            "village_locality": Student.objects.exclude(village_locality="").count(),
            "block": Student.objects.exclude(block="").count(),
            "district": Student.objects.exclude(district="").count(),
            "board_caste_code": Student.objects.exclude(board_caste_code="").count(),
            "caste": Student.objects.exclude(caste="").count(),
        }

        # Dict of students by legacy_sid
        students = {s.legacy_sid: s for s in Student.objects.all() if s.legacy_sid}

        with source_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            
            with transaction.atomic():
                for row in reader:
                    sid_str = row.get("sid", "").strip()
                    if not sid_str:
                        continue
                        
                    try:
                        legacy_sid = int(float(sid_str))
                    except ValueError:
                        continue

                    s = students.get(legacy_sid)
                    if not s:
                        unmatched += 1
                        continue

                    padr1 = row.get("padr1", "").strip()
                    padr2 = row.get("padr2", "").strip()
                    padr3 = row.get("padr3", "").strip()
                    cast = row.get("cast", "").strip().upper()
                    cast1 = row.get("cast1", "").strip()

                    new_village = padr1
                    new_block = padr2
                    new_district = normalize_district(padr3)
                    new_board_code = caste_map.get(cast, "")
                    new_caste = cast1

                    # Preserve existing if blank
                    final_village = new_village if new_village else s.village_locality
                    final_block = new_block if new_block else s.block
                    final_district = new_district if new_district else s.district
                    final_board_code = new_board_code if new_board_code else s.board_caste_code
                    final_caste = new_caste if new_caste else s.caste

                    if new_district and new_district != "Kushinagar":
                        non_kushinagar[new_district] = non_kushinagar.get(new_district, 0) + 1

                    if not new_block or not new_district:
                        exceptions.append({
                            "legacy_sid": legacy_sid,
                            "name": s.full_name,
                            "issue": "Blank block or district in source",
                        })

                    preview_row = {
                        "legacy_sid": legacy_sid,
                        "full_name": s.full_name,
                        "old_village": s.village_locality,
                        "new_village": final_village,
                        "old_block": s.block,
                        "new_block": final_block,
                        "old_district": s.district,
                        "new_district": final_district,
                        "old_board_caste": s.board_caste_code,
                        "new_board_caste": final_board_code,
                        "old_caste": s.caste,
                        "new_caste": final_caste,
                    }
                    preview_data.append(preview_row)

                    matched += 1

                    if not dry_run:
                        s.village_locality = final_village
                        s.block = final_block
                        s.district = final_district
                        s.board_caste_code = final_board_code
                        s.caste = final_caste
                        s.save(update_fields=['village_locality', 'block', 'district', 'board_caste_code', 'caste'])

        if dry_run:
            # Write preview CSV
            with preview_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
                if preview_data:
                    writer = csv.DictWriter(f, fieldnames=preview_data[0].keys())
                    writer.writeheader()
                    writer.writerows(preview_data)

            # Generate Report
            sample_size = min(10, len(preview_data))
            samples = random.sample(preview_data, sample_size) if preview_data else []
            
            report = [
                "# Student Address & Caste Backfill Preview Report",
                f"**Mode**: {'Dry Run' if dry_run else 'Live Apply'}",
                "",
                "## Summary",
                f"- Total matched students: {matched}",
                f"- Exceptions / blank overrides avoided: {len(exceptions)}",
                "",
                "## Fill Counts (Before -> Expected After)",
                f"- village_locality: {before_counts['village_locality']} -> {len([d for d in preview_data if d['new_village']])}",
                f"- block: {before_counts['block']} -> {len([d for d in preview_data if d['new_block']])}",
                f"- district: {before_counts['district']} -> {len([d for d in preview_data if d['new_district']])}",
                f"- board_caste_code: {before_counts['board_caste_code']} -> {len([d for d in preview_data if d['new_board_caste']])}",
                f"- caste: {before_counts['caste']} -> {len([d for d in preview_data if d['new_caste']])}",
                "",
                "## Non-Kushinagar Districts",
            ]
            
            for dist, count in non_kushinagar.items():
                report.append(f"- {dist}: {count}")
                
            report.append("")
            report.append("## Exceptions (Blank Block/District in source)")
            for ex in exceptions[:10]:
                report.append(f"- SID {ex['legacy_sid']}: {ex['name']} - {ex['issue']}")
            if len(exceptions) > 10:
                report.append(f"- ... and {len(exceptions) - 10} more.")
                
            report.append("")
            report.append("## Random Samples")
            report.append("| SID | Name | Old Village -> New | Old Block -> New | Old Dist -> New | Old Caste -> New |")
            report.append("|---|---|---|---|---|---|")
            for s in samples:
                report.append(f"| {s['legacy_sid']} | {s['full_name']} | {s['old_village']} -> {s['new_village']} | {s['old_block']} -> {s['new_block']} | {s['old_district']} -> {s['new_district']} | {s['old_board_caste']} -> {s['new_board_caste']} |")

            with report_path.open("w", encoding="utf-8") as f:
                f.write("\n".join(report))
                
            self.stdout.write(f"Dry run complete. Report at {report_path}")

        else:
            self.stdout.write(f"Apply complete. Updated {matched} students.")
