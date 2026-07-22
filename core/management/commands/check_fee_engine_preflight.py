from django.core.management.base import BaseCommand, CommandError

from core.models import FeeReceipt


class Command(BaseCommand):
    help = "Block new fee-engine enablement when deprecated previous-due receipt fields contain data."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")

    def handle(self, *args, **options):
        database = options["database"]
        receipts = FeeReceipt.objects.using(database)
        total = receipts.count()
        previous_due_count = receipts.exclude(previous_due_amount=0).count()
        carried_forward_count = receipts.filter(carried_forward=True).count()

        if previous_due_count or carried_forward_count:
            raise CommandError(
                "Fee-engine preflight failed: "
                f"receipts={total}, previous_due_amount_nonzero={previous_due_count}, "
                f"carried_forward_true={carried_forward_count}. Manual reconciliation is required."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Fee-engine preflight PASS: "
                f"receipts={total}, previous_due_amount_nonzero=0, carried_forward_true=0."
            )
        )
