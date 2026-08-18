import csv

csv.field_size_limit(2147483647)
fee_map = {row['SID'].strip(): row for row in csv.DictReader(open(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\FEE.csv", encoding="utf-8-sig"))}
stufee_rows = list(csv.DictReader(open(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\StuFee.csv", encoding="utf-8-sig")))

print("Inspecting Class IX Admission & Balance in FEE.csv vs StuFee.csv:")
checked = set()
for r in stufee_rows:
    sid = r.get('sid', '').strip()
    if r.get('sclass') == 'IX' and sid not in checked:
        checked.add(sid)
        f_curr = fee_map.get(sid, {}).get('CURR_AMT', '0')
        f_prv = fee_map.get(sid, {}).get('PRV_AMT', '0')
        print(f"SID {sid:5} | {r.get('sname', ''):20} | Rcp {r.get('rcpno'):4} | Adm Fee: {r.get('ADM_FEE'):6} | Tut Fee: {r.get('TUT_FEE'):6} | Paid: {r.get('paid'):6} | Due: {r.get('due'):6} | FEE CURR: {f_curr:5} PRV: {f_prv:5}")
        if len(checked) >= 15:
            break
