from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Sum

from core.fee_engine import DEFAULT_PACKAGE_TOTAL, PACKAGE_FEE_HEAD_NAME
from core.models import AcademicSession, FeeHead, FeeStructure, SchoolClass, Student, StudentOpeningBalance


REPORT_DIR = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports")
READMISSION_HEAD_NAME = "Re-admission Fee"
READMISSION_CLASSES = ("IX", "XI (ART)", "XI (BIO)", "XI (MATHS)")
POLICY_REFERENCE = "THPSIC fee policy 2026-27"
OFFICIAL_CLASSES = (
    "IX",
    "X",
    "XI (ART)",
    "XI (BIO)",
    "XI (COM)",
    "XI (MATHS)",
    "XII (ART)",
    "XII (BIO)",
    "XII (COM)",
    "XII (MATHS)",
)
OFFICIAL_HEADS = ("Admission / Reg Fee", "Practical Fee", "Tuition Fee", "Exam Fee", "Annual Fee")
OFFICIAL_FEE_ROWS = {
    # Tuition Fee is stored as the monthly rate because the fee engine's
    # MONTHLY rule multiplies it by the number of academic months due.
    "IX": {"Admission / Reg Fee": 2000, "Practical Fee": 600, "Tuition Fee": 500, "Exam Fee": 1500},
    "X": {"Annual Fee": 2000, "Practical Fee": 1800, "Tuition Fee": 500, "Exam Fee": 1500},
    "XI (ART)": {"Admission / Reg Fee": 2000, "Practical Fee": 600, "Tuition Fee": 600, "Exam Fee": 1500},
    "XI (BIO)": {"Admission / Reg Fee": 2000, "Practical Fee": 600, "Tuition Fee": 600, "Exam Fee": 1500},
    "XI (COM)": {"Admission / Reg Fee": 2000, "Practical Fee": 600, "Tuition Fee": 600, "Exam Fee": 1500},
    "XI (MATHS)": {"Admission / Reg Fee": 2000, "Practical Fee": 600, "Tuition Fee": 600, "Exam Fee": 1500},
    "XII (ART)": {"Annual Fee": 2000, "Practical Fee": 1200, "Tuition Fee": 600, "Exam Fee": 1500},
    "XII (BIO)": {"Annual Fee": 2000, "Practical Fee": 1800, "Tuition Fee": 600, "Exam Fee": 1500},
    "XII (COM)": {"Annual Fee": 2000, "Practical Fee": 1200, "Tuition Fee": 600, "Exam Fee": 1500},
    "XII (MATHS)": {"Annual Fee": 2000, "Practical Fee": 1800, "Tuition Fee": 600, "Exam Fee": 1500},
}


