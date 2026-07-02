from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import AcademicSession, FeeHead, FeeStructure, SchoolClass, Section


class Command(BaseCommand):
    help = "Create starter session, classes, sections, and fee heads for the phase-1 prototype."

    def handle(self, *args, **options):
        session, _ = AcademicSession.objects.get_or_create(
            name="2026-27",
            defaults={
                "starts_on": date(2026, 4, 1),
                "ends_on": date(2027, 3, 31),
                "is_active": True,
            },
        )

        class_names = [
            "Nursery",
            "LKG",
            "UKG",
            "I",
            "II",
            "III",
            "IV",
            "V",
            "VI",
            "VII",
            "VIII",
            "IX",
            "X",
            "XI",
            "XII",
        ]

        classes = []
        for order, class_name in enumerate(class_names, start=1):
            school_class, _ = SchoolClass.objects.get_or_create(
                name=class_name,
                defaults={"display_order": order},
            )
            classes.append(school_class)

            for section_name in ["A", "B"]:
                Section.objects.get_or_create(school_class=school_class, name=section_name)

        fee_heads = [
            ("Admission Fee", "Admission Fee", FeeHead.Frequency.ONE_TIME, False),
            ("Annual Fee", "Annual Fee", FeeHead.Frequency.ANNUAL, False),
            ("Tuition Fee", "Fees Amt#", FeeHead.Frequency.MONTHLY, False),
            ("Exam Fee", "Exam Fee", FeeHead.Frequency.ANNUAL, False),
            ("Transport", "Transport", FeeHead.Frequency.MONTHLY, True),
            ("Late Fee", "Late Fee", FeeHead.Frequency.OPTIONAL, False),
            ("Concession", "Concession", FeeHead.Frequency.OPTIONAL, False),
        ]

        created_heads = []
        for name, legacy_column, frequency, is_transport in fee_heads:
            fee_head, _ = FeeHead.objects.get_or_create(
                name=name,
                defaults={
                    "legacy_column": legacy_column,
                    "frequency": frequency,
                    "is_transport": is_transport,
                },
            )
            created_heads.append(fee_head)

        for school_class in classes:
            for fee_head in created_heads:
                if fee_head.name in {"Late Fee", "Concession"}:
                    continue

                FeeStructure.objects.get_or_create(
                    session=session,
                    school_class=school_class,
                    fee_head=fee_head,
                    defaults={"amount": Decimal("0.00")},
                )

        self.stdout.write(self.style.SUCCESS("Phase-1 bootstrap data is ready."))
