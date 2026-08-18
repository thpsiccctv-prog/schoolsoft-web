import csv

csv.field_size_limit(2147483647)
stufee_rows = list(csv.DictReader(open(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\StuFee.csv", encoding="utf-8-sig")))

sids = ['9791', '9689', '9690', '10144']

for sid in sids:
    print(f"\n=== All Receipts in StuFee.csv for SID {sid} ===")
    for r in stufee_rows:
        if r.get('sid') == sid:
            print(f"  Rcp No: {r.get('rcpno')} | Date: {r.get('v_date')[:10]} | Month: {r.get('MONTH')} ({r.get('FRMONTH')} to {r.get('TOMONTH')})")
            print(f"    ADM_FEE: {r.get('ADM_FEE')} | TUT_FEE: {r.get('TUT_FEE')} | GEN_FEE: {r.get('GEN_FEE')} | EXA_FEE: {r.get('EXA_FEE')} | DUE_FEE: {r.get('DUE_FEE')}")
            print(f"    FEE_TOT: {r.get('FEE_TOT')} | CON_TOT: {r.get('CON_TOT')} | NET_TOT: {r.get('NET_TOT')} | PAID: {r.get('paid')} | DUE: {r.get('due')}")
