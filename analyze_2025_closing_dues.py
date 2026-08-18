import csv
from decimal import Decimal
from collections import defaultdict

csv.field_size_limit(2147483647)

# Read all receipts in Folder 33 (Session 2025-2026)
stufee_33 = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp33\csv-for-analysis\StuFee.csv"

# Group receipts by student SID and find the latest receipt / closing due
students_2025_dues = {}

with open(stufee_33, encoding="utf-8-sig", errors="ignore") as f:
    rows = list(csv.DictReader(f))

# Sort rows by receipt number / date
# In legacy system, rcpno is numeric sequence
for r in rows:
    sid = r.get('sid', '').strip()
    if not sid: continue
    rcp_no = int(r.get('rcpno', 0) or 0)
    due_amt = Decimal(r.get('due', '0') or '0')
    v_date = r.get('v_date', '')
    sname = r.get('sname', '')
    sclass = r.get('sclass', '')
    
    if sid not in students_2025_dues or rcp_no > students_2025_dues[sid]['last_rcp_no']:
        students_2025_dues[sid] = {
            'sid': sid,
            'name': sname,
            'class_2025': sclass,
            'last_rcp_no': rcp_no,
            'last_date': v_date[:10],
            'closing_due_2025': due_amt,
        }

non_zero_2025_dues = {sid: d for sid, d in students_2025_dues.items() if d['closing_due_2025'] > 0}

print(f"Total students with receipts in 2025-2026 (Folder 33): {len(students_2025_dues)}")
print(f"Total students with genuine UNPAID CLOSING DUES in 2025-2026: {len(non_zero_2025_dues)}")
print(f"Total Unpaid Dues Amount carried from 2025-2026: Rs. {sum(d['closing_due_2025'] for d in non_zero_2025_dues.values()):,.2f}")

print("\nSample 10 students with genuine 2025-2026 closing dues:")
for sid, d in list(non_zero_2025_dues.items())[:10]:
    print(f"  SID {sid:5} | {d['name']:22} | Class 2025: {d['class_2025']:10} | Last Rcp: {d['last_rcp_no']} ({d['last_date']}) | Closing Due: Rs. {d['closing_due_2025']}")

# Check Manish Kumar specifically
if '9087' in students_2025_dues:
    print(f"\nMANISH KUMAR (SID 9087) VERIFICATION:")
    print(f"  Details: {students_2025_dues['9087']}")
