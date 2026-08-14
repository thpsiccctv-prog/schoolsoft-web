import csv
import os
import sys
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings

# Increase CSV field limit to handle large/malformed fields
csv.field_size_limit(2147483647)

class Command(BaseCommand):
    help = 'Dry run migration for THPSIC Inter College from Access DB CSVs'

    def add_arguments(self, parser):
        parser.add_argument('--addmission_csv', type=str, 
                            default=r'E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\ADDMISSION.csv')
        parser.add_argument('--output_dir', type=str, 
                            default=r'E:\THPSIC-INTER-COLLEGE\05-reports')

    def handle(self, *args, **options):
        addmission_csv = options['addmission_csv']
        output_dir = options['output_dir']

        if not os.path.exists(addmission_csv):
            self.stdout.write(self.style.ERROR(f"File not found: {addmission_csv}"))
            sys.exit(1)

        output_file = os.path.join(output_dir, 'ADDMISSION_ACTIVE_REVIEW.csv')

        self.stdout.write(f"Starting dry run using {addmission_csv}")

        total_rows = 0
        active_count = 0
        left_count = 0
        missing_mobile = 0
        missing_dob = 0
        missing_father = 0

        # Columns for active review export
        export_columns = [
            'sid', 'admno', 'sname', 'fname', 'sclass', 'section', 
            'v_date', 'tc', 'TC_ISSUE', 'TC_NO', 'TC_DATE', 'AED', 'pmobile'
        ]
        
        active_students_data = []

        # Read huge CSV
        # Because the file might have null bytes or bad encoding, use encoding that won't crash
        with open(addmission_csv, mode='r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                total_rows += 1
                
                # Normalize values
                sid = row.get('sid', '').strip()
                admno = row.get('admno', '').strip()
                sname = row.get('sname', '').strip()
                fname = row.get('fname', '').strip()
                sclass = row.get('sclass', '').strip()
                section = row.get('section', '').strip()
                v_date = row.get('v_date', '').strip()
                tc_val = row.get('tc', '').strip()
                tc_issue = row.get('TC_ISSUE', '').strip().upper()
                tc_no = row.get('TC_NO', '').strip()
                tc_date = row.get('TC_DATE', '').strip()
                aed = row.get('AED', '').strip()
                pmobile = row.get('pmobile', '').strip()
                dob = row.get('dobfig', '').strip()

                is_active = (tc_issue == 'NO')

                if is_active:
                    active_count += 1
                    active_students_data.append({
                        'sid': sid,
                        'admno': admno,
                        'sname': sname,
                        'fname': fname,
                        'sclass': sclass,
                        'section': section,
                        'v_date': v_date,
                        'tc': tc_val,
                        'TC_ISSUE': tc_issue,
                        'TC_NO': tc_no,
                        'TC_DATE': tc_date,
                        'AED': aed,
                        'pmobile': pmobile
                    })

                    if not pmobile:
                        missing_mobile += 1
                    if not dob:
                        missing_dob += 1
                    if not fname:
                        missing_father += 1
                else:
                    left_count += 1

        # Write out active review
        with open(output_file, mode='w', newline='', encoding='utf-8') as out_f:
            writer = csv.DictWriter(out_f, fieldnames=export_columns)
            writer.writeheader()
            writer.writerows(active_students_data)

        self.stdout.write(self.style.SUCCESS(f"\n--- DRY RUN SUMMARY ---"))
        self.stdout.write(f"Total ADDMISSION rows read: {total_rows}")
        self.stdout.write(f"Active students (TC_ISSUE=NO): {active_count}")
        self.stdout.write(f"Left/Inactive students (TC_ISSUE=YES): {left_count}")
        self.stdout.write(f"\nData Quality in Active Students:")
        self.stdout.write(f"- Missing mobile: {missing_mobile}")
        self.stdout.write(f"- Missing DOB: {missing_dob}")
        self.stdout.write(f"- Missing Father name: {missing_father}")
        
        self.stdout.write(self.style.SUCCESS(f"\nActive review exported to: {output_file}"))
        self.stdout.write(self.style.WARNING(f"\nNo live data was modified. This was purely a dry-run read."))
