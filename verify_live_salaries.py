import os
from decimal import Decimal
from django.db.models import Sum

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Staff, SalaryPayment

payments = SalaryPayment.objects.filter(is_cancelled=False).select_related('staff').order_by('slip_no')

print(f"=== LIVE SALARY REGISTER VERIFICATION ({payments.count()} VOUCHERS) ===")
print(f"{'Slip No':15} | {'Payment Date':12} | {'Salary Month':12} | {'Staff Name':22} | {'Basic':10} | {'Allow/CL':10} | {'Amount Paid':12}")
print("-" * 115)

for p in payments:
    print(f"{p.slip_no:15} | {p.payment_date.strftime('%d-%m-%Y'):12} | {p.pay_month.strftime('%b %Y'):12} | {p.staff.full_name:22} | Rs.{p.basic_pay:8,.2f} | Rs.{p.other_allowances:8,.2f} | Rs.{p.amount_paid:10,.2f}")

print("-" * 115)
total_amt = payments.aggregate(t=Sum('amount_paid'))['t'] or Decimal("0.00")
print(f"GRAND TOTAL SALARIES PAID: Rs. {total_amt:,.2f}")

print("\n--- Month-wise Totals ---")
for m_str, m_date in [("April 2026", "2026-04-01"), ("May 2026", "2026-05-01"), ("July 2026", "2026-07-01")]:
    m_tot = payments.filter(pay_month=m_date).aggregate(t=Sum('amount_paid'))['t'] or Decimal("0.00")
    m_cnt = payments.filter(pay_month=m_date).count()
    print(f"  {m_str:12}: {m_cnt:2} vouchers | Rs. {m_tot:10,.2f}")
