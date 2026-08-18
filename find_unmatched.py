import os
import sys
import re
from collections import Counter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from core.models import Student
from generate_hindi_master_csv import DICTIONARY

words = Counter()
for s in Student.objects.filter(is_active=True):
    for field in [s.full_name, s.father_name, s.mother_name]:
        if field:
            cleaned = re.sub(r"[^a-zA-Z\s\.]", " ", field).strip()
            for w in cleaned.split():
                if w.upper() not in DICTIONARY:
                    words[w.upper()] += 1

with open("unmatched_words.txt", "w", encoding="utf-8") as f:
    for w, c in words.most_common():
        f.write(f"{w}: {c}\n")

print(f"Total unique unmatched words: {len(words)}")
print("Top 40:")
for w, c in words.most_common(40):
    print(f"  {w}: {c}")
