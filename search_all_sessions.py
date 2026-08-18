import os
import subprocess
from pathlib import Path

tools_dir = r"E:\THPSIC-INTER-COLLEGE\06-ai-handoff\tools\mdbtools-win"
mdb_export = os.path.join(tools_dir, "mdb-export.exe")
base_dir = Path(r"E:\THPSIC SCHOOLSOFT MAIN\SchoolSOFT")

print("=== SEARCHING FOR RECEIPT 1991 / SID 9087 ACROSS ALL SCHOOLSOFT FOLDERS ===")

results = []

for folder in sorted(base_dir.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 999):
    if not folder.is_dir() or not folder.name.isdigit():
        continue
    mdb_file = folder / "SCHOOL7.mdb"
    if not mdb_file.exists():
        continue
    
    # Check StuFee
    try:
        cmd = [mdb_export, str(mdb_file), "StuFee"]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        lines = res.stdout.splitlines()
        rcp_1991 = [l for l in lines if "1991" in l or "1990" in l or "1989" in l]
        sid_9087 = [l for l in lines if "9087" in l]
        
        # Check FEE table as well
        cmd_fee = [mdb_export, str(mdb_file), "FEE"]
        res_fee = subprocess.run(cmd_fee, capture_output=True, text=True, errors="ignore")
        fee_9087 = [l for l in res_fee.stdout.splitlines() if "9087" in l]
        
        # Check ADDMISSION table for school year title
        cmd_env = [mdb_export, str(mdb_file), "SCHOOL_NAME"]
        res_env = subprocess.run(cmd_env, capture_output=True, text=True, errors="ignore")
        sname = res_env.stdout.splitlines()[1] if len(res_env.stdout.splitlines()) > 1 else ""

        print(f"Folder [{folder.name:2}] ({mdb_file.stat().st_size/(1024*1024):.1f} MB) | School: {sname[:30]} | StuFee rows: {len(lines)} | Fee rows: {len(res_fee.stdout.splitlines())}")
        if rcp_1991:
            print(f"   -> MATCH FOUND FOR RCP 1991 in Folder {folder.name}:")
            for r in rcp_1991[:3]: print("     ", r)
        if sid_9087:
            print(f"   -> MATCH FOUND FOR SID 9087 in StuFee in Folder {folder.name}:")
            for r in sid_9087[:3]: print("     ", r)
        if fee_9087:
            print(f"   -> MATCH FOUND FOR SID 9087 in FEE in Folder {folder.name}:")
            for r in fee_9087[:3]: print("     ", r)
    except Exception as e:
        print(f"Folder [{folder.name}]: Error {e}")
