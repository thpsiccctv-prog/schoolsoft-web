import csv

csv.field_size_limit(2147483647)
with open(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\DuE.csv", encoding="utf-8-sig") as f:
    r = list(csv.DictReader(f))
    print(f"Total rows in DuE.csv: {len(r)}")
    valid_dues = [row for row in r if row.get('DUE') and float(row.get('DUE', 0)) > 0]
    print(f"Rows with positive DUE: {len(valid_dues)}")
    for row in valid_dues[:15]:
        print(f"  SID: {row.get('Sid')} | Name: {row.get('SNAME')} | DUE: ₹{row.get('DUE')}")
