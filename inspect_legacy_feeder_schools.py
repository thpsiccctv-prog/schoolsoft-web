import os
import csv
from collections import Counter

csv.field_size_limit(2147483647)
addmission_35 = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis\ADDMISSION.csv"

# Let's inspect column names in ADDMISSION.csv
with open(addmission_35, encoding="utf-8-sig", errors="ignore") as f:
    reader = csv.DictReader(f)
    print("ADDMISSION.csv fieldnames (first 30):", reader.fieldnames[:30])
    
    # Check for school fields
    school_fields = [fn for fn in reader.fieldnames if 'school' in fn.lower() or 'from' in fn.lower() or 'attached' in fn.lower() or 'center' in fn.lower() or 'branch' in fn.lower()]
    print("Potential feeder school fields in ADDMISSION.csv:", school_fields)

# Inspect unique values in these fields
with open(addmission_35, encoding="utf-8-sig", errors="ignore") as f:
    reader = csv.DictReader(f)
    from_schools = Counter()
    for row in reader:
        for sf in school_fields:
            val = row.get(sf, '').strip()
            if val and val != '0':
                from_schools[f"{sf}: {val}"] += 1

print("\nFeeder School values in ADDMISSION.csv:")
for k, cnt in from_schools.most_common(30):
    print(f"  {k:45}: {cnt} students")
