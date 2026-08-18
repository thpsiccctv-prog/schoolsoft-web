import csv

csv.field_size_limit(2147483647)
with open(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\FEE.csv", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

prv_non_zero = [r for r in rows if float(r.get('PRV_AMT', 0) or 0) > 0]
curr_non_zero = [r for r in rows if float(r.get('CURR_AMT', 0) or 0) > 0]

print(f"Total rows in FEE.csv: {len(rows)}")
print(f"Rows with PRV_AMT > 0 (Actual Previous Year Dues): {len(prv_non_zero)}")
print(f"Rows with CURR_AMT > 0 (Current Year Payments/Transactions): {len(curr_non_zero)}")

print("\nSample rows with PRV_AMT > 0:")
for r in prv_non_zero[:10]:
    print(f"  SID: {r.get('SID')} | CURR_AMT: {r.get('CURR_AMT')} | PRV_AMT: {r.get('PRV_AMT')}")

print("\nSample rows with CURR_AMT > 0 and PRV_AMT == 0:")
for r in curr_non_zero[:10]:
    if float(r.get('PRV_AMT', 0) or 0) == 0:
        print(f"  SID: {r.get('SID')} | CURR_AMT: {r.get('CURR_AMT')} | PRV_AMT: {r.get('PRV_AMT')}")
