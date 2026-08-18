import os
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Staff

active_staff = Staff.objects.filter(is_active=True).order_by("legacy_emp_code")

# Khatabook verified salary payments (April 2026, May 2026, July 2026)
# Format: {legacy_emp_code: {'staff_name': ..., 'APR': (amt, allowances, date), 'MAY': (amt, allowances, date), 'JUL': (amt, allowances, date)}}
salary_schedule = {
    14: { # ASHOK SINGH (Lecturer)
        "APR": {"amount": Decimal("16000.00"), "basic": Decimal("15000.00"), "allowances": Decimal("1000.00"), "date": "2026-07-02", "remarks": "Salary of April + CL 1000"},
        "MAY": {"amount": Decimal("16000.00"), "basic": Decimal("15000.00"), "allowances": Decimal("1000.00"), "date": "2026-07-02", "remarks": "Salary of May + CL 1000"},
        "JUL": {"amount": Decimal("16000.00"), "basic": Decimal("15000.00"), "allowances": Decimal("1000.00"), "date": "2026-08-17", "remarks": "Salary of July + CL 1000"},
    },
    16: { # KM ANURADHA SINGH (Lecturer)
        "APR": {"amount": Decimal("8000.00"), "basic": Decimal("8000.00"), "allowances": Decimal("0.00"), "date": "2026-08-17", "remarks": "Salary of April"},
        "MAY": {"amount": Decimal("8000.00"), "basic": Decimal("8000.00"), "allowances": Decimal("0.00"), "date": "2026-08-17", "remarks": "Salary of May"},
        "JUL": {"amount": Decimal("8000.00"), "basic": Decimal("8000.00"), "allowances": Decimal("0.00"), "date": "2026-08-17", "remarks": "Salary of July"},
    },
    12: { # HARIKESH YADAV (English)
        "APR": {"amount": Decimal("15467.00"), "basic": Decimal("15467.00"), "allowances": Decimal("0.00"), "date": "2026-07-02", "remarks": "Salary of April"},
        "MAY": {"amount": Decimal("16533.00"), "basic": Decimal("16000.00"), "allowances": Decimal("533.00"), "date": "2026-07-02", "remarks": "Salary of May"},
        "JUL": {"amount": Decimal("14934.00"), "basic": Decimal("14934.00"), "allowances": Decimal("0.00"), "date": "2026-08-17", "remarks": "Salary of July"},
    },
    11: { # JAIPRAKASH PRAJAPATI (Bio & Chem)
        "APR": None, # Unpaid / Joined later
        "MAY": None, # Unpaid / Joined later
        "JUL": {"amount": Decimal("15500.00"), "basic": Decimal("15000.00"), "allowances": Decimal("500.00"), "date": "2026-08-17", "remarks": "Salary of July + 500 CL bonus"},
    },
    17: { # MANOJ KUMAR (Asst Teacher)
        "APR": {"amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "date": "2026-07-02", "remarks": "Salary of April"},
        "MAY": {"amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "date": "2026-07-02", "remarks": "Salary of May"},
        "JUL": {"amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "date": "2026-08-17", "remarks": "Salary of July (Office confirmed)"},
    },
    18: { # SARITA (Peon)
        "APR": {"amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "date": "2026-04-22", "remarks": "Salary of April"},
        "MAY": {"amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "date": "2026-05-27", "remarks": "Salary of May"},
        "JUL": {"amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "date": "2026-07-23", "remarks": "Salary of July"},
    },
    13: { # SATYNARAYAN SINGH (Gate Man)
        "APR": None, # Old gateman was paid, Satyanarayan started July
        "MAY": None,
        "JUL": {"amount": Decimal("5000.00"), "basic": Decimal("5000.00"), "allowances": Decimal("0.00"), "date": "2026-08-17", "remarks": "Salary of July"},
    },
    19: { # VINOD YADAV (Lecturer)
        "APR": {"amount": Decimal("17400.00"), "basic": Decimal("17400.00"), "allowances": Decimal("0.00"), "date": "2026-07-02", "remarks": "Salary of April"},
        "MAY": {"amount": Decimal("19200.00"), "basic": Decimal("18000.00"), "allowances": Decimal("1200.00"), "date": "2026-07-02", "remarks": "Salary of May"},
        "JUL": {"amount": Decimal("18000.00"), "basic": Decimal("18000.00"), "allowances": Decimal("0.00"), "date": "2026-08-17", "remarks": "Salary of July"},
    },
    15: { # AYUSHI SINGH (Computer Operator) - Cash based, office will enter
        "APR": None, "MAY": None, "JUL": None
    },
    2: { # JITENDRA SINGH (Principal) - No entry in Khatabook
        "APR": None, "MAY": None, "JUL": None
    },
    1: { # PRAGATI SINGH (Manager) - Honorary / No salary
        "APR": None, "MAY": None, "JUL": None
    }
}

print("=== THPSIC 11 ACTIVE STAFF SALARY SCHEDULE FROM KHATABOOK ===")
print(f"{'Code':4} | {'Staff Name':22} | {'Designation':22} | {'April 2026':12} | {'May 2026':12} | {'July 2026':12} | {'Total Paid':12}")
print("-" * 105)

total_apr = Decimal("0.00")
total_may = Decimal("0.00")
total_jul = Decimal("0.00")

for s in active_staff:
    code = int(s.legacy_emp_code or 0)
    sched = salary_schedule.get(code, {})
    apr = sched.get("APR")
    may = sched.get("MAY")
    jul = sched.get("JUL")
    
    apr_amt = apr["amount"] if apr else Decimal("0.00")
    may_amt = may["amount"] if may else Decimal("0.00")
    jul_amt = jul["amount"] if jul else Decimal("0.00")
    
    total_apr += apr_amt
    total_may += may_amt
    total_jul += jul_amt
    tot = apr_amt + may_amt + jul_amt
    
    apr_str = f"Rs.{apr_amt:,.0f}" if apr else "-"
    may_str = f"Rs.{may_amt:,.0f}" if may else "-"
    jul_str = f"Rs.{jul_amt:,.0f}" if jul else "-"
    tot_str = f"Rs.{tot:,.0f}" if tot > 0 else "-"
    
    print(f"{code:4} | {s.full_name:22} | {s.designation:22} | {apr_str:12} | {may_str:12} | {jul_str:12} | {tot_str:12}")

print("-" * 105)
print(f"{'TOTAL':4} | {'':22} | {'':22} | Rs.{total_apr:10,.0f} | Rs.{total_may:10,.0f} | Rs.{total_jul:10,.0f} | Rs.{total_apr+total_may+total_jul:10,.0f}")
