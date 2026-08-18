import os
import subprocess
from pathlib import Path

tools_dir = r"E:\THPSIC-INTER-COLLEGE\06-ai-handoff\tools\mdbtools-win"
mdb_export = os.path.join(tools_dir, "mdb-export.exe")
db33 = r"E:\THPSIC SCHOOLSOFT MAIN\SchoolSOFT\33\SCHOOL7.mdb"
out_dir = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp33\csv-for-analysis")
out_dir.mkdir(parents=True, exist_ok=True)

# Export key tables from Folder 33
for tbl in ["FEE", "StuFee", "ADDMISSION", "Student", "OutStanding1_1", "DUES", "FEE_FOR_OUT", "DEL_LEDGER"]:
    csv_file = out_dir / f"{tbl}.csv"
    cmd = [mdb_export, db33, tbl]
    try:
        with open(csv_file, "wb") as f:
            subprocess.run(cmd, stdout=f, check=True)
        print(f"Exported Folder 33 [{tbl}] -> {csv_file.stat().st_size/1024:.1f} KB")
    except Exception as e:
        print(f"Failed [{tbl}]: {e}")

# Inspect Manish Kumar (9087) in Folder 33
import csv
csv.field_size_limit(2147483647)

print("\n=== MANISH KUMAR (SID 9087) IN FOLDER 33 (SESSION 2025-2026) ===")
with open(out_dir / "StuFee.csv", encoding="utf-8-sig", errors="ignore") as f:
    for r in csv.DictReader(f):
        if r.get('sid') == '9087':
            print(f"StuFee Rcp {r.get('rcpno')} | Date: {r.get('v_date')} | Month: {r.get('MONTH')} | Total: {r.get('NET_TOT')} | Paid: {r.get('paid')} | Due: {r.get('due')}")

with open(out_dir / "OutStanding1_1.csv", encoding="utf-8-sig", errors="ignore") as f:
    for r in csv.DictReader(f):
        if r.get('sid') == '9087':
            print(f"OutStanding1_1: {r}")

with open(out_dir / "FEE_FOR_OUT.csv", encoding="utf-8-sig", errors="ignore") as f:
    for r in csv.DictReader(f):
        if r.get('SID') == '9087':
            print(f"FEE_FOR_OUT: {r}")
