import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.board_registration_exports import (
    EXPORT_DEFINITIONS,
    build_rows,
    export_columns,
    export_filename,
    output_timestamp,
)


class Command(BaseCommand):
    help = "Export UP Board registration CSV files for Class IX and Class XI templates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--kind",
            choices=["all", *EXPORT_DEFINITIONS.keys()],
            default="all",
            help="Which board registration export to generate.",
        )
        parser.add_argument(
            "--output-dir",
            default=r"E:\THPSIC-INTER-COLLEGE\05-reports\board-registration-exports",
            help="Folder where CSV files will be written.",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        kinds = list(EXPORT_DEFINITIONS.keys()) if options["kind"] == "all" else [options["kind"]]
        timestamp = output_timestamp()
        total_rows = 0

        for kind in kinds:
            filename = export_filename(kind).replace(".csv", f"_{timestamp}.csv")
            output_path = output_dir / filename
            rows = build_rows(kind)
            with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(export_columns(kind))
                writer.writerows(rows)
            total_rows += len(rows)
            self.stdout.write(self.style.SUCCESS(f"{kind}: {len(rows)} rows -> {output_path}"))

        if total_rows == 0:
            raise CommandError("No board registration rows exported. Check classes and Class 11 board source fields.")
