import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import SchoolProfile


class Command(BaseCommand):
    help = "Import active school profile from legacy comp_mast and enviromain CSV exports."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-dir",
            default=r"D:\english medium\migration_audit\exports",
            help="Folder containing comp_mast.csv and enviromain.csv.",
        )

    def handle(self, *args, **options):
        source_dir = Path(options["source_dir"])
        comp_mast = source_dir / "comp_mast.csv"
        enviromain = source_dir / "enviromain.csv"

        if not comp_mast.exists():
            raise CommandError(f"comp_mast.csv not found: {comp_mast}")
        if not enviromain.exists():
            raise CommandError(f"enviromain.csv not found: {enviromain}")

        comp_rows = self.read_csv(comp_mast)
        env_rows = self.read_csv(enviromain)
        active_comp_code = self.to_int(env_rows[0].get("comp_no")) if env_rows else None

        if active_comp_code is None:
            raise CommandError("Active comp_no not found in enviromain.csv.")

        active_row = None
        for row in comp_rows:
            if self.to_int(row.get("comp_code")) == active_comp_code:
                active_row = row
                break

        if active_row is None:
            raise CommandError(f"comp_mast row not found for comp_code {active_comp_code}.")

        SchoolProfile.objects.update(is_active=False)
        profile, _ = SchoolProfile.objects.update_or_create(
            legacy_comp_code=active_comp_code,
            defaults={
                "name": self.clean(active_row.get("comp_name")),
                "address_line1": self.clean(active_row.get("comp_add1")),
                "address_line2": self.clean(active_row.get("comp_add2")),
                "address_line3": self.clean(active_row.get("comp_add3")),
                "email": self.clean(active_row.get("E_mail")) or self.clean(active_row.get("comp_add4")),
                "phone": self.clean(active_row.get("phone")),
                "current_year": self.clean(active_row.get("cur_yr")),
                "is_active": True,
            },
        )

        self.stdout.write(self.style.SUCCESS(f"Active school profile imported: {profile.name}"))

    def read_csv(self, path):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

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
