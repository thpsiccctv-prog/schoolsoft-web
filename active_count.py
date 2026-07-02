"""Prints active/inactive student counts for the current database."""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
django.setup()

from core.models import Student  # noqa: E402

total = Student.objects.count()
active = Student.objects.filter(is_active=True).count()
print(f"TOTAL students : {total}")
print(f"ACTIVE (unblocked) : {active}")
print(f"INACTIVE (blocked/TC) : {total - active}")
