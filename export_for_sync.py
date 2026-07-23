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
    # Build dumpdata args
    args = [sys.executable, "manage.py", "dumpdata", "--verbosity=0"]
    for exc in EXCLUDES:
        args += ["-e", exc]

    print("[3/6] Exporting desktop DB to data.json (clean UTF-8)...")
    result = subprocess.run(args, capture_output=True)

    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")
        print(f"ERROR: dumpdata failed:\n{err}", file=sys.stderr)
        sys.exit(1)

    # Decode as Latin-1 first (lossless — every byte 0x00-0xFF is valid Latin-1)
    # then re-encode as UTF-8. This converts Windows-1252 special chars like
    # 0x97 (em-dash) to their proper Unicode codepoints (U+2014) in UTF-8.
    raw_bytes = result.stdout

    # Strip UTF-8 BOM if present
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raw_bytes = raw_bytes[3:]

    text = raw_bytes.decode("latin-1")

    # Validate it's parseable JSON before writing
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"ERROR: dumpdata output is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    out_path = pathlib.Path("data.json")
    out_path.write_text(text, encoding="utf-8")
    print(f"    Export OK: {len(obj)} records written to {out_path}")


if __name__ == "__main__":
    main()
