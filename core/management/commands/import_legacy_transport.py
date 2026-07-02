import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    LegacyImportBatch,
    Student,
    StudentTransport,
    TransportBus,
    TransportRoute,
)


class Command(BaseCommand):
    help = (
        "Import legacy Busmaster.csv, RouteMaster.csv, and BUS_APPLICABLE.csv exports. "
        "Run migration_audit/export_mdb_tables.ps1 with -Tables @('Busmaster','RouteMaster','BUS_APPLICABLE') first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-dir",
            default=r"D:\english medium\migration_audit\exports",
            help="Folder containing Busmaster.csv, RouteMaster.csv, and BUS_APPLICABLE.csv.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate CSVs without writing to the database.",
        )

    def handle(self, *args, **options):
        source_dir = Path(options["source_dir"])
        dry_run = options["dry_run"]
        bus_rows = self.read_required_csv(source_dir / "Busmaster.csv")
        route_rows = self.read_required_csv(source_dir / "RouteMaster.csv")
        assignment_rows = self.read_required_csv(source_dir / "BUS_APPLICABLE.csv")

        summary = {
            "bus_rows_seen": len(bus_rows),
            "buses_imported": 0,
            "route_rows_seen": len(route_rows),
            "routes_imported": 0,
            "assignment_rows_seen": len(assignment_rows),
            "assignments_imported": 0,
            "assignments_skipped_no_student": 0,
            "assignments_name_mismatch": 0,
            "assignments_route_matched": 0,
            "assignments_bus_matched": 0,
        }

        with transaction.atomic():
            bus_by_code, bus_by_label = self.import_buses(bus_rows, dry_run, summary)
            route_by_code, route_by_name = self.import_routes(route_rows, dry_run, summary)
            self.import_assignments(
                assignment_rows,
                route_by_code,
                route_by_name,
                bus_by_code,
                bus_by_label,
                dry_run,
                summary,
            )

            if dry_run:
                transaction.set_rollback(True)

        if not dry_run:
            LegacyImportBatch.objects.create(
                source_database="SCHOOL7.mdb CSV export",
                source_table="Busmaster/RouteMaster/BUS_APPLICABLE",
                records_seen=summary["bus_rows_seen"] + summary["route_rows_seen"] + summary["assignment_rows_seen"],
                records_imported=summary["buses_imported"] + summary["routes_imported"] + summary["assignments_imported"],
                notes=(
                    "Transport import keeps legacy route/bus labels when BUS_APPLICABLE text does not exactly "
                    "match Busmaster or RouteMaster."
                ),
            )

        mode = "DRY RUN" if dry_run else "IMPORT"
        self.stdout.write(self.style.SUCCESS(f"{mode} complete."))
        for key, value in summary.items():
            self.stdout.write(f"{key}: {value}")

    def import_buses(self, rows, dry_run, summary):
        by_code = {}
        by_label = {}

        for row in rows:
            legacy_code = self.to_int(row.get("BUS_CODE"))
            name = self.clean(row.get("BUS_NAME")) or self.clean(row.get("BUSNO")) or f"Bus {legacy_code or ''}".strip()
            defaults = {
                "name": name,
                "vehicle_no": self.clean(row.get("BUSNO")),
                "driver_name": self.clean(row.get("DRIVER_NAME")),
                "helpline": self.clean(row.get("HELPLINE")),
                "default_amount": self.to_decimal(row.get("BUS_AMT")) or Decimal("0.00"),
                "is_active": self.clean(row.get("AED")).upper() != "D",
            }

            if dry_run:
                bus = None
            elif legacy_code:
                bus, _ = TransportBus.objects.update_or_create(legacy_bus_code=legacy_code, defaults=defaults)
            else:
                bus, _ = TransportBus.objects.update_or_create(name=name, defaults=defaults)

            summary["buses_imported"] += 1
            self.index_transport_item(by_code, by_label, legacy_code, [name, defaults["vehicle_no"]], bus)

        return by_code, by_label

    def import_routes(self, rows, dry_run, summary):
        by_code = {}
        by_name = {}

        for row in rows:
            legacy_code = self.to_int(row.get("ROUTE_CODE"))
            name = self.clean(row.get("ROUTE_NAME")) or f"Route {legacy_code or ''}".strip()
            defaults = {
                "name": name,
                "monthly_charge": self.to_decimal(row.get("CHARGE")) or Decimal("0.00"),
                "is_active": self.clean(row.get("AED")).upper() != "D",
            }

            if dry_run:
                route = None
            elif legacy_code:
                route, _ = TransportRoute.objects.update_or_create(legacy_route_code=legacy_code, defaults=defaults)
            else:
                route, _ = TransportRoute.objects.update_or_create(name=name, defaults=defaults)

            summary["routes_imported"] += 1
            self.index_transport_item(by_code, by_name, legacy_code, [name], route)

        return by_code, by_name

    def import_assignments(
        self,
        rows,
        route_by_code,
        route_by_name,
        bus_by_code,
        bus_by_label,
        dry_run,
        summary,
    ):
        for row in rows:
            student_sid = self.to_int(row.get("STUDENT_ID"))
            student = Student.objects.filter(legacy_sid=student_sid).first() if student_sid else None
            if not student:
                summary["assignments_skipped_no_student"] += 1
                continue

            legacy_student_name = self.clean(row.get("NAME"))
            legacy_father_name = self.clean(row.get("FATHER"))
            if self.normalized(legacy_student_name) and self.normalized(legacy_student_name) != self.normalized(student.full_name):
                summary["assignments_name_mismatch"] += 1

            route = self.find_route(row, route_by_code, route_by_name, dry_run)
            bus = self.find_bus(row, bus_by_code, bus_by_label, dry_run)
            if route:
                summary["assignments_route_matched"] += 1
            if bus:
                summary["assignments_bus_matched"] += 1

            if not dry_run:
                defaults = {
                    "student": student,
                    "route": route,
                    "bus": bus,
                    "legacy_student_name": legacy_student_name,
                    "legacy_father_name": legacy_father_name,
                    "legacy_route_name": self.clean(row.get("ROUTED")) or self.clean(row.get("ROUT")),
                    "legacy_bus_label": self.clean(row.get("BUSNO")),
                    "stop_name": self.clean(row.get("STOP")),
                    "applied_on": self.parse_date(row.get("APP_DATE")) or self.parse_date(row.get("DATE")),
                    "charge_month": self.clean(row.get("CMONTH")),
                    "due_month": self.clean(row.get("DMONTH")),
                    "is_transport_enabled": self.clean(row.get("BUS_DSEL")).upper() != "NO",
                    "is_active": self.clean(row.get("BUS_DSEL")).upper() != "NO",
                }
                legacy_sr_no = self.to_int(row.get("SR_NO"))
                if legacy_sr_no:
                    StudentTransport.objects.update_or_create(legacy_sr_no=legacy_sr_no, defaults=defaults)
                else:
                    StudentTransport.objects.update_or_create(student=student, defaults=defaults)

            summary["assignments_imported"] += 1

    def find_route(self, row, route_by_code, route_by_name, dry_run):
        route_code = self.to_int(row.get("ROUT"))
        route_name = self.clean(row.get("ROUTED")) or self.clean(row.get("ROUT"))

        if route_code and route_code in route_by_code:
            route = route_by_code[route_code]
            return route if not dry_run else True
        if self.normalized(route_name) in route_by_name:
            route = route_by_name[self.normalized(route_name)]
            return route if not dry_run else True
        if not dry_run:
            return TransportRoute.objects.filter(name__iexact=route_name).first()
        return None

    def find_bus(self, row, bus_by_code, bus_by_label, dry_run):
        bus_code = self.to_int(row.get("BUS_NO"))
        bus_label = self.clean(row.get("BUSNO"))

        if bus_code and bus_code in bus_by_code:
            bus = bus_by_code[bus_code]
            return bus if not dry_run else True
        if self.normalized(bus_label) in bus_by_label:
            bus = bus_by_label[self.normalized(bus_label)]
            return bus if not dry_run else True
        if not dry_run:
            return TransportBus.objects.filter(vehicle_no__iexact=bus_label).first()
        return None

    def index_transport_item(self, by_code, by_label, code, labels, instance):
        if code:
            by_code[code] = instance
        for label in labels:
            normalized = self.normalized(label)
            if normalized:
                by_label[normalized] = instance

    def read_required_csv(self, path):
        if not path.exists():
            raise CommandError(f"{path.name} not found at {path}. Export transport tables first.")
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def clean(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def normalized(self, value):
        return " ".join(self.clean(value).lower().split())

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
