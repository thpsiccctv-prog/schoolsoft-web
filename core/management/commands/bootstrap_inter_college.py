from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import AcademicSession, FeeHead, FeeStructure, SchoolClass, SchoolProfile, Section


class Command(BaseCommand):
    help = "Create starter profile, session, classes and fee heads for THPSIC Inter College."

    def handle(self, *args, **options):
        SchoolProfile.objects.update(is_active=False)
        SchoolProfile.objects.update_or_create(
            name="Thakur Harikesh Pratap Singh Intermediate College",
            defaults={
                "address_line1": "Uday, Kushinagar",
                "recognized_upto": "Class XII",
                "medium": "",
                "current_year": "2026-27",
                "is_active": True,
            },
        )

        session, _ = AcademicSession.objects.update_or_create(
            name="2026-27",
            defaults={
                "starts_on": date(2026, 4, 1),
                "ends_on": date(2027, 3, 31),
                "is_active": True,
            },
        )

        class_names = ["VI", "VII", "VIII", "IX", "X", "XI", "XII"]
        fee_heads = [
            ("Admission Fee", "Admission Fee", FeeHead.Frequency.ONE_TIME, False),
            ("Annual Fee", "Annual Fee", FeeHead.Frequency.ANNUAL, False),
            ("Tuition Fee", "Fees Amt#", FeeHead.Frequency.MONTHLY, False),
            ("Exam Fee", "Exam Fee", FeeHead.Frequency.ANNUAL, False),
            ("Transport", "Transport", FeeHead.Frequency.MONTHLY, True),
            ("Late Fee", "Late Fee", FeeHead.Frequency.OPTIONAL, False),
            ("Concession", "Concession", FeeHead.Frequency.OPTIONAL, False),
        ]

        heads = []
        for name, legacy_column, frequency, is_transport in fee_heads:
            head, _ = FeeHead.objects.update_or_create(
                name=name,
                defaults={
                    "legacy_column": legacy_column,
                    "frequency": frequency,
                    "is_transport": is_transport,
                },
            )
            heads.append(head)

        for order, class_name in enumerate(class_names, start=6):
            school_class, _ = SchoolClass.objects.update_or_create(
                name=class_name,
                defaults={"display_order": order},
            )
            for section_name in ["A", "B"]:
                Section.objects.get_or_create(school_class=school_class, name=section_name)

            for head in heads:
                if head.name in {"Late Fee", "Concession"}:
                    continue
                FeeStructure.objects.get_or_create(
                    session=session,
                    school_class=school_class,
                    fee_head=head,
                    defaults={"amount": Decimal("0.00")},
                )

        self.stdout.write(self.style.SUCCESS("THPSIC Inter College starter data is ready."))
