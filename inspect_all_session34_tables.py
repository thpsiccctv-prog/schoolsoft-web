import os
import subprocess

mdb_path = r"E:\THPSIC SCHOOLSOFT MAIN\SchoolSOFT\34\SCHOOL7.mdb"
tools_dir = r"E:\THPSIC-INTER-COLLEGE\06-ai-handoff\tools\mdbtools-win"
mdb_tables = os.path.join(tools_dir, "mdb-tables.exe")
mdb_count = os.path.join(tools_dir, "mdb-count.exe")

# Get table names
res = subprocess.run([mdb_tables, "-1", mdb_path], capture_output=True, text=True, check=True)
tables = [t.strip() for t in res.stdout.splitlines() if t.strip()]

print(f"Total tables in Session 34 MDB: {len(tables)}")
print("Table row counts (showing tables with > 0 rows):")

for t in tables:
    try:
        cnt_res = subprocess.run([mdb_count, mdb_path, t], capture_output=True, text=True)
        cnt = cnt_res.stdout.strip()
        if cnt and cnt != "0":
            print(f"  [{t}]: {cnt} rows")
    except:
        pass
