import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from core.models import Staff

class Command(BaseCommand):
    help = 'Safely sync April 2026+ Staff from legacy Access DB (SubGroup.csv)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run the sync without saving to the database',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING("Running in DRY-RUN mode. No data will be saved."))

        csv_path = r'D:\english medium\migration_audit\exports\SubGroup.csv'
        created_count = 0
        updated_count = 0

        # We determined that CODE == '9' corresponds to the "SALARY" group in MGROUP
        SALARY_GROUP_CODE = '9'

        try:
            with open(csv_path, mode='r', encoding='utf-8-sig', errors='ignore') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['CODE'] != SALARY_GROUP_CODE:
                        continue
                    
                    full_name = row.get('NAME', '').strip()
                    if not full_name:
                        continue

                    phone = row.get('PHONE', '').strip()[:50]
                    address = " ".join([row.get(f'ADD{i}', '').strip() for i in range(1, 4)]).strip()

                    staff_defaults = {
                        'phone': phone,
                        'address': address,
                        'is_active': True,
                    }

                    if not dry_run:
                        staff, created = Staff.objects.update_or_create(
                            full_name=full_name,
                            defaults=staff_defaults
                        )
                        if created:
                            created_count += 1
                        else:
                            updated_count += 1
                    else:
                        try:
                            Staff.objects.get(full_name=full_name)
                            updated_count += 1
                        except Staff.DoesNotExist:
                            created_count += 1
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"CSV file not found: {csv_path}"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Staff Sync Summary:\n"
            f"Created: {created_count}\n"
            f"Updated: {updated_count}\n"
            f"{'(DRY RUN - no data saved)' if dry_run else '(Data saved to database)'}"
        ))
