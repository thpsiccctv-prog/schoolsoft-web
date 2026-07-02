"""Fast bulk loader: data.json -> DATABASE_URL database.

Replaces slow `manage.py loaddata` (one INSERT per row over the internet)
with batched bulk_create (500 rows per round trip). Prints progress per
model and verifies final counts. FK order is handled by Postgres deferred
constraints inside a single transaction.
"""
import io
import os
from collections import OrderedDict

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
django.setup()

from django.core import serializers  # noqa: E402
from django.core.management.color import no_style  # noqa: E402
from django.db import connection, transaction  # noqa: E402

if connection.vendor != "postgresql":
    raise SystemExit(
        "DATABASE_URL PostgreSQL ki taraf nahi hai (engine: %s). "
        "Pehle Render ka External Database URL set kijiye." % connection.vendor
    )

print("Reading data.json ...")
with io.open("data.json", encoding="utf-8") as f:
    deserialized = list(serializers.deserialize("json", f, ignorenonexistent=True))
print(f"{len(deserialized)} objects in file.")

by_model = OrderedDict()
for item in deserialized:
    by_model.setdefault(item.object.__class__, []).append(item.object)

existing = {m: m.objects.count() for m in by_model}
already = {m: c for m, c in existing.items() if c > 0}
if already:
    print("WARNING: in models already have rows (duplicate load?):")
    for m, c in already.items():
        print("  ", m._meta.label, c)
    raise SystemExit("Pehle Render DB khali kijiye ya duplicate se bachne ke liye ruk gaya.")

print("Loading into PostgreSQL (batches of 500)...")
with transaction.atomic():
    with connection.constraint_checks_disabled():
        for model, objs in by_model.items():
            model.objects.bulk_create(objs, batch_size=500)
            print(f"  {model._meta.label}: {len(objs)}")

print("Resetting primary-key sequences...")
reset_sql = connection.ops.sequence_reset_sql(no_style(), list(by_model.keys()))
with connection.cursor() as cursor:
    for statement in reset_sql:
        cursor.execute(statement)

print("\nVerifying counts in PostgreSQL:")
total = 0
for model in by_model:
    count = model.objects.count()
    total += count
    print(f"  {model._meta.label}: {count}")
print("TOTAL:", total)
print("\nSAB HO GAYA! Website refresh kar ke dekhiye.")
