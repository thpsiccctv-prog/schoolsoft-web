import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeReceipt, AcademicSession
from core.fee_engine import calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()

print("Testing calculate_student_due with actual receipts counted:")

# Let's inspect test cases
for sid in ['9786', '9003', '9008', '9112', '9084', '9148']:
    s = Student.objects.filter(legacy_sid=sid).first()
    if not s: continue
    
    # Calculate due
    res = calculate_student_due(student=s, session=session, through_month='AUG')
    print(f"\nStudent SID {sid}: {s.full_name} ({s.current_class} {s.current_section})")
    print(f"  Scheduled Fee: Rs. {res.scheduled_fee_demand}")
    print(f"  Opening Balance: Rs. {res.opening_balance_amount}")
    print(f"  Gross Demand: Rs. {res.gross_demand}")
    print(f"  Received Amount (Paid): Rs. {res.received_amount}")
    print(f"  Concession: Rs. {res.concession_amount}")
    print(f"  Final Due Amount: Rs. {res.due_amount}")
    print(f"  Credit Amount: Rs. {res.credit_amount}")
