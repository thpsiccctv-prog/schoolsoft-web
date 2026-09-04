import shutil
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


DEFAULT_BACKUP_ROOT = Path(r"E:\THPSIC-INTER-COLLEGE\04-backups\daily_backups")


class Command(BaseCommand):
    help = "Create a consistent SQLite backup using sqlite3 backup API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out-dir",
            default=str(DEFAULT_BACKUP_ROOT),
            help="Backup output directory.",
        )
        parser.add_argument(
            "--label",
            default="manual",
            help="Short label used in the backup filename.",
        )
        parser.add_argument(
            "--copy-media",
            action="store_true",
            help="Also copy MEDIA_ROOT next to the database backup.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "sqlite":
            raise CommandError("safe_sqlite_backup only supports SQLite databases.")

        out_dir = Path(options["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        label = "".join(ch for ch in options["label"] if ch.isalnum() or ch in ("-", "_")).strip() or "manual"
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        backup_dir = out_dir / f"{stamp}-{label}"
        backup_dir.mkdir(parents=True, exist_ok=False)

        db_path = Path(connection.settings_dict["NAME"])
        backup_path = backup_dir / "db.sqlite3"

        connection.ensure_connection()
        destination = sqlite3.connect(backup_path)
        try:
            connection.connection.backup(destination)
        finally:
            destination.close()

        if options["copy_media"]:
            media_root = Path(settings.MEDIA_ROOT)
            if media_root.exists() and media_root.is_dir():
                shutil.copytree(media_root, backup_dir / "media")

        note = (
            "THPSIC SchoolSoft SQLite Backup\n"
            "================================\n\n"
            f"Created at: {timezone.localtime():%d/%m/%Y %I:%M:%S %p}\n"
            f"Source DB: {db_path}\n"
            f"Backup DB: {backup_path}\n\n"
            "Restore rule: app band karke current live DB ka alag backup banayein, "
            "phir is db.sqlite3 ko live db.sqlite3 par replace karein.\n"
        )
        (backup_dir / "RESTORE-NOTE.txt").write_text(note, encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Backup complete: {backup_path}"))
