import csv

csv.field_size_limit(2147483647)
due_map = {row['Sid'].strip(): row for row in csv.DictReader(open(r'E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\DuE.csv', encoding='utf-8-sig')) if row.get('Sid')}
fee_map = {row['SID'].strip(): row for row in csv.DictReader(open(r'E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\FEE.csv', encoding='utf-8-sig')) if row.get('SID')}

sids = ['9786', '9003', '9008', '8645', '7979', '9496', '7973', '8512', '9713', '9783', '8931', '9485', '9281', '8322', '9131', '8961', '8511', '9126', '9883']

for s in sids:
    f_curr = fee_map.get(s, {}).get('CURR_AMT', '0')
    f_prv = fee_map.get(s, {}).get('PRV_AMT', '0')
    d_val = due_map.get(s, {}).get('DUE', 'None')
    print(f"SID: {s:5} | FEE table: CURR={f_curr:6} PRV={f_prv:6} | DuE table: DUE={d_val}")
