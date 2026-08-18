import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeStructure, FeeHead, SchoolClass, AcademicSession

session = AcademicSession.objects.filter(is_active=True).first()
cls_9 = SchoolClass.objects.filter(name__icontains='IX').first()

print(f"Fee Structures for Class {cls_9}:")
for fs in FeeStructure.objects.filter(school_class=cls_9, session=session).select_related('fee_head'):
    print(f"  Head: {fs.fee_head.name:25} | Amount: Rs. {fs.amount:6} | Months: {fs.charge_months} | Rule: {fs.charge_rule} | Applies To: {fs.applies_to}")
