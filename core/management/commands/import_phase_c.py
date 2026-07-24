import json
from decimal import Decimal
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import (
    AcademicSession, SchoolClass, FeeHead, FeeStructure,
    TransportRoute, StudentTransport, Student, StudentOpeningBalance
)

class Command(BaseCommand):
    help = 'Import Phase C Fee Structures, Transport, and Opening Balances'

    def handle(self, *args, **options):
        with open('E:/THPSIC SCHOOL/phase_c_import_payload.json', 'r', encoding='utf-8') as f:
            payload = json.load(f)

        session = AcademicSession.objects.get(name='2026-27')

        with transaction.atomic():
            # 1. Update/Create FeeHeads
            for db_head_name, config in payload['head_configs'].items():
                head, created = FeeHead.objects.get_or_create(name=db_head_name)
                head.frequency = config['frequency']
                head.applies_to = config['applies_to']
                head.new_student_charge_rule = config['new_rule']
                head.new_student_charge_months = config['new_months']
                head.old_student_charge_rule = config['old_rule']
                head.old_student_charge_months = config['old_months']
                head.save()

            # 2. Deactivate stale legacy structures for covered classes
            covered_classes = payload['covered_classes']
            FeeStructure.objects.filter(
                session=session,
                school_class__name__in=covered_classes
            ).update(is_active=False)

            # 3. Create or update the target structures
            for target in payload['targets']:
                c = SchoolClass.objects.get(name=target['class_name'])
                h = FeeHead.objects.get(name=target['db_head'])
                
                struct, created = FeeStructure.objects.update_or_create(
                    session=session,
                    school_class=c,
                    fee_head=h,
                    defaults={
                        'amount': Decimal(target['amount']),
                        'is_active': True,
                        'source': 'final_sheet',
                        'source_reference': f'Phase C Import'
                    }
                )

            # 4. Create/update StudentTransport rows
            for transport_row in payload['transport_rows']:
                student = Student.objects.get(legacy_sid=transport_row['sid'])
                route = TransportRoute.objects.get(name=transport_row['route_name'])
                
                StudentTransport.objects.update_or_create(
                    student=student,
                    session=session,
                    defaults={
                        'route': route,
                        'monthly_amount': Decimal(transport_row['monthly_amount']) if transport_row.get('monthly_amount') is not None else None,
                        'start_month': transport_row['start_month'],
                        'end_month': transport_row['end_month'],
                        'billing_confirmed': True,
                        'note': transport_row['notes'] or ''
                    }
                )

            # 5. Create Anushka Opening Balance (SID 2352)
            anushka = Student.objects.get(legacy_sid=2352)
            StudentOpeningBalance.objects.update_or_create(
                student=anushka,
                session=session,
                defaults={
                    'amount': Decimal('2750.00'),
                    'as_of_date': date(2026, 4, 1),
                    'source_reference': 'SF-1000',
                    'note': 'Phase C Import'
                }
            )

            self.stdout.write(self.style.SUCCESS('Successfully imported Phase C data.'))
