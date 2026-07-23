import os
import sys
from decimal import Decimal
from datetime import date

# Set up Django environment
sys.path.insert(0, os.getcwd())
# Ensure we run against the DB path provided by SCHOOLSOFT_SQLITE_PATH
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'schoolsoft.settings')
import django
django.setup()

from core.models import Student, StudentOpeningBalance, AcademicSession
from django.utils import timezone

def main():
    # Ensure active session exists
    session = AcademicSession.objects.filter(is_active=True).first()
    if not session:
        print("ERROR: No active session found.")
        return

    balances_to_import = [
        {"sid": 2518, "amount": "6000.00", "source": "2026-27/SF-82"},
        {"sid": 2116, "amount": "50.00", "source": "2026-27/SF-2"},
        {"sid": 2117, "amount": "700.00", "source": "2026-27/SF-79"},
        {"sid": 2583, "amount": "600.00", "source": "2026-27/SF-85"},
        {"sid": 2233, "amount": "1900.00", "source": "2026-27/SF-106"},
        {"sid": 2589, "amount": "9000.00", "source": "2026-27/SF-35"},
        {"sid": 2006, "amount": "800.00", "source": "2026-27/SF-52"},
        {"sid": 2554, "amount": "4500.00", "source": "2026-27/SF-16"},
        {"sid": 2582, "amount": "13000.00", "source": "2026-27/SF-93"},
        {"sid": 2567, "amount": "4700.00", "source": "2026-27/SF-64"},
        {"sid": 2555, "amount": "5550.00", "source": "2026-27/SF-17"},
        {"sid": 104,  "amount": "1900.00", "source": "2026-27/SF-1"},
    ]

    total_amount = Decimal("0.00")
    success_count = 0

    as_of_date = session.starts_on if session.starts_on else timezone.localdate()

    for data in balances_to_import:
        student = Student.objects.filter(legacy_sid=data["sid"], is_active=True).first()
        if not student:
            print(f"ERROR: Active student with SID {data['sid']} not found.")
            continue
        
        amount = Decimal(data["amount"])
        
        # Create or update StudentOpeningBalance
        balance, created = StudentOpeningBalance.objects.update_or_create(
            student=student,
            session=session,
            defaults={
                "amount": amount,
                "source_reference": data["source"],
                "as_of_date": as_of_date
            }
        )
        total_amount += amount
        success_count += 1
        
        status = "Created" if created else "Updated"
        print(f"{status} balance for {student.full_name} (SID {student.legacy_sid}): Rs. {amount} (Source: {data['source']})")

    print(f"\nSuccessfully imported {success_count} opening balances.")
    print(f"Total Amount: Rs. {total_amount}")

if __name__ == "__main__":
    main()
