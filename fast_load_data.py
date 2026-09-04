import json
import os
import sys
import time
from collections import OrderedDict
from pathlib import Path

import django
from django.apps import apps
from django.core import serializers
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.management.color import no_style
from django.db import InterfaceError, OperationalError, connection, transaction


BATCH_SIZE = int(os.environ.get("SCHOOLSOFT_SYNC_BATCH_SIZE", "50"))
DB_PHASE_ATTEMPTS = int(os.environ.get("SCHOOLSOFT_SYNC_DB_ATTEMPTS", "3"))
BATCH_PAUSE_SECONDS = float(os.environ.get("SCHOOLSOFT_SYNC_BATCH_PAUSE_SECONDS", "0.02"))

# Keep parent rows before child rows when committing in small batches.  The
# fixture is dumped app-by-app, so auth rows naturally appear after core rows,
# but FeeReceipt rows can reference auth.User through edit/cancel audit fields.
# Keep parent rows before child rows when committing in small batches.
# Essential for PostgreSQL which enforces FK constraints at commit time.
MODEL_LOAD_PRIORITY = {
    "auth.group": 10,
    "auth.user": 20,
    "core.feederschool": 25,
    "core.house": 25,
    "core.academicsession": 25,
    "core.schoolclass": 26,
    "core.section": 27,
    "core.schoolprofile": 28,
    "core.feehead": 29,
    "core.accountgroup": 30,
    "core.ledgeraccount": 31,
    "core.staff": 32,
    "core.subject": 33,
    "core.examterm": 34,
    "core.examtest": 35,
    "core.student": 40,
    "core.feestructure": 45,
    "core.studentopeningbalance": 50,
    "core.studentfeewaiver": 50,
    "core.studentconcession": 50,
    "core.feereceipt": 60,
    "core.feereceiptline": 70,
    "core.salarypayment": 80,
    "core.salarypaymentauditlog": 85,
    "core.vouchercounter": 90,
    "core.voucher": 92,
    "core.exammark": 95,
    "core.legacyimportbatch": 100,
}


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


def run_db_phase(label, callback):
    """Render free DB can close stale local connections; reopen and retry phases."""
    for attempt in range(1, DB_PHASE_ATTEMPTS + 1):
        connection.close()
        try:
            return callback()
        except (OperationalError, InterfaceError, CommandError) as exc:
            connection.close()
            if attempt >= DB_PHASE_ATTEMPTS:
                raise
            wait_seconds = attempt * 5
            print(f"    {label} failed ({exc.__class__.__name__}). Retry {attempt + 1}/{DB_PHASE_ATTEMPTS} in {wait_seconds}s...")
            time.sleep(wait_seconds)


def bulk_create_batch(model, batch, model_name):
    for attempt in range(1, DB_PHASE_ATTEMPTS + 1):
        connection.close()
        try:
            with transaction.atomic():
                apply_postgres_batch_timeouts()
                model.objects.bulk_create(
                    batch,
                    batch_size=BATCH_SIZE,
                    # If Render drops the connection during COMMIT, PostgreSQL
                    # may still have committed that batch. Retrying with
                    # ignore_conflicts avoids duplicate-PK aborts while still
                    # surfacing FK or constraint mistakes.
                    ignore_conflicts=attempt > 1,
                )
            connection.close()
            if BATCH_PAUSE_SECONDS:
                time.sleep(BATCH_PAUSE_SECONDS)
            return
        except (OperationalError, InterfaceError) as exc:
            connection.close()
            if attempt >= DB_PHASE_ATTEMPTS:
                raise
            wait_seconds = attempt * 5
            print(
                f"    {model_name} batch failed ({exc.__class__.__name__}). "
                f"Retry {attempt + 1}/{DB_PHASE_ATTEMPTS} in {wait_seconds}s..."
            )
            cleanup_stale_load_sessions(model_name)
            time.sleep(wait_seconds)


