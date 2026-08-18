"""
Migration: Add Hindi name fields and exam_medium to Student model.

New fields:
  - full_name_hindi
  - father_name_hindi
  - mother_name_hindi
  - exam_medium  (H=Hindi / E=English, blank allowed)

All fields are blank=True / default '' so this is a safe, no-data-loss migration.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0036_fix_amount_validator_drift'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='full_name_hindi',
            field=models.CharField(
                blank=True,
                max_length=120,
                verbose_name='Full Name (Hindi)',
                help_text='छात्र/छात्रा का नाम हिंदी में (admission form print ke liye).',
            ),
        ),
        migrations.AddField(
            model_name='student',
            name='father_name_hindi',
            field=models.CharField(
                blank=True,
                max_length=120,
                verbose_name="Father's Name (Hindi)",
                help_text='पिता का नाम हिंदी में।',
            ),
        ),
        migrations.AddField(
            model_name='student',
            name='mother_name_hindi',
            field=models.CharField(
                blank=True,
                max_length=120,
                verbose_name="Mother's Name (Hindi)",
                help_text='माता का नाम हिंदी में।',
            ),
        ),
        migrations.AddField(
            model_name='student',
            name='exam_medium',
            field=models.CharField(
                blank=True,
                choices=[('H', 'Hindi'), ('E', 'English')],
                max_length=1,
                verbose_name='Exam Medium',
                help_text='परीक्षा माध्यम: Hindi or English (UP Board form field).',
            ),
        ),
    ]
