"""Counts rows in whichever database DATABASE_URL points to."""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
django.setup()

from django.apps import apps  # noqa: E402
from django.db import connection  # noqa: E402

print("Database engine:", connection.vendor)
total = 0
for model in apps.get_models():
    if model._meta.app_label in ("core", "auth"):
        count = model.objects.count()
        total += count
        print(f"{model._meta.app_label}.{model.__name__}: {count}")
print("TOTAL:", total)
