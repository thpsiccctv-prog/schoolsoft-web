import os
import csv
from decimal import Decimal
from collections import defaultdict

stufee_35 = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\StuFee.csv"
csv.field_size_limit(2147483647)

daily_stufee = defaultdict(lambda: {"count": 0, "total": Decimal("0.00"), "rcps": []})

with open(stufee_35, encoding="utf-8-sig", errors="ignore") as f:
    for r in csv.DictReader(f):
        try:
            rcp = int(float(r.get('rcpno') or 0))
            paid = Decimal(str(r.get('paid') or '0').strip())
            v_date = r.get('v_date', '')[:10]
            daily_stufee[v_date]["count"] += 1
            daily_stufee[v_date]["total"] += paid
            daily_stufee[v_date]["rcps"].append((rcp, paid, r.get('sname')))
        except:
            pass

print("=== STUFEE.CSV DAILY TOTALS (SAMPLE DAYS) ===")
for d in sorted(daily_stufee.keys()):
    print(f"  Date: {d} | Receipts: {daily_stufee[d]['count']:2} | Total: Rs. {daily_stufee[d]['total']:10,.2f}")
