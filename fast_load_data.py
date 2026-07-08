import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

import django
from django.apps import apps
from django.core import serializers
from django.core.management import call_command
from django.core.management.color import no_style
from django.db import connection, transaction


BATCH_SIZE = 1000


def fixture_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    return Path("data.json")


def batched(items, size):
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def load_objects(path):
    with path.open("r", encoding="utf-8") as stream:
        # Deserializer converts dates, decimals, FKs, and raw fixture values
        # correctly. We bulk-create the resulting model instances below.
        return list(serializers.deserialize("json", stream))


def reset_database_tables():
    print("[1/5] Remote database tables clear ho rahe hain...")
    call_command("flush", "--noinput", verbosity=0)


def migrate_database():
    print("[2/5] Migrations apply/check ho rahe hain...")
    call_command("migrate", "--noinput", verbosity=1)


def bulk_insert(deserialized):
    print("[3/5] Data bulk insert ho raha hai...")
    grouped = OrderedDict()
    m2m_rows = []

    for item in deserialized:
        grouped.setdefault(item.object.__class__, []).append(item.object)
        if item.m2m_data:
            m2m_rows.append(item)

    inserted = 0
    loaded_models = []
    with transaction.atomic():
        with connection.constraint_checks_disabled():
            for model, objects in grouped.items():
                loaded_models.append(model)
                model_name = model._meta.label
                for batch in batched(objects, BATCH_SIZE):
                    model.objects.bulk_create(batch, batch_size=BATCH_SIZE)
                    inserted += len(batch)
                    print(f"    {model_name}: {inserted} total objects inserted")

            # Most SchoolSoft fixture models have no M2M data, but auth.User can.
            for item in m2m_rows:
                obj = item.object
                for field_name, values in item.m2m_data.items():
                    getattr(obj, field_name).set(values)

        print("[4/5] Constraints check ho raha hai...")
        connection.check_constraints()

        sequence_sql = connection.ops.sequence_reset_sql(no_style(), loaded_models)
        if sequence_sql:
            with connection.cursor() as cursor:
                for statement in sequence_sql:
                    cursor.execute(statement)

    print(f"    Total loaded objects: {inserted}")


def print_counts():
    print("[5/5] Final counts:")
    for label in [
        "core.Student",
        "core.FeeReceipt",
        "core.FeeReceiptLine",
        "core.ExamMark",
        "core.Staff",
        "core.StudentTransport",
        "core.AccountGroup",
        "core.LedgerAccount",
        "core.Voucher",
        "core.SalaryPayment",
    ]:
        model = apps.get_model(label)
        print(f"    {label}: {model.objects.count()}")


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL missing hai. Render External Database URL set/paste kijiye.")

    path = fixture_path()
    if not path.exists():
        raise SystemExit(f"{path} nahi mila.")

    django.setup()
    migrate_database()
    data = load_objects(path)
    print(f"    Fixture objects: {len(data)}")
    reset_database_tables()
    bulk_insert(data)
    print_counts()
    print("SAB HO GAYA - Render site refresh karke counts verify kijiye.")


if __name__ == "__main__":
    main()
