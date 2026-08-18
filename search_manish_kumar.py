import os
import csv
from pathlib import Path

dir34 = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp34\csv-for-analysis")
dir35 = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis")

print("=== SEARCHING FOR SID 9087 (MANISH KUMAR) IN SESSION 34 (2025-2026) ===")

for p in dir34.glob("*.csv"):
    try:
        with open(p, encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f)
            matches = []
            for row in reader:
                # Check if any field contains 9087 or MANISH
                row_str = " ".join(str(v) for v in row.values())
                if "9087" in row_str or "MANISH" in row_str.upper():
                    matches.append(row)
            if matches:
                print(f"\nFound {len(matches)} match(es) in Session 34 [{p.name}]:")
                for m in matches[:5]:
                    print(" ", m)
    except Exception as e:
        print(f"Error reading {p.name}: {e}")

print("\n=== SEARCHING FOR SID 9087 (MANISH KUMAR) IN SESSION 35 (2026-2027) ===")
for p in dir35.glob("*.csv"):
    try:
        with open(p, encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f)
            matches = []
            for row in reader:
                row_str = " ".join(str(v) for v in row.values())
                if "9087" in row_str or "MANISH" in row_str.upper():
                    if row.get('SID') == '9087' or row.get('sid') == '9087' or "9087" in row_str:
                        matches.append(row)
            if matches:
                print(f"\nFound {len(matches)} match(es) in Session 35 [{p.name}]:")
                for m in matches[:5]:
                    print(" ", m)
    except Exception as e:
        print(f"Error reading {p.name}: {e}")
