from django.db import migrations


def set_thps_official_identity(apps, schema_editor):
    SchoolProfile = apps.get_model("core", "SchoolProfile")
    SchoolProfile.objects.filter(name__icontains="THPS").update(
        udise_code="09591200129",
        recognition_no="170/2018 (16-07-2018)",
        recognized_upto="Class VIII",
        medium="English",
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0024_student_scholar_register_no")]

    operations = [
        migrations.RunPython(set_thps_official_identity, migrations.RunPython.noop),
    ]
