# Generated for Cancel/Void Receipt workflow (2026-07-05)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0009_schoolprofile_udise_code_student_nationality_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='feereceipt',
            name='is_cancelled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='feereceipt',
            name='cancelled_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='feereceipt',
            name='cancel_reason',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='feereceipt',
            name='cancelled_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cancelled_receipts',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
