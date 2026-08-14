import csv
import os
import sys
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from core.models import Student, SchoolClass, Section


class Command(BaseCommand):
    help = 'Import THPSIC Inter College students from preview CSV'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv', type=str,
            default=r'E:\THPSIC-INTER-COLLEGE\05-reports\ADDMISSION_IMPORT_PREVIEW.csv',
            help='Path to the preview CSV file'
        )
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually apply the changes to the database (default is dry-run)'
        )
        parser.add_argument(
            '--confirm', type=str,
            help='Confirmation string (must be "THPSIC") when using --apply'
        )
        parser.add_argument(
            '--report-out', type=str,
            default=r'E:\THPSIC-INTER-COLLEGE\05-reports\STUDENT_IMPORT_SCRIPT_DRYRUN_RESULT.md',
            help='Path to write the summary report'
        )

    def parse_date(self, date_str):
        if not date_str:
            return None
        
        date_str = date_str.split(' ')[0].strip()
        
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            try:
                return datetime.strptime(date_str, '%d/%m/%Y').date()
            except ValueError:
                return None

    def handle(self, *args, **options):
        csv_file = options['csv']
        apply_changes = options['apply']
        confirm_str = options['confirm']
        report_out = options['report_out']

        if apply_changes and confirm_str != 'THPSIC':
            raise CommandError("You must provide '--confirm THPSIC' to use the --apply flag.")

        if not os.path.exists(csv_file):
            self.stdout.write(self.style.ERROR(f"CSV file not found: {csv_file}"))
            sys.exit(1)

        db_path = settings.DATABASES['default'].get('NAME', 'Unknown DB Path')
        self.stdout.write(f"Target Database: {db_path}")

        if Student.objects.exists():
            raise CommandError("The Student table is not empty. Aborting to prevent mixing data.")

        stats = {
            'students_to_import': 0,
            'classes_created': 0,
            'sections_created': 0,
            'duplicate_sid': 0,
            'missing_phone': 0,
            'invalid_dates': 0,
            'invalid_blood_group': 0,
        }
        
        class_cache = {}
        section_cache = {}

        self.stdout.write(f"Starting import from {csv_file}")
        self.stdout.write(f"Mode: {'APPLY' if apply_changes else 'DRY RUN'}")

        bg_mapping = {
            'A+': 'A+', 'A-': 'A-', 'B+': 'B+', 'B-': 'B-', 
            'O+': 'O+', 'O-': 'O-', 'AB+': 'AB+', 'AB-': 'AB-',
            'AB': 'AB+',
        }

        try:
            with transaction.atomic():
                with open(csv_file, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    
                    for row in reader:
                        sid = row.get('sid', '').strip()
                        if not sid: continue

                        if Student.objects.filter(legacy_sid=sid).exists():
                            stats['duplicate_sid'] += 1
                            self.stdout.write(self.style.WARNING(f"Duplicate sid found: {sid}"))
                            continue
                            
                        class_name = row.get('class_normalized', '').strip()
                        section_name = row.get('section', '').strip()
                        
                        if class_name not in class_cache:
                            # Check XII before XI before X to avoid prefix collision
                            _om = {"VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}
                            if class_name in _om:
                                order = _om[class_name]
                            elif class_name.startswith("XII"):
                                order = 12
                            elif class_name.startswith("XI"):
                                order = 11
                            else:
                                order = 0

                            c_obj, created = SchoolClass.objects.get_or_create(
                                name=class_name,
                                defaults={"display_order": order}
                            )
                            if created:
                                stats['classes_created'] += 1
                            class_cache[class_name] = c_obj
                        school_class = class_cache[class_name]

                        if section_name:
                            sec_key = f"{class_name}-{section_name}"
                            if sec_key not in section_cache:
                                s_obj, created = Section.objects.get_or_create(
                                    school_class=school_class,
                                    name=section_name
                                )
                                if created:
                                    stats['sections_created'] += 1
                                section_cache[sec_key] = s_obj
                            section = section_cache[sec_key]
                        else:
                            section = None
                            
                        dob = self.parse_date(row.get('dob'))
                        v_date = self.parse_date(row.get('admission_date'))
                        
                        if row.get('dob') and not dob:
                            stats['invalid_dates'] += 1
                        if row.get('admission_date') and not v_date:
                            stats['invalid_dates'] += 1
                        
                        mobile_primary = row.get('mobile_primary', '').strip()
                        if not mobile_primary:
                            stats['missing_phone'] += 1
                            
                        gender_val = row.get('gender', '').strip().upper()
                        gender_code = 'U'
                        if gender_val.startswith('M'): gender_code = 'M'
                        elif gender_val.startswith('F'): gender_code = 'F'

                        raw_bg = row.get('blood_group', '').strip().upper()
                        bg_mapped = ''
                        if raw_bg:
                            if raw_bg in bg_mapping:
                                bg_mapped = bg_mapping[raw_bg]
                            else:
                                stats['invalid_blood_group'] += 1

                        roll_no_val = row.get('roll_no', '').strip()
                        roll_no = int(roll_no_val) if roll_no_val.isdigit() else None

                        Student.objects.create(
                            legacy_sid=sid,
                            admission_no=sid,
                            registration_no=sid,
                            full_name=row.get('full_name', ''),
                            father_name=row.get('father_name', ''),
                            mother_name=row.get('mother_name', ''),
                            gender=gender_code,
                            date_of_birth=dob,
                            aadhaar_no=row.get('aadhaar_no', ''),
                            category=row.get('category', ''),
                            religion=row.get('religion', ''),
                            email=row.get('email', ''),
                            mobile_primary=mobile_primary,
                            mobile_secondary=row.get('mobile_secondary', ''),
                            blood_group=bg_mapped,
                            address_permanent=row.get('address_permanent', ''),
                            pin_code=row.get('pin_code', ''),
                            previous_school_name=row.get('previous_school', ''),
                            previous_board_name=row.get('board', ''),
                            previous_passing_year=row.get('pass_year', ''),
                            current_class=school_class,
                            current_section=section,
                            admission_date=v_date,
                            roll_no=roll_no,
                            is_active=True,
                        )
                        stats['students_to_import'] += 1

                if not apply_changes:
                    raise Exception("DRY_RUN_ROLLBACK")

        except Exception as e:
            if str(e) == "DRY_RUN_ROLLBACK":
                self.stdout.write(self.style.SUCCESS("\n--- Dry Run Complete. Rolled back successfully. ---"))
            else:
                raise e
        else:
            self.stdout.write(self.style.SUCCESS("\n--- Live Import Complete. ---"))

        import_ready = "YES" if (stats['duplicate_sid'] == 0) else "NO (Duplicates found)"

        report_content = f"""# THPSIC Student Import Dry-Run Report

## Summary
- **Mode**: {'Live' if apply_changes else 'Dry-Run'}
- **Source**: `{csv_file}`
- **Target DB**: `{db_path}`

## Counts
- **Students to Import**: {stats['students_to_import']}
- **Classes Created**: {stats['classes_created']}
- **Sections Created**: {stats['sections_created']}
- **Duplicate sid/admission_no**: {stats['duplicate_sid']}
- **Missing Phone**: {stats['missing_phone']}
- **Invalid DOB/Date**: {stats['invalid_dates']}
- **Invalid Blood Group**: {stats['invalid_blood_group']}

## Status
- **Import Ready**: **{import_ready}**
"""
        with open(report_out, 'w', encoding='utf-8') as rf:
            rf.write(report_content)
            
        self.stdout.write(f"Report written to: {report_out}")
        self.stdout.write("Done.")
