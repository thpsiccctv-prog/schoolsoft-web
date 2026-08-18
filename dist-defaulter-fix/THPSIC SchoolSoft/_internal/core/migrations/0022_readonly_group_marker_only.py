from django.db import migrations


READONLY_GROUP = "SchoolSoft Read Only"


def make_readonly_group_marker_only(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group = Group.objects.filter(name=READONLY_GROUP).first()
    if not group:
        return

    module_permissions = Permission.objects.filter(
        content_type__app_label="core",
        content_type__model="moduleaccess",
    )
    permission_ids = list(module_permissions.values_list("id", flat=True))
    if not permission_ids:
        return

    # Older viewer accounts may have relied only on the seeded group's grants.
    # Preserve their effective access before turning the group into a marker.
    for user in group.user_set.all():
        has_direct_modules = user.user_permissions.filter(id__in=permission_ids).exists()
        if not has_direct_modules:
            user.user_permissions.add(*module_permissions)

    group.permissions.remove(*module_permissions)


def restore_readonly_group_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group = Group.objects.filter(name=READONLY_GROUP).first()
    if not group:
        return

    module_permissions = Permission.objects.filter(
        content_type__app_label="core",
        content_type__model="moduleaccess",
    )
    group.permissions.add(*module_permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0021_family_alter_moduleaccess_options_student_family"),
    ]

    operations = [
        migrations.RunPython(
            make_readonly_group_marker_only,
            restore_readonly_group_permissions,
        ),
    ]
