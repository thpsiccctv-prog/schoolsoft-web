# Fixes migration drift: 0035 AlterField for 'amount' dropped MinValueValidator.
# This restores it so Django's migration state matches the model.

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0035_studentconcession_month_range'),
    ]

    operations = [
        migrations.AlterField(
            model_name='studentconcession',
            name='amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Fixed: rupees per month. Percent: e.g. 50. Blank for Full Free.',
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name='Amount / Percentage',
            ),
        ),
    ]
