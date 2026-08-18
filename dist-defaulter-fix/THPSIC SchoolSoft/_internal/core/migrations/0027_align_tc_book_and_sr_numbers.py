from django.db import migrations


def align_tc_numbers(apps, schema_editor):
    TransferCertificate = apps.get_model("core", "TransferCertificate")
    for tc in TransferCertificate.objects.select_related("student").iterator():
        student = tc.student
        tc.book_no = student.scholar_register_no
        tc.sr_no = student.admission_no or str(student.legacy_sid or "")
        tc.save(update_fields=["book_no", "sr_no"])


class Migration(migrations.Migration):
    dependencies = [("core", "0026_backfill_scholar_register_numbers")]

    operations = [migrations.RunPython(align_tc_numbers, migrations.RunPython.noop)]
