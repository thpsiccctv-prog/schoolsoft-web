# Generated manually — adds from_month / to_month to StudentConcession
# and updates verbose choices to match the revised model.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0034_studentconcession'),
    ]

    operations = [
        # Add from_month field
        migrations.AddField(
            model_name='studentconcession',
            name='from_month',
            field=models.CharField(
                blank=True,
                choices=[
                    ('APR', 'APR'), ('MAY', 'MAY'), ('JUN', 'JUN'),
                    ('JUL', 'JUL'), ('AUG', 'AUG'), ('SEP', 'SEP'),
                    ('OCT', 'OCT'), ('NOV', 'NOV'), ('DEC', 'DEC'),
                    ('JAN', 'JAN'), ('FEB', 'FEB'), ('MAR', 'MAR'),
                ],
                help_text='Blank = from session start (APR).',
                max_length=3,
                verbose_name='From Month',
            ),
        ),
        # Add to_month field
        migrations.AddField(
            model_name='studentconcession',
            name='to_month',
            field=models.CharField(
                blank=True,
                choices=[
                    ('APR', 'APR'), ('MAY', 'MAY'), ('JUN', 'JUN'),
                    ('JUL', 'JUL'), ('AUG', 'AUG'), ('SEP', 'SEP'),
                    ('OCT', 'OCT'), ('NOV', 'NOV'), ('DEC', 'DEC'),
                    ('JAN', 'JAN'), ('FEB', 'FEB'), ('MAR', 'MAR'),
                ],
                help_text='Blank = till session end (MAR).',
                max_length=3,
                verbose_name='To Month',
            ),
        ),
        # Update concession_type choices (verbose label change for full_free and sibling_discount)
        migrations.AlterField(
            model_name='studentconcession',
            name='concession_type',
            field=models.CharField(
                choices=[
                    ('monthly_waiver', 'Monthly Fee Waiver'),
                    ('sibling_discount', 'Sibling Discount'),
                    ('one_time', 'One-time Concession'),
                    ('full_free', 'Full Free (Whole Session)'),
                ],
                default='monthly_waiver',
                max_length=20,
                verbose_name='Concession Type',
            ),
        ),
        # Update amount_type choices (verbose label change)
        migrations.AlterField(
            model_name='studentconcession',
            name='amount_type',
            field=models.CharField(
                choices=[
                    ('fixed', 'Fixed Amount (₹)'),
                    ('percent', 'Percentage (%) — monthly only'),
                    ('full', '100% Free'),
                ],
                default='fixed',
                max_length=10,
                verbose_name='Amount Type',
            ),
        ),
        # Update amount help_text
        migrations.AlterField(
            model_name='studentconcession',
            name='amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Fixed: rupees per month. Percent: e.g. 50. Blank for Full Free.',
                max_digits=10,
                null=True,
                verbose_name='Amount / Percentage',
            ),
        ),
    ]
