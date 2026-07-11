from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0022_readonly_group_marker_only")]

    operations = [
        migrations.AddField(
            model_name="schoolprofile",
            name="medium",
            field=models.CharField(blank=True, default="English", max_length=50),
        ),
        migrations.AddField(
            model_name="schoolprofile",
            name="recognition_no",
            field=models.CharField(blank=True, max_length=100, verbose_name="Recognition Order No."),
        ),
        migrations.AddField(
            model_name="schoolprofile",
            name="recognized_upto",
            field=models.CharField(blank=True, default="Class VIII", max_length=50),
        ),
        migrations.AddField(
            model_name="transfercertificate",
            name="annual_exam_result",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="transfercertificate",
            name="application_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="transfercertificate",
            name="extracurricular_activities",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
