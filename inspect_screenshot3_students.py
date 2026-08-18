import csv

stufee_33 = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp33\csv-for-analysis\StuFee.csv"
target_sids = ['9087', '8966', '8981', '9294']

print("=== INSPECTING SCREENSHOT 3 STUDENTS IN 2025-2026 (FOLDER 33) ===")
with open(stufee_33, encoding="utf-8-sig", errors="ignore") as f:
    for r in csv.DictReader(f):
        sid = r.get('sid', '').strip()
        if sid in target_sids:
            print(f"SID {sid:5} | {r.get('sname'):22} | Rcp {r.get('rcpno'):4} | Date: {r.get('v_date')[:10]} | Month: {r.get('MONTH'):22} | Paid: Rs.{r.get('paid'):5} | Due: Rs.{r.get('due')}")
