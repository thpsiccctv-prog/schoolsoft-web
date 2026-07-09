"""Seed the 4 default student houses (Red/Blue/Green/Yellow).

Usage:
    python manage.py seed_houses

Safe to run multiple times - skips houses that already exist by name. Rename
or recolor them any time afterwards via Django admin (Core -> Houses); this
command will not touch existing rows.
"""
from django.core.management.base import BaseCommand

from core.models import House


HOUSES = [
    # (name, color_code, display_order)
    ("Red House", "#DC2626", 1),
    ("Blue House", "#2563EB", 2),
    ("Green House", "#16A34A", 3),
    ("Yellow House", "#CA8A04", 4),
]


class Command(BaseCommand):
    help = "Seed the 4 default student houses (Red/Blue/Green/Yellow)."

    def handle(self, *args, **options):
        created_count = 0
        for name, color_code, order in HOUSES:
            _, created = House.objects.get_or_create(
                name=name,
                defaults={"color_code": color_code, "display_order": order},
            )
            if created:
                created_count += 1
                self.stdout.write(f"  + House: {name} ({color_code})")

        self.stdout.write(self.style.SUCCESS(f"Done: {created_count} houses created."))
