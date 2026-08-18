import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student, FeeStructure, FeeHead, SchoolClass, AcademicSession
from core.fee_engine import calculate_student_due

session = AcademicSession.objects.filter(is_active=True).first()

# Inspect FeeHead ID 16 or Name 'Admission / Reg Fee'
fh_reg = FeeHead.objects.filter(name__icontains='Admission / Reg').first()
print(f"FeeHead: {fh_reg.id} | {fh_reg.name} | Current applies_to: {fh_reg.applies_to}")

# Let's clean up duplicate heads in Class IX / XI structures if any:
# In Class IX, there was both 'Admission Fee' (1000), 'Admission / Reg Fee' (2000), and 'Re-admission Fee' (1000).
# Let's see which structures exist for Class IX and Class XI:
for cname in ['IX', 'XI (BIO)', 'XI (MATHS)', 'XI (ART)', 'XI (COM)']:
    sc = SchoolClass.objects.filter(name=cname).first()
    if not sc: continue
    print(f"\nStructures for {sc}:")
    for fs in FeeStructure.objects.filter(school_class=sc, session=session).select_related('fee_head'):
        print(f"  ID {fs.id}: {fs.fee_head.name} | Rs.{fs.amount} | Applies: {fs.fee_head.applies_to} | Active: {fs.is_active}")
