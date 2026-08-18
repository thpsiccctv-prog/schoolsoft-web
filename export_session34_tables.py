import os
import subprocess
from pathlib import Path

mdb_path = r"E:\THPSIC SCHOOLSOFT MAIN\SchoolSOFT\34\SCHOOL7.mdb"
tools_dir = r"E:\THPSIC-INTER-COLLEGE\06-ai-handoff\tools\mdbtools-win"
mdb_export = os.path.join(tools_dir, "mdb-export.exe")
out_dir = Path(r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp34\csv-for-analysis")
out_dir.mkdir(parents=True, exist_ok=True)

key_tables = [
    "FEE", "StuFee", "ADDMISSION", "Student", "Class", "Section",
    "OutStanding1", "OutStanding1_1", "OUTSTANDING_FEE", "BALANCE", "DUES", "DuE",
    "FEE_FOR_OUT", "NEW_OUTSTANDING", "DUE_2010"
]

print(f"Exporting tables from Session 34 MDB to: {out_dir}")

for tbl in key_tables:
    csv_file = out_dir / f"{tbl}.csv"
    cmd = [mdb_export, mdb_path, tbl]
    try:
        with open(csv_file, "wb") as f:
            res = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, check=True)
        sz = csv_file.stat().st_size / 1024
        print(f"  Exported [{tbl}] -> {sz:.1f} KB")
    except Exception as e:
        print(f"  Failed [{tbl}]: {e}")

print("\nExport completed!")
