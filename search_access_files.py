import os
import glob
from pathlib import Path

# Search for SCHOOL7 files
search_paths = [
    r"E:\THPSIC SCHOOLSOFT MAIN",
    r"E:\THPSIC-INTER-COLLEGE",
    r"E:\*",
]

print("=== SEARCHING FOR ACCESS DATABASE FILES ===")
for base in [r"E:\THPSIC SCHOOLSOFT MAIN", r"E:\THPSIC-INTER-COLLEGE", r"E:\34", r"E:\35"]:
    if os.path.exists(base):
        for root, dirs, files in os.walk(base):
            for f in files:
                if "school" in f.lower() or f.lower().endswith(('.mdb', '.accdb', '.csv')):
                    fp = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(fp) / (1024 * 1024)
                        print(f"  Found: {fp} ({sz:.2f} MB)")
                    except:
                        pass
