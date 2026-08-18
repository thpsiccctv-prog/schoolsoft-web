from django.db import migrations, models


def copy_existing_sr_numbers(apps, schema_editor):
    Student = apps.get_model("core", "Student")
    TransferCertificate = apps.get_model("core", "TransferCertificate")

    for tc in TransferCertificate.objects.exclude(sr_no="").iterator():
        Student.objects.filter(pk=tc.student_id, scholar_register_no="").update(
            scholar_register_no=tc.sr_no
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0023_tc_official_record_fields")]

    operations = [
        migrations.AddField(
            model_name="student",
            name="scholar_register_no",
            field=models.CharField(
                blank=True,
                help_text="Office's permanent Scholar's Register page number for this student (assigned at admission, written by hand in the physical register).",
                max_length=30,
                verbose_name="Scholar Register No.",
            ),
        ),
        migrations.RunPython(copy_existing_sr_numbers, migrations.RunPython.noop),
    ]