def apply_postgres_batch_timeouts():
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '20s'")
        cursor.execute("SET LOCAL statement_timeout = '120s'")
        cursor.execute("SET LOCAL idle_in_transaction_session_timeout = '60s'")


def cleanup_stale_load_sessions(model_name):
    try:
        terminate_stale_postgres_load_sessions()
    except (OperationalError, InterfaceError) as cleanup_exc:
        connection.close()
        print(
            f"    {model_name} stale-session cleanup skipped "
            f"({cleanup_exc.__class__.__name__})."
        )


def terminate_stale_postgres_load_sessions():
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            select pg_terminate_backend(pid)
            from pg_stat_activity
            where datname = current_database()
              and pid <> pg_backend_pid()
              and (
                    state = 'idle in transaction'
                    or query like 'INSERT INTO "core_%'
                    or query like 'TRUNCATE "%'
                  );
            """
        )
        terminated = sum(1 for row in cursor.fetchall() if row[0])
    if terminated:
        print(f"    Stale PostgreSQL load sessions terminated: {terminated}")
    connection.close()


def reset_database_tables():
    print("[1/5] Remote database tables clear ho rahe hain...")
    run_db_phase("terminate stale sessions", terminate_stale_postgres_load_sessions)
    run_db_phase("flush", lambda: call_command("flush", "--noinput", verbosity=0))
    connection.close()


def migrate_database():
    print("[2/5] Migrations apply/check ho rahe hain...")
    run_db_phase("migrate", lambda: call_command("migrate", "--noinput", verbosity=1))
    connection.close()


def bulk_insert(deserialized):
    print("[3/5] Data bulk insert ho raha hai...")
    grouped = OrderedDict()
    m2m_rows = []

    for item in deserialized:
        grouped.setdefault(item.object.__class__, []).append(item.object)
        if item.m2m_data:
            m2m_rows.append(item)

    inserted = 0
    # Dynamic topological sort based on FK dependencies to guarantee parent before child on PostgreSQL
    from collections import deque
    present_models = list(grouped.keys())
    adj = {m: set() for m in present_models}
    in_degree = {m: 0 for m in present_models}
    for m in present_models:
        for f in m._meta.fields:
            if f.is_relation and f.related_model in present_models and f.related_model != m:
                if m not in adj[f.related_model]:
                    adj[f.related_model].add(m)
                    in_degree[m] += 1

    queue = deque([m for m in present_models if in_degree[m] == 0])
    ordered_models = []
    while queue:
        curr = queue.popleft()
        ordered_models.append(curr)
        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    for m in present_models:
        if m not in ordered_models:
            ordered_models.append(m)

    ordered_groups = [(m, grouped[m]) for m in ordered_models]

    loaded_models = []
    for model, objects in ordered_groups:
        loaded_models.append(model)
        model_name = model._meta.label
        for batch in batched(objects, BATCH_SIZE):
            bulk_create_batch(model, batch, model_name)
            inserted += len(batch)
            print(f"    {model_name}: {inserted} total objects inserted")

    # Most SchoolSoft fixture models have no M2M data, but auth.User can.
    for item in m2m_rows:
        obj = item.object
        for field_name, values in item.m2m_data.items():
            with transaction.atomic():
                getattr(obj, field_name).set(values)

    print("[4/5] Constraints check ho raha hai...")
    connection.check_constraints()

    sequence_sql = connection.ops.sequence_reset_sql(no_style(), loaded_models)
    if sequence_sql:
        with connection.cursor() as cursor:
            for statement in sequence_sql:
                cursor.execute(statement)

    connection.close()
    print(f"    Total loaded objects: {inserted}")


def print_counts():
    connection.close()
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
    marker_path = os.environ.get("SCHOOLSOFT_SYNC_LOAD_MARKER")
    if marker_path:
        Path(marker_path).write_text("fast_load_data complete\n", encoding="utf-8")
    print("SAB HO GAYA - Render site refresh karke counts verify kijiye.")


if __name__ == "__main__":
    main()
