from django.db import migrations


def register_number(identifier):
    try:
        number = int(str(identifier).strip())
    except (TypeError, ValueError):
        return ""
    return str(((number - 1) // 100) + 1) if number > 0 else ""


def backfill_register_numbers(apps, schema_editor):
    Student = apps.get_model("core", "Student")
    for student in Student.objects.only("pk", "admission_no", "legacy_sid").iterator():
        identifier = student.admission_no if str(student.admission_no).strip().isdigit() else student.legacy_sid
        value = register_number(identifier)
        if value:
            Student.objects.filter(pk=student.pk).update(scholar_register_no=value)


class Migration(migrations.Migration):
    dependencies = [("core", "0025_thps_official_school_identity")]

    operations = [migrations.RunPython(backfill_register_numbers, migrations.RunPython.noop)]
