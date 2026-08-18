import os
import csv
from decimal import Decimal

stufee_35 = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\StuFee.csv"
csv.field_size_limit(2147483647)

# Let's check receipts on 11/06/2026 vs Cash Book Page 16:
# Cash Book Page 16:
# Opening on 11/06/2026: 316980.00
# SCCR 195: 800.00
# Closing on 11/06/2026: 318280.00 -> wait, 316980 + 800 = 317780, but Cash Book printed Closing: 318280 (diff = 500)!
# Let's check StuFee for 11/06/2026:
with open(stufee_35, encoding="utf-8-sig", errors="ignore") as f:
    for r in csv.DictReader(f):
        if '2026-06-11' in r.get('v_date', '') or r.get('rcpno') in ['195', '196']:
            print(f"Rcp {r.get('rcpno')} | Date: {r.get('v_date')} | SID: {r.get('sid')} | Name: {r.get('sname')} | Paid: {r.get('paid')}")
            
# Let's check Page 17 (11/06/2026 continued or 15/06/2026):
# Page 17: SCCR 196 (ID-8602, 500.00) -> Closing: 318280.00!
# So SCCR 195 (800) + SCCR 196 (500) = 1300!
# 316980 + 1300 = 318280! (Match!)

# Let's compare all dates systematically!
# Cash book page daily closing balances:
cb_daily = {
    '2026-04-01': Decimal('21000.00'),
    '2026-04-04': Decimal('22500.00'),
    '2026-04-06': Decimal('23100.00'),
    '2026-04-07': Decimal('25100.00'),
    '2026-04-08': Decimal('35000.00'),
    '2026-04-09': Decimal('46300.00'),
    '2026-04-10': Decimal('50600.00'),
    '2026-04-12': Decimal('53600.00'),
    '2026-04-13': Decimal('57000.00'),
    '2026-04-14': Decimal('60000.00'),
    '2026-04-15': Decimal('67000.00'),
    '2026-04-16': Decimal('75500.00'),
    '2026-04-17': Decimal('85200.00'),
    '2026-04-18': Decimal('86600.00'),
    '2026-04-20': Decimal('88200.00'),
    '2026-04-21': Decimal('91800.00'),
    '2026-04-22': Decimal('95300.00'),
    '2026-04-23': Decimal('98800.00'),
    '2026-04-24': Decimal('99300.00'),
    '2026-04-25': Decimal('105800.00'),
    '2026-04-26': Decimal('107300.00'),
    '2026-04-27': Decimal('111200.00'),
    '2026-04-28': Decimal('113200.00'),
    '2026-04-29': Decimal('117200.00'),
    '2026-04-30': Decimal('131600.00'),
    '2026-05-02': Decimal('136200.00'),
    '2026-05-03': Decimal('139200.00'),
    '2026-05-04': Decimal('147800.00'),
    '2026-05-05': Decimal('154500.00'),
    '2026-05-06': Decimal('173200.00'),
    '2026-05-08': Decimal('184400.00'),
    '2026-05-09': Decimal('185400.00'),
    '2026-05-11': Decimal('203600.00'), # In StuFee: May 11 had Rs. 19,200 -> 185400 + 19200 = 204600! But CB shows 203600 (diff = -1000)!
}

print("\nChecking May 11 receipts in StuFee vs Cash Book:")
with open(stufee_35, encoding="utf-8-sig", errors="ignore") as f:
    for r in csv.DictReader(f):
        if '2026-05-11' in r.get('v_date', ''):
            print(f"  Rcp {r.get('rcpno'):3} | SID: {r.get('sid')} | Name: {r.get('sname'):20} | Paid: Rs.{r.get('paid')}")
