import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeReceipt

for sec in ['B', 'C']:
    st_list = Student.objects.filter(is_active=True, current_section__name=sec)
    st_ids = [s.id for s in st_list]
    rcps = FeeReceipt.objects.filter(student_id__in=st_ids, is_cancelled=False)
    print(f"\nSection {sec}: Total Active Students = {st_list.count()}")
    print(f"  Total Receipts in System for Section {sec} students = {rcps.count()}")
    print(f"  Total Amount Paid in Receipts = Rs. {sum(r.received_amount for r in rcps)}")
    print("  Sample 5 students with their receipts:")
    for s in st_list[:5]:
        s_rcps = rcps.filter(student=s)
        rcp_str = ", ".join([f"{r.receipt_no}: Rs.{r.received_amount}" for r in s_rcps])
        print(f"    SID {s.legacy_sid:5} | {s.full_name:20} | Class {str(s.current_class):10} | Receipts: {rcp_str or 'None'}")
