import os
import csv
from pathlib import Path

csv.field_size_limit(2147483647)
dir35 = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35\csv-for-analysis")

print("=== SEARCHING FOR 'GREEN LAND', 'SAMIM', 'SHIVPUJAN' ACROSS ALL COMP35 TABLES ===")

for p in dir35.glob("*.csv"):
    try:
        with open(p, encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f)
            matches = []
            for row in reader:
                row_str = " ".join(str(v) for v in row.values()).upper()
                if "GREEN LAND" in row_str or "SAMIM" in row_str or "SHIVPUJAN" in row_str or "SUNDRY" in row_str:
                    matches.append(row)
            if matches:
                print(f"\nFound {len(matches)} matches in [{p.name}]:")
                for m in matches[:5]:
                    # print only non-empty fields
                    non_empty = {k: v for k, v in m.items() if v and v != '0' and v != '0.00'}
                    print(" ", non_empty)
    except Exception as e:
        print(f"Error in {p.name}: {e}")
