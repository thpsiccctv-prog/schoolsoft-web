from decimal import Decimal
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from core.models import AccountGroup, LedgerAccount


class Command(BaseCommand):
    help = "Safely sets the opening balance for Cash in Hand ledger account without creating vouchers"

    def add_arguments(self, parser):
        parser.add_argument(
            "--amount",
            type=float,
            default=16000.00,
            help="Opening balance amount (default: 16000)",
        )
        parser.add_argument(
            "--date",
            type=str,
            default="2026-04-01",
            help="Opening balance date YYYY-MM-DD (default: 2026-04-01)",
        )
        parser.add_argument(
            "--confirm",
            type=str,
            help="Must be 'THPSIC'",
        )

    def handle(self, *args, **options):
        confirm = options.get("confirm")
        if confirm != "THPSIC":
            raise CommandError("Please provide '--confirm THPSIC' to apply opening balance.")

        amount = Decimal(str(options.get("amount", 16000.00)))
        op_date = date.fromisoformat(options.get("date", "2026-04-01"))

        # Find or create Cash & Bank group
        group, _ = AccountGroup.objects.get_or_create(
            name="Cash & Bank",
            defaults={"group_type": AccountGroup.GroupType.ASSET, "display_order": 1},
        )

        # Find or create Cash in Hand ledger
        cash_ledger, created = LedgerAccount.objects.get_or_create(
            name="Cash in Hand",
            defaults={
                "group": group,
                "opening_balance": amount,
                "opening_balance_date": op_date,
                "is_cash_or_bank": True,
                "is_active": True,
            },
        )

        if not created:
            cash_ledger.opening_balance = amount
            cash_ledger.opening_balance_date = op_date
            cash_ledger.is_cash_or_bank = True
            cash_ledger.save(update_fields=["opening_balance", "opening_balance_date", "is_cash_or_bank"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully set Cash in Hand Opening Balance: ₹{cash_ledger.opening_balance:,.2f} as of {cash_ledger.opening_balance_date}"
            )
        )
