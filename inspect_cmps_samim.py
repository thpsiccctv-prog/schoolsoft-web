import os
import csv
from collections import Counter

legacy_dir = r'E:\THPSIC-INTER-COLLEGE\02-legacy-data'
adm_csv = os.path.join(legacy_dir, 'ADDMISSION.csv')

with open(adm_csv, 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"Total rows in ADDMISSION.csv: {len(rows)}")
fieldnames = reader.fieldnames
print("Fieldnames:", fieldnames)

# Look for CMPS or SAMIM in all fields
matches_by_field = {}
for field in fieldnames:
    field_matches = []
    for r in rows:
        val = r.get(field, '') or ''
        if any(k in val.upper() for k in ['CMPS', 'SAMIM', 'SHAMIM']):
            field_matches.append(val)
    if field_matches:
        matches_by_field[field] = Counter(field_matches)

print("\n--- ALL MATCHES FOR CMPS / SAMIM ACROSS ALL COLUMNS ---")
for field, counter in matches_by_field.items():
    print(f"\nColumn: '{field}' (Total matched: {sum(counter.values())})")
    for val, count in counter.most_common(10):
        print(f"  '{val}': {count}")
