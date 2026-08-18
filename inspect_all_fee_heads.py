import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeStructure, FeeHead, SchoolClass, AcademicSession

session = AcademicSession.objects.filter(is_active=True).first()

print(f"=== ALL FEE HEADS IN DATABASE ===")
for fh in FeeHead.objects.all():
    print(f"ID: {fh.id:2} | Name: {fh.name:25} | Applies: {fh.applies_to:5} | New: {fh.new_student_charge_rule} ({fh.new_student_charge_months}) | Old: {fh.old_student_charge_rule} ({fh.old_student_charge_months})")

print(f"\n=== ALL CLASSES ===")
for sc in SchoolClass.objects.all().order_by("display_order", "name"):
    print(f"Class ID {sc.id:2}: {sc.name}")
    structures = FeeStructure.objects.filter(school_class=sc, session=session).select_related('fee_head')
    for fs in structures:
        print(f"   Head: {fs.fee_head.name:25} | Amount: Rs.{fs.amount:6} | Applies: {fs.fee_head.applies_to}")
