from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Sum

from core.models import AcademicSession, FeeReceipt, Student


REPORT_PATH = (
    Path(r"E:\THPSIC-INTER-COLLEGE")
    / "05-reports"
    / "THPSIC_STUFEE_IMPORT_REPAIR_REPORT.md"
)


class Command(BaseCommand):
    help = "Repair THPSIC StuFee receipt import session/history flags after live migration."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write changes to the database.")
        parser.add_argument(
            "--confirm",
            default="",
            help="Required confirmation token for --apply. Use: THPSIC",
        )
        parser.add_argument(
            "--target-session",
            default="",
            help="Target session name. Defaults to the active session.",
        )
        parser.add_argument(
            "--placeholder-sid",
            type=int,
            default=6840,
            help="Legacy SID created as placeholder by the first StuFee import.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        if apply_changes and options["confirm"] != "THPSIC":
            raise CommandError("--apply requires --confirm THPSIC")

        target_session = self.get_target_session(options["target_session"])
        before = self.snapshot(target_session, options["placeholder_sid"])

        if apply_changes:
            with transaction.atomic():
                self.apply_repair(target_session, options["placeholder_sid"])

        after = self.snapshot(target_session, options["placeholder_sid"])
        report = self.write_report(
            mode="APPLY" if apply_changes else "DRY RUN",
            target_session=target_session,
            before=before,
            after=after,
            placeholder_sid=options["placeholder_sid"],
        )

        self.stdout.write(self.style.SUCCESS(f"{'APPLY' if apply_changes else 'DRY RUN'} complete."))
        self.stdout.write(f"DB: {settings.DATABASES['default']['NAME']}")
        self.stdout.write(f"Report: {report}")
        self.stdout.write(f"Legacy receipts: {after['legacy_receipts']}")
        self.stdout.write(f"Legacy receipts in target session: {after['legacy_in_target_session']}")
        self.stdout.write(f"History-only receipts: {after['history_only_receipts']}")
        self.stdout.write(f"Active students: {after['active_students']}")

    def get_target_session(self, session_name):
        if session_name:
            return AcademicSession.objects.get(name=session_name)
        session = AcademicSession.objects.filter(is_active=True).order_by("-starts_on", "name").first()
        if not session:
            raise CommandError("No active AcademicSession found.")
        return session

    def legacy_receipts(self):
        return FeeReceipt.objects.filter(
            legacy_receipt_no__isnull=False,
            receipt_no__startswith="SF-",
            is_cancelled=False,
        )

    def snapshot(self, target_session, placeholder_sid):
        legacy = self.legacy_receipts()
        placeholder = Student.objects.filter(legacy_sid=placeholder_sid).first()
        placeholder_data = None
        if placeholder:
            placeholder_data = {
                "id": placeholder.id,
                "name": placeholder.full_name,
                "active": placeholder.is_active,
                "class": placeholder.current_class.name if placeholder.current_class else "",
                "section": placeholder.current_section.name if placeholder.current_section else "",
                "receipts": FeeReceipt.objects.filter(student=placeholder).count(),
                "received": FeeReceipt.objects.filter(student=placeholder).aggregate(
                    total=Sum("received_amount")
                )["total"]
                or Decimal("0.00"),
            }

        return {
            "db": settings.DATABASES["default"]["NAME"],
            "sessions": list(AcademicSession.objects.values_list("name", "is_active")),
            "active_students": Student.objects.filter(is_active=True).count(),
            "total_students": Student.objects.count(),
            "legacy_receipts": legacy.count(),
            "legacy_received": legacy.aggregate(total=Sum("received_amount"))["total"] or Decimal("0.00"),
            "legacy_lines": legacy.aggregate(total=Count("lines"))["total"] or 0,
            "legacy_in_target_session": legacy.filter(session=target_session).count(),
            "legacy_outside_target_session": legacy.exclude(session=target_session).count(),
            "history_only_receipts": legacy.filter(carried_forward=True).count(),
            "non_history_legacy_receipts": legacy.filter(carried_forward=False).count(),
            "session_breakdown": list(
                legacy.values("session__name")
                .annotate(count=Count("id"), total=Sum("received_amount"))
                .order_by("session__name")
            ),
            "placeholder": placeholder_data,
        }

    def apply_repair(self, target_session, placeholder_sid):
        receipts = self.legacy_receipts().select_related(
            "student",
            "student__current_class",
            "student__current_section",
        )

        for receipt in receipts:
            student = receipt.student
            receipt.session = target_session
            receipt.carried_forward = True
            receipt.student_name_snapshot = student.full_name or ""
            receipt.father_name_snapshot = student.father_name or ""
            receipt.class_snapshot = student.current_class.name if student.current_class else ""
            receipt.section_snapshot = student.current_section.name if student.current_section else ""
            receipt.save(
                update_fields=[
                    "session",
                    "carried_forward",
                    "student_name_snapshot",
                    "father_name_snapshot",
                    "class_snapshot",
                    "section_snapshot",
                ]
            )

        placeholder = Student.objects.filter(legacy_sid=placeholder_sid).first()
        if placeholder and placeholder.is_active:
            placeholder.is_active = False
            placeholder.fee_package_enabled = False
            placeholder.fee_package_note = "Inactive legacy placeholder from StuFee import"
            placeholder.save(update_fields=["is_active", "fee_package_enabled", "fee_package_note"])

    def write_report(self, *, mode, target_session, before, after, placeholder_sid):
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# THPSIC StuFee Import Repair Report",
            "",
            f"- Mode: {mode}",
            f"- DB: `{settings.DATABASES['default']['NAME']}`",
            f"- Target session: {target_session.name}",
            "",
            "## Purpose",
            "",
            "- Move imported StuFee receipts into the active 2026-27 session.",
            "- Mark them `carried_forward=True` so they remain visible as pre-migration history but do not reduce current due twice.",
            f"- Mark placeholder SID {placeholder_sid} inactive, keeping its receipt history.",
            "",
            "## Before",
            "",
            *self.format_snapshot(before),
            "",
            "## After",
            "",
            *self.format_snapshot(after),
        ]
        REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
        return REPORT_PATH

    def format_snapshot(self, data):
        placeholder = data["placeholder"] or {}
        return [
            f"- Active students: {data['active_students']}",
            f"- Total students: {data['total_students']}",
            f"- Legacy receipts: {data['legacy_receipts']}",
            f"- Legacy received total: Rs {data['legacy_received']}",
            f"- Legacy receipt lines: {data['legacy_lines']}",
            f"- Legacy receipts in target session: {data['legacy_in_target_session']}",
            f"- Legacy receipts outside target session: {data['legacy_outside_target_session']}",
            f"- History-only receipts: {data['history_only_receipts']}",
            f"- Non-history legacy receipts: {data['non_history_legacy_receipts']}",
            f"- Session breakdown: {data['session_breakdown']}",
            (
                "- Placeholder: "
                f"id={placeholder.get('id', '-')}, name={placeholder.get('name', '-')}, "
                f"active={placeholder.get('active', '-')}, "
                f"class={placeholder.get('class', '-')}-{placeholder.get('section', '-')}, "
                f"receipts={placeholder.get('receipts', '-')}, "
                f"received=Rs {placeholder.get('received', '-')}"
            ),
        ]
