from django.db import migrations


def create_balance_fee_head(apps, schema_editor):
    FeeHead = apps.get_model("core", "FeeHead")
    FeeHead.objects.update_or_create(
        name="Balance Fee",
        defaults={
            "frequency": "optional",
            "applies_to": "both",
            "new_student_charge_rule": "not_applicable",
            "old_student_charge_rule": "not_applicable",
            "new_student_charge_months": [],
            "old_student_charge_months": [],
            "is_transport": False,
            "is_active": True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_studentopeningbalance_feehead_applies_to_and_more"),
    ]

    operations = [
        migrations.RunPython(create_balance_fee_head, migrations.RunPython.noop),
    ]