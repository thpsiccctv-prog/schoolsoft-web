import os
import csv
from decimal import Decimal

stufee_35 = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\StuFee.csv"
csv.field_size_limit(2147483647)

comp35_receipts = {}
with open(stufee_35, encoding="utf-8-sig", errors="ignore") as f:
    for r in csv.DictReader(f):
        try:
            rcp = int(float(r.get('rcpno') or 0))
            paid = Decimal(str(r.get('paid') or '0').strip())
            sid = str(r.get('sid') or '').strip()
            sname = r.get('sname', '')
            v_date = r.get('v_date', '')[:10]
            comp35_receipts[rcp] = {
                'rcpno': rcp,
                'sid': sid,
                'name': sname,
                'date': v_date,
                'paid': paid,
                'fee_tot': Decimal(str(r.get('NET_TOT') or r.get('FEE_TOT') or '0').strip()),
            }
        except:
            pass

print(f"Loaded {len(comp35_receipts)} receipts from StuFee.csv")

# Let's inspect receipts with 0 paid in StuFee or missing in Cash Book
zero_paid = [r for r in comp35_receipts.values() if r['paid'] == 0]
print(f"\nZero-paid receipts in StuFee ({len(zero_paid)}):")
for z in zero_paid:
    print(f"  Rcp #{z['rcpno']:3} | Date: {z['date']} | SID: {z['sid']} | {z['name']} | FeeTot: {z['fee_tot']} | Paid: {z['paid']}")

# Let's check SCCR vouchers in Cash Book that had 0 in StuFee or vice versa
# Check Page 1 of Cash Book:
# Notice: Cash Book starts at SCCR 2 on 01/04/2026!
# Where is SCCR 1?
print(f"\nReceipt #1 in StuFee: {comp35_receipts.get(1)}")

# Let's check all receipts where SCCR in Cash Book had no amount printed in OCR
# (e.g. SCCR 5, 6, 101, 112, 124, 126, 140, 143, 144, 200-211, etc.)
blank_ocr_vouchers = [5, 6, 101, 112, 124, 126, 140, 143, 144, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 247, 248, 267, 275, 313, 318, 319, 320, 321, 358, 359, 365, 372, 373, 387, 388, 398, 399, 423, 431, 458, 463, 464, 465, 468, 474, 485, 612, 614, 645, 657, 668, 680]

print(f"\nChecking blank OCR vouchers in StuFee (sample):")
blank_total_in_stufee = Decimal("0.00")
for v in blank_ocr_vouchers:
    st = comp35_receipts.get(v)
    if st:
        blank_total_in_stufee += st['paid']
        if st['paid'] > 0:
            print(f"  Rcp #{v:3} in StuFee has paid: Rs. {st['paid']} (SID {st['sid']} {st['name']})")

print(f"Total paid in StuFee for blank vouchers: Rs. {blank_total_in_stufee:,.2f}")