class Command(BaseCommand):
    help = "Dry-run or apply THPSIC section/package fee policy."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write fee policy changes.")
        parser.add_argument("--confirm", default="", help="Required as --confirm THPSIC with --apply.")

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        if apply_changes and options["confirm"] != "THPSIC":
            raise CommandError("Live apply requires --confirm THPSIC.")

        session = AcademicSession.objects.filter(is_active=True).order_by("-starts_on").first()
        if not session:
            raise CommandError("No active AcademicSession found.")

        before = self.snapshot(session)
        planned = self.plan(session)

        if apply_changes:
            with transaction.atomic():
                self.apply_policy(session)

        after = self.snapshot(session)
        report_path = self.write_report(
            mode="APPLY" if apply_changes else "DRY RUN",
            session=session,
            before=before,
            after=after,
            planned=planned,
        )

        self.stdout.write(self.style.SUCCESS(f"{'APPLY' if apply_changes else 'DRY RUN'} SUMMARY"))
        self.stdout.write(f"DB: {settings.DATABASES['default']['NAME']}")
        self.stdout.write(f"Package students: {planned['package_students']}")
        self.stdout.write(f"Zero-fee section students: {planned['zero_students']}")
        self.stdout.write(f"Official IX-XII structure rows: {planned['official_structure_rows']}")
        self.stdout.write(f"Legacy IX-XII rows to deactivate: {planned['official_structures_to_replace']}")
        self.stdout.write(f"Report: {report_path}")
        if not apply_changes:
            self.stdout.write("DB was not changed. Use --apply --confirm THPSIC after review.")

    def plan(self, session):
        active_students = Student.objects.filter(is_active=True).select_related("current_class", "current_section")
        policy_package_students = []
        zero_students = []
        direct_manual_students = []

        for student in active_students:
            if student.is_zero_fee_section:
                zero_students.append(student)
                continue
            if student.fee_section_name == "D" or student.is_commerce_class:
                policy_package_students.append(student)
            elif student.fee_package_enabled:
                direct_manual_students.append(student)

        official_structures_to_replace = FeeStructure.objects.filter(
            session=session,
            school_class__name__in=OFFICIAL_CLASSES,
            is_active=True,
        ).exclude(fee_head__name__in=OFFICIAL_HEADS)
        heads_without_charge_rule = FeeHead.objects.filter(
            is_active=True,
            is_transport=False,
            new_student_charge_rule=FeeHead.ChargeRule.NOT_APPLICABLE,
            old_student_charge_rule=FeeHead.ChargeRule.NOT_APPLICABLE,
        ).exclude(
            name__in=[
                "Balance Fee",
                "Concession",
                "Late Fee",
                PACKAGE_FEE_HEAD_NAME,
            ]
        ).count()
        readmission_existing = FeeStructure.objects.filter(
            session=session,
            school_class__name__in=READMISSION_CLASSES,
            fee_head__name=READMISSION_HEAD_NAME,
            is_active=True,
        ).count()

        return {
            "package_students": len(policy_package_students),
            "zero_students": len(zero_students),
            "manual_package_students": len(direct_manual_students),
            "official_structures_to_replace": official_structures_to_replace.count(),
            "official_structure_rows": sum(len(heads) for heads in OFFICIAL_FEE_ROWS.values()),
            "heads_without_charge_rule": heads_without_charge_rule,
            "readmission_existing": readmission_existing,
            "package_sample": policy_package_students[:8],
            "zero_sample": zero_students[:8],
            "manual_package_sample": direct_manual_students[:8],
        }

    def apply_policy(self, session):
        self.fix_fee_head_charge_rules()
        FeeHead.objects.update_or_create(
            name=PACKAGE_FEE_HEAD_NAME,
            defaults={
                "legacy_column": "PACKAGE_FEE",
                "frequency": FeeHead.Frequency.OPTIONAL,
                "applies_to": FeeHead.AppliesTo.BOTH,
                "new_student_charge_rule": FeeHead.ChargeRule.NOT_APPLICABLE,
                "old_student_charge_rule": FeeHead.ChargeRule.NOT_APPLICABLE,
                "new_student_charge_months": [],
                "old_student_charge_months": [],
                "is_transport": False,
                "is_active": True,
            },
        )
        self.apply_official_fee_structures(session)

        active_students = Student.objects.filter(is_active=True).select_related("current_class", "current_section")
        for student in active_students:
            update_fields = []
            if student.is_zero_fee_section:
                if student.fee_package_enabled:
                    student.fee_package_enabled = False
                    update_fields.append("fee_package_enabled")
            elif student.fee_section_name == "D" or student.is_commerce_class:
                if not student.fee_package_enabled:
                    student.fee_package_enabled = True
                    update_fields.append("fee_package_enabled")
                if not student.fee_package_total or student.fee_package_total <= 0:
                    student.fee_package_total = DEFAULT_PACKAGE_TOTAL
                    update_fields.append("fee_package_total")
                if not student.fee_package_note:
                    student.fee_package_note = "Auto package by THPSIC section/stream policy"
                    update_fields.append("fee_package_note")

            if update_fields:
                student.save(update_fields=update_fields)

    def apply_official_fee_structures(self, session):
        FeeStructure.objects.filter(session=session, school_class__name__in=OFFICIAL_CLASSES).update(is_active=False)

        for class_name, heads in OFFICIAL_FEE_ROWS.items():
            school_class = SchoolClass.objects.get(name=class_name)
            for head_name, amount in heads.items():
                head = self.get_or_update_official_head(head_name)
                FeeStructure.objects.update_or_create(
                    session=session,
                    school_class=school_class,
                    fee_head=head,
                    defaults={
                        "amount": Decimal(str(amount)).quantize(Decimal("0.01")),
                        "is_active": True,
                        "source": FeeStructure.Source.MANUAL,
                        "source_reference": "Official annual fee structure 2026-27",
                    },
                )

    def get_or_update_official_head(self, head_name):
        defaults = self.charge_rule_defaults_for_name(head_name)
        head, _created = FeeHead.objects.update_or_create(name=head_name, defaults=defaults)
        return head

    def fix_fee_head_charge_rules(self):
        for head in FeeHead.objects.filter(is_active=True):
            defaults = self.charge_rule_defaults(head)
            if not defaults:
                continue
            for field, value in defaults.items():
                setattr(head, field, value)
            head.save(update_fields=list(defaults))

    def charge_rule_defaults(self, head):
        if head.is_transport:
            return {
                "new_student_charge_rule": FeeHead.ChargeRule.NOT_APPLICABLE,
                "old_student_charge_rule": FeeHead.ChargeRule.NOT_APPLICABLE,
                "new_student_charge_months": [],
                "old_student_charge_months": [],
            }
        if head.name in {"Admission Fee", "Admission / Reg Fee", "Practical Fee", "Board Fee", "Annual Fee", "Tuition Fee", "Exam Fee"}:
            return self.charge_rule_defaults_for_name(head.name)
        if head.name in {READMISSION_HEAD_NAME, PACKAGE_FEE_HEAD_NAME, "Balance Fee", "Concession", "Late Fee"}:
            return None
        if head.frequency in {FeeHead.Frequency.MONTHLY, FeeHead.Frequency.ANNUAL, FeeHead.Frequency.ONE_TIME}:
            return {
                "applies_to": FeeHead.AppliesTo.BOTH,
                "new_student_charge_rule": FeeHead.ChargeRule.FIXED_MONTHS,
                "old_student_charge_rule": FeeHead.ChargeRule.FIXED_MONTHS,
                "new_student_charge_months": ["APR"],
                "old_student_charge_months": ["APR"],
            }
        return None

    def charge_rule_defaults_for_name(self, head_name):
        base = {
            "legacy_column": head_name.upper().replace(" / ", "_").replace(" ", "_"),
            "is_transport": False,
            "is_active": True,
        }
        if head_name in {"Admission Fee", "Admission / Reg Fee"}:
            return {
                **base,
                "frequency": FeeHead.Frequency.ONE_TIME,
                "applies_to": FeeHead.AppliesTo.NEW,
                "new_student_charge_rule": FeeHead.ChargeRule.ADMISSION_MONTH,
                "old_student_charge_rule": FeeHead.ChargeRule.NOT_APPLICABLE,
                "new_student_charge_months": [],
                "old_student_charge_months": [],
            }
        if head_name == "Tuition Fee":
            return {
                **base,
                "frequency": FeeHead.Frequency.MONTHLY,
                "applies_to": FeeHead.AppliesTo.BOTH,
                "new_student_charge_rule": FeeHead.ChargeRule.MONTHLY,
                "old_student_charge_rule": FeeHead.ChargeRule.MONTHLY,
                "new_student_charge_months": [],
                "old_student_charge_months": [],
            }
        if head_name == "Exam Fee":
            return {
                **base,
                "frequency": FeeHead.Frequency.INSTALLMENT,
                "applies_to": FeeHead.AppliesTo.BOTH,
                "new_student_charge_rule": FeeHead.ChargeRule.FIXED_MONTHS,
                "old_student_charge_rule": FeeHead.ChargeRule.FIXED_MONTHS,
                "new_student_charge_months": ["AUG", "NOV", "JAN"],
                "old_student_charge_months": ["AUG", "NOV", "JAN"],
            }
        if head_name == "Practical Fee":
            return {
                **base,
                "frequency": FeeHead.Frequency.INSTALLMENT,
                "applies_to": FeeHead.AppliesTo.BOTH,
                "new_student_charge_rule": FeeHead.ChargeRule.FIXED_MONTHS,
                "old_student_charge_rule": FeeHead.ChargeRule.FIXED_MONTHS,
                "new_student_charge_months": ["NOV"],
                "old_student_charge_months": ["NOV"],
            }
        if head_name == "Board Fee":
            months = ["DEC"]
        else:
            months = ["APR"]
        return {
            **base,
            "frequency": FeeHead.Frequency.ANNUAL,
            "applies_to": FeeHead.AppliesTo.BOTH,
            "new_student_charge_rule": FeeHead.ChargeRule.FIXED_MONTHS,
            "old_student_charge_rule": FeeHead.ChargeRule.FIXED_MONTHS,
            "new_student_charge_months": months,
            "old_student_charge_months": months,
        }

    def snapshot(self, session):
        return {
            "fee_heads": FeeHead.objects.count(),
            "active_fee_structures": FeeStructure.objects.filter(session=session, is_active=True).count(),
            "total_fee_structures": FeeStructure.objects.filter(session=session).count(),
            "official_active_structures": FeeStructure.objects.filter(
                session=session,
                school_class__name__in=OFFICIAL_CLASSES,
                fee_head__name__in=OFFICIAL_HEADS,
                is_active=True,
            ).count(),
            "legacy_active_official_classes": FeeStructure.objects.filter(
                session=session,
                school_class__name__in=OFFICIAL_CLASSES,
                is_active=True,
            ).exclude(fee_head__name__in=OFFICIAL_HEADS).count(),
            "readmission_structures": FeeStructure.objects.filter(
                session=session,
                fee_head__name=READMISSION_HEAD_NAME,
                is_active=True,
            ).count(),
            "com_structures": FeeStructure.objects.filter(session=session, school_class__name__contains="COM").count(),
            "package_students": Student.objects.filter(is_active=True, fee_package_enabled=True).count(),
            "opening_balances": StudentOpeningBalance.objects.filter(session=session).count(),
            "opening_balance_total": StudentOpeningBalance.objects.filter(session=session).aggregate(total=Sum("amount"))[
                "total"
            ]
            or Decimal("0.00"),
            "students_by_section": list(
                Student.objects.filter(is_active=True)
                .values("current_section__name")
                .annotate(count=Count("id"))
                .order_by("current_section__name")
            ),
        }

    def write_report(self, *, mode, session, before, after, planned):
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORT_DIR / "THPSIC_FEE_POLICY_DRYRUN.md"
        if mode == "APPLY":
            path = REPORT_DIR / "THPSIC_FEE_POLICY_APPLY_REPORT.md"

        def student_line(student):
            class_name = student.current_class.name if student.current_class else "-"
            section = student.current_section.name if student.current_section else "-"
            amount = student.effective_fee_package_total
            return f"- SID {student.legacy_sid or '-'} | {student.full_name} | {class_name}-{section} | package {amount}"

        lines = [
            f"# THPSIC Fee Policy {mode}",
            "",
            f"- DB: `{settings.DATABASES['default']['NAME']}`",
            f"- Session: {session.name}",
            "",
            "## Planned Policy",
            "",
            "- Official 2026-27 annual fee sheet is the regular IX-XII source of truth",
            "- Section B/C: zero class fee demand",
            "- Section D: package demand, default Rs 4500",
            "- Existing COM students are package-marked; COM fee structures remain for future regular students",
            "- Direct X/XII: manual package override through student package fields",
            "- Tuition is monthly: IX/X Rs 500, XI/XII Rs 600",
            "- Admission / Reg Fee is charged only to new students in admission month",
            "- Exam Fee is split across AUG/NOV/JAN; Practical Fee in NOV",
            "- X/XII board-related Rs 2000 is collected under Annual Fee in APR; Board Fee stays hidden/inactive",
            "",
            "## Counts Before",
            "",
            f"- Fee heads: {before['fee_heads']}",
            f"- Active fee structures: {before['active_fee_structures']}",
            f"- Total fee structures: {before['total_fee_structures']}",
            f"- Official IX-XII active structures: {before['official_active_structures']}",
            f"- Legacy active rows in official classes: {before['legacy_active_official_classes']}",
            f"- Package-enabled students: {before['package_students']}",
            f"- Opening balances: {before['opening_balances']} / Rs {before['opening_balance_total']}",
            "",
            "## Dry-Run Plan",
            "",
            f"- Package students by Section D/COM: {planned['package_students']}",
            f"- Zero-fee section students: {planned['zero_students']}",
            f"- Existing manual package students: {planned['manual_package_students']}",
            f"- Official IX-XII structure rows to upsert: {planned['official_structure_rows']}",
            f"- Legacy IX-XII rows to deactivate: {planned['official_structures_to_replace']}",
            f"- Active fee heads needing charge-rule fix: {planned['heads_without_charge_rule']}",
            "",
            "## Counts After",
            "",
            f"- Fee heads: {after['fee_heads']}",
            f"- Active fee structures: {after['active_fee_structures']}",
            f"- Total fee structures: {after['total_fee_structures']}",
            f"- Official IX-XII active structures: {after['official_active_structures']}",
            f"- Legacy active rows in official classes: {after['legacy_active_official_classes']}",
            f"- Package-enabled students: {after['package_students']}",
            f"- Opening balances: {after['opening_balances']} / Rs {after['opening_balance_total']}",
            "",
            "## Package Sample",
            "",
            *(student_line(student) for student in planned["package_sample"]),
            "",
            "## Zero-Fee Sample",
            "",
            *(student_line(student) for student in planned["zero_sample"]),
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
