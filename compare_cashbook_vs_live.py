import os
import csv
from decimal import Decimal
from collections import defaultdict

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import FeeReceipt, Student

# Live FeeReceipts in DB
live_receipts = FeeReceipt.objects.filter(is_cancelled=False).select_related('student')
live_total = sum(r.received_amount for r in live_receipts)
print(f"=== LIVE DJANGO SYSTEM RECEIPTS ===")
print(f"  Total Non-Cancelled Receipts: {live_receipts.count()}")
print(f"  Total Amount Collected: Rs. {live_total:,.2f}")

# Read legacy StuFee.csv from comp35 (which corresponds to old cash book SCCR 1 to 682)
csv.field_size_limit(2147483647)
stufee_35 = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\StuFee.csv"

comp35_receipts = []
comp35_total = Decimal("0.00")
with open(stufee_35, encoding="utf-8-sig", errors="ignore") as f:
    for r in csv.DictReader(f):
        try:
            rcp = int(float(r.get('rcpno') or 0))
            paid = Decimal(str(r.get('paid') or '0').strip())
            sid = str(r.get('sid') or '').strip()
            sname = r.get('sname', '')
            v_date = r.get('v_date', '')[:10]
            comp35_receipts.append({
                'rcpno': rcp,
                'sid': sid,
                'name': sname,
                'date': v_date,
                'paid': paid,
                'due': Decimal(str(r.get('due') or '0').strip()),
            })
            comp35_total += paid
        except Exception as e:
            pass

print(f"\n=== LEGACY COMP35 / STUFEE.CSV (682 RECEIPTS) ===")
print(f"  Total Receipts: {len(comp35_receipts)}")
print(f"  Total Amount in StuFee.csv: Rs. {comp35_total:,.2f}")

# Compare Cash Book PDF numbers:
# On Page 41 of Cash Book:
# Closing Balance: 12,86,230.00
# Opening Balance (01/04/2026): 16,000.00
# Net Fee Collections in Cash Book = 12,86,230 - 16,000 = 12,70,230.00
cb_total = Decimal("1286230.00") - Decimal("16000.00")
print(f"\n=== 41-PAGE CASH BOOK PDF TOTALS ===")
print(f"  Closing Balance on 13/08/2026: Rs. 1,286,230.00")
print(f"  Minus 01/04/2026 Opening Balance: Rs. 16,000.00")
print(f"  Net Fee Collection in Cash Book: Rs. {cb_total:,.2f}")

diff = live_total - cb_total
print(f"\nDifference between Live System and Cash Book Net Collection: Rs. {diff:,.2f}")

# Check which receipts make up the difference
live_by_rcp = {}
for r in live_receipts:
    num_str = str(r.legacy_receipt_no or r.receipt_no or '').replace('REC-', '').strip()
    if num_str.isdigit():
        live_by_rcp[int(num_str)] = r
comp_by_rcp = {r['rcpno']: r for r in comp35_receipts}

print(f"\nReceipt count in Live: {len(live_by_rcp)} vs Comp35: {len(comp_by_rcp)}")

# Find receipts in comp35 not in live or vice versa
missing_in_live = [rcp for rcp in comp_by_rcp if rcp not in live_by_rcp]
missing_in_comp = [rcp for rcp in live_by_rcp if rcp not in comp_by_rcp]
print(f"Missing in Live: {missing_in_live}")
print(f"Missing in Comp35: {missing_in_comp}")

# Check amount differences for common receipts
amt_diffs = []
for rcp, c_r in comp_by_rcp.items():
    if rcp in live_by_rcp:
        l_r = live_by_rcp[rcp]
        if l_r.amount_paid != c_r['paid']:
            amt_diffs.append((rcp, c_r['name'], c_r['paid'], l_r.amount_paid))

print(f"\nAmount Mismatches across matching receipts ({len(amt_diffs)}):")
for rcp, name, c_amt, l_amt in amt_diffs[:10]:
    print(f"  Rcp #{rcp:4} | {name:22} | Comp35: Rs.{c_amt:,.2f} | Live: Rs.{l_amt:,.2f} | Diff: Rs.{l_amt-c_amt:,.2f}")

# Check Receipt #1 in Cash Book vs StuFee
print("\nChecking Receipt #1 (SCCR 1) in Cash Book / StuFee:")
print(f"  In Comp35 Rcp #1: {comp_by_rcp.get(1)}")
