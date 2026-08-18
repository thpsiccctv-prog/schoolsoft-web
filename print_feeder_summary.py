import os
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import FeederSchool

print("=" * 90)
print(f"{'Attached School Name':30} | {'Students':8} | {'Total Demand':14} | {'Total Paid':14} | {'Balance Due':14}")
print("=" * 90)

total_stu = 0
total_dem = Decimal("0.00")
total_rec = Decimal("0.00")
total_bal = Decimal("0.00")

for s in FeederSchool.objects.all():
    stu = s.total_enrolled_students
    dem = s.total_demand
    rec = s.total_received
    bal = s.balance_due
    total_stu += stu
    total_dem += dem
    total_rec += rec
    total_bal += bal
    print(f"{s.name:30} | {stu:8} | Rs.{dem:11,.2f} | Rs.{rec:11,.2f} | Rs.{bal:11,.2f}")

print("=" * 90)
print(f"{'GRAND TOTAL':30} | {total_stu:8} | Rs.{total_dem:11,.2f} | Rs.{total_rec:11,.2f} | Rs.{total_bal:11,.2f}")
print("=" * 90)
