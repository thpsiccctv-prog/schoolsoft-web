"""
export_for_sync.py — Clean UTF-8 export of SchoolSoft desktop DB for online sync.

Why this exists:
  Django's dumpdata on Windows can emit non-UTF-8 bytes (e.g. 0x97 em-dash from
  data entry, written as Windows-1252/Latin-1 bytes into the JSON stream). This
  script runs dumpdata as a subprocess, captures raw bytes, and re-encodes them
  as clean UTF-8 before writing data.json — so fast_load_data.py never sees a
  UnicodeDecodeError.

Usage (called by sync-desktop-to-online.bat):
  python export_for_sync.py
"""
import subprocess
import sys
import pathlib
import json
import os


EXCLUDES = [
    "contenttypes",
    "auth.permission",
    "sessions",
    "admin.logentry",
    "core.moduleaccess",
]


def main():
    out_path = pathlib.Path("data.json")
    args = [sys.executable, "manage.py", "dumpdata", f"--output={out_path}", "--verbosity=1"]
    for exc in EXCLUDES:
        args += ["-e", exc]

    print("[3/6] Exporting desktop DB to data.json (clean UTF-8)...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(args, capture_output=True, env=env)

    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")
        print(f"ERROR: dumpdata failed:\n{err}", file=sys.stderr)
        sys.exit(1)

    # Validate it's parseable JSON
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception as e:
        print(f"ERROR: data.json is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"    Export OK: {len(obj)} records written to {out_path}")


if __name__ == "__main__":
    main()
