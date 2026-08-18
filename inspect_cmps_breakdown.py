import csv
from collections import Counter

csv.field_size_limit(2147483647)
addmission_path = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\ADDMISSION.csv"

sch_names = Counter()
cmps_rows = []

with open(addmission_path, encoding="utf-8-sig", errors="ignore") as f:
    for row in csv.DictReader(f):
        sch = (row.get("sch_name") or "").strip().upper()
        if "CMPS" in sch or "SAMIM" in sch or "SHAMIM" in sch:
            sch_names[sch] += 1
            cmps_rows.append({
                "sid": row.get("sid"),
                "name": row.get("st_name"),
                "fname": row.get("f_name"),
                "sch_name": sch,
                "class": row.get("c_code"),
                "sec": row.get("sec_code")
            })

print("Distinct sch_name values and counts:")
for s, c in sch_names.items():
    print(f"  '{s}': {c}")

print(f"\nTotal rows matched: {len(cmps_rows)}")

# Let's inspect some samples of each sch_name
for sch in sch_names.keys():
    samples = [r for r in cmps_rows if r['sch_name'] == sch][:3]
    print(f"\nSamples for '{sch}':")
    for samp in samples:
        print(f"  SID {samp['sid']}: {samp['name']} s/o {samp['fname']} (Class {samp['class']}, Sec {samp['sec']})")
