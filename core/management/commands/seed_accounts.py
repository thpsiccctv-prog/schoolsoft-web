"""Seed default account groups and ledger accounts for Phase 1 MVP.

Usage:
    python manage.py seed_accounts

Safe to run multiple times — skips existing groups/ledgers by name.
"""
from django.core.management.base import BaseCommand

from core.models import AccountGroup, LedgerAccount


GROUPS = [
    ("Cash & Bank", "asset", 1),
    ("Expense", "expense", 2),
    ("Income", "income", 3),
    ("Advance Given", "asset", 4),
    ("Loan & Liability", "liability", 5),
]

LEDGERS = [
    # (name, group_name, is_cash_or_bank, display_order)
    ("Cash in Hand", "Cash & Bank", True, 1),
    ("Bank Account", "Cash & Bank", True, 2),
    ("Diesel for Bus", "Expense", False, 10),
    ("Electricity", "Expense", False, 11),
    ("Repair & Maintenance", "Expense", False, 12),
    ("Stationery", "Expense", False, 13),
    ("Sweeper", "Expense", False, 14),
    ("Driver Payment", "Expense", False, 15),
    ("Misc Expense", "Expense", False, 20),
    ("Staff Advance", "Advance Given", False, 30),
    ("Manager Advance", "Advance Given", False, 31),
    ("Other Income", "Income", False, 40),
]


class Command(BaseCommand):
    help = "Seed default account groups and ledger accounts."

    def handle(self, *args, **options):
        groups_created = 0
        for name, group_type, order in GROUPS:
            _, created = AccountGroup.objects.get_or_create(
                name=name,
                defaults={"group_type": group_type, "display_order": order},
            )
            if created:
                groups_created += 1
                self.stdout.write(f"  + Group: {name}")

        ledgers_created = 0
        for name, group_name, is_cb, order in LEDGERS:
            group = AccountGroup.objects.get(name=group_name)
            _, created = LedgerAccount.objects.get_or_create(
                name=name,
                defaults={
                    "group": group,
                    "is_cash_or_bank": is_cb,
                    "display_order": order,
                },
            )
            if created:
                ledgers_created += 1
                self.stdout.write(f"  + Ledger: {name} ({group_name})")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {groups_created} groups, {ledgers_created} ledgers created."
            )
        )
