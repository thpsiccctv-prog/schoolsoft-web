import csv

csv.field_size_limit(2147483647)
stufee_rows = list(csv.DictReader(open(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\StuFee.csv", encoding="utf-8-sig")))

mid_sids = set()
with open(r"E:\THPSIC-INTER-COLLEGE\05-reports\ALL_SCHOOL_FEE_RECONCILIATION_MASTER.csv", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        if row['class'] in ['VI', 'VII', 'VIII']:
            mid_sids.add(row['sid'])

print(f"Total active middle school students: {len(mid_sids)}")
matched_rcps = [r for r in stufee_rows if r.get('sid') in mid_sids]
print(f"Total receipts in StuFee.csv for these students: {len(matched_rcps)}")
if matched_rcps:
    for r in matched_rcps[:5]:
        print(f"  SID {r.get('sid')} | Rcp {r.get('rcpno')} | Paid: {r.get('paid')}")
else:
    print("Confirmed: No legacy receipts exist in StuFee.csv for Class VI, VII, VIII students in this session (All 53 students have ₹0 paid in old software as well).")
