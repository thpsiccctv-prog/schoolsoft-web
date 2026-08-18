from django.db import migrations, models


PERMISSIONS = [
    ("access_all_modules", "SchoolSoft: Access all modules"),
    ("access_dashboard", "SchoolSoft: Open dashboard"),
    ("access_students", "SchoolSoft: Students and admissions"),
    ("access_fee_collection", "SchoolSoft: Fee collection"),
    ("access_receipts", "SchoolSoft: Receipt register and receipt PDFs"),
    ("access_dues", "SchoolSoft: Dues report"),
    ("access_collection", "SchoolSoft: Collection report"),
    ("access_fee_setup", "SchoolSoft: Fee setup"),
    ("access_marks", "SchoolSoft: Marks and marksheets"),
    ("access_staff", "SchoolSoft: Staff and salary"),
    ("access_transport", "SchoolSoft: Transport"),
    ("access_school_profile", "SchoolSoft: School profile"),
]

GROUPS = {
    "SchoolSoft Administrator": [codename for codename, _ in PERMISSIONS],
    "Admission Desk": [
        "access_dashboard",
        "access_students",
        "access_school_profile",
    ],
    "Fee Desk": [
        "access_dashboard",
        "access_students",
        "access_fee_collection",
        "access_receipts",
        "access_dues",
        "access_collection",
        "access_fee_setup",
        "access_school_profile",
    ],
    "Exam Desk": [
        "access_dashboard",
        "access_students",
        "access_marks",
        "access_school_profile",
    ],
    "Staff and Transport Desk": [
        "access_dashboard",
        "access_staff",
        "access_transport",
        "access_school_profile",
    ],
    "SchoolSoft Read Only": [
        "access_dashboard",
        "access_students",
        "access_receipts",
        "access_dues",
        "access_collection",
        "access_fee_setup",
        "access_marks",
        "access_staff",
        "access_transport",
        "access_school_profile",
    ],
}


def seed_module_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    content_type, _ = ContentType.objects.get_or_create(
        app_label="core",
        model="moduleaccess",
    )

    permission_map = {}
    for codename, name in PERMISSIONS:
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        if permission.name != name:
            permission.name = name
            permission.save(update_fields=["name"])
        permission_map[codename] = permission

    for group_name, codenames in GROUPS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(*(permission_map[codename] for codename in codenames))


def unseed_module_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=GROUPS.keys()).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core", "0007_studenttransport_legacy_father_name_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModuleAccess",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
            ],
            options={
                "verbose_name": "SchoolSoft module permission",
                "verbose_name_plural": "SchoolSoft module permissions",
                "default_permissions": (),
                "permissions": PERMISSIONS,
                "managed": False,
            },
        ),
        migrations.RunPython(seed_module_permissions, unseed_module_permissions),
    ]
