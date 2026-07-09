"""In-app Users & Permissions screen (administrators only).

Built on Django's own auth (users, groups, permissions) so no extra model or
migration is needed. Module access is stored as direct user permissions; the
"view / print only" flag is stored as membership of the Read Only group.
"""
import json

from django.contrib import messages
from django.contrib.auth.models import Group, Permission, User
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .access import MODULE_PERMISSIONS, READONLY_GROUP, manage_users_required


# Modules shown as checkboxes (dashboard is always granted, so it is omitted).
MODULES_UI = [
    ("students", "Students & Admissions"),
    ("fee_collection", "Fee Collection"),
    ("receipts", "Receipts"),
    ("dues", "Dues"),
    ("collection", "Collection Report"),
    ("fee_setup", "Fee Setup"),
    ("marks", "Marks & Marksheets"),
    ("staff", "Staff & Salary"),
    ("transport", "Transport"),
    ("school_profile", "School Profile"),
    ("accounts", "Accounts & Cash Book"),
    ("inventory", "Inventory (Uniform/Books)"),
]
ALL_KEYS = [key for key, _ in MODULES_UI]

ROLE_LABELS = [
    ("admin", "Administrator (full access)"),
    ("fee", "Fee Desk"),
    ("admission", "Admission Desk"),
    ("exam", "Exam Desk"),
    ("staff", "Staff & Transport"),
    ("accounts", "Accounts Desk"),
    ("viewer", "Viewer (read / print only)"),
    ("custom", "Custom"),
]

ROLE_PRESETS = {
    "admin": {"modules": ALL_KEYS, "view_only": False, "is_admin": True},
    "fee": {
        "modules": ["students", "fee_collection", "receipts", "dues",
                    "collection", "fee_setup", "school_profile"],
        "view_only": False, "is_admin": False,
    },
    "admission": {"modules": ["students", "school_profile"], "view_only": False, "is_admin": False},
    "exam": {"modules": ["students", "marks", "school_profile"], "view_only": False, "is_admin": False},
    "staff": {"modules": ["staff", "transport", "school_profile"], "view_only": False, "is_admin": False},
    "accounts": {
        "modules": ["accounts", "school_profile"],
        "view_only": False, "is_admin": False,
    },
    "viewer": {"modules": ALL_KEYS, "view_only": True, "is_admin": False},
    "custom": {"modules": [], "view_only": False, "is_admin": False},
}


def get_access_permissions():
    """codename -> Permission object for the SchoolSoft module permissions."""
    perms = Permission.objects.filter(
        content_type__app_label="core",
        content_type__model="moduleaccess",
    )
    return {p.codename: p for p in perms}


def apply_permissions(user, module_keys, view_only, is_admin):
    perms = get_access_permissions()
    codes = {"access_dashboard"}
    if is_admin:
        codes.add("access_all_modules")
        codes.update(MODULE_PERMISSIONS[k] for k in ALL_KEYS)
    else:
        codes.update(MODULE_PERMISSIONS[k] for k in module_keys if k in MODULE_PERMISSIONS)

    user.user_permissions.set([perms[c] for c in codes if c in perms])

    user.groups.clear()
    if view_only and not is_admin:
        readonly_group, _ = Group.objects.get_or_create(name=READONLY_GROUP)
        user.groups.add(readonly_group)


def describe_user(user):
    """Short access summary for the list screen."""
    if user.is_superuser:
        return "Superuser", False
    if user.has_perm("core.access_all_modules"):
        return "Administrator", False
    readonly = user.groups.filter(name=READONLY_GROUP).exists()
    granted = [label for key, label in MODULES_UI if user.has_perm(f"core.{MODULE_PERMISSIONS[key]}")]
    if readonly:
        return "Viewer (read / print) · " + (", ".join(granted) if granted else "no modules"), True
    if not granted:
        return "No modules", False
    return ", ".join(granted), False


def current_modules(user):
    return [key for key in ALL_KEYS if user.has_perm(f"core.{MODULE_PERMISSIONS[key]}")]


@manage_users_required
def user_list(request):
    rows = []
    for user in User.objects.order_by("username"):
        summary, readonly = describe_user(user)
        rows.append({
            "obj": user,
            "summary": summary,
            "readonly": readonly,
            "is_admin": user.is_superuser or user.has_perm("core.access_all_modules"),
        })
    return render(request, "core/users_list.html", {"rows": rows})


@manage_users_required
def user_create(request):
    context = {
        "modules": MODULES_UI,
        "roles": ROLE_LABELS,
        "presets_json": json.dumps(ROLE_PRESETS),
        "editing": False,
        "form": {"username": "", "first_name": "", "role": "custom",
                 "modules": [], "view_only": False, "is_active": True},
    }

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        first_name = (request.POST.get("first_name") or "").strip()
        password = request.POST.get("password") or ""
        role = request.POST.get("role") or "custom"
        selected = request.POST.getlist("modules")
        view_only = bool(request.POST.get("view_only"))
        is_admin = role == "admin"

        context["form"] = {"username": username, "first_name": first_name, "role": role,
                           "modules": selected, "view_only": view_only, "is_active": True}

        errors = []
        if not username:
            errors.append("Username is required.")
        elif User.objects.filter(username__iexact=username).exists():
            errors.append("That username is already taken.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")

        if errors:
            context["errors"] = errors
            return render(request, "core/user_form.html", context)

        user = User.objects.create_user(username=username, password=password, first_name=first_name)
        user.is_active = True
        user.save()
        apply_permissions(user, selected, view_only, is_admin)
        messages.success(request, f"User '{username}' created.")
        return redirect(reverse("core:user_list"))

    return render(request, "core/user_form.html", context)


@manage_users_required
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        first_name = (request.POST.get("first_name") or "").strip()
        role = request.POST.get("role") or "custom"
        selected = request.POST.getlist("modules")
        view_only = bool(request.POST.get("view_only"))
        is_active = bool(request.POST.get("is_active"))
        is_admin = role == "admin"

        user.first_name = first_name
        # Never let an admin lock themselves out of their own account.
        if user.pk == request.user.pk:
            is_active = True
        user.is_active = is_active
        user.save()

        if not user.is_superuser:
            apply_permissions(user, selected, view_only, is_admin)
        messages.success(request, f"Updated '{user.username}'.")
        return redirect(reverse("core:user_list"))

    readonly = user.groups.filter(name=READONLY_GROUP).exists()
    context = {
        "modules": MODULES_UI,
        "roles": ROLE_LABELS,
        "presets_json": json.dumps(ROLE_PRESETS),
        "editing": True,
        "target": user,
        "form": {
            "username": user.username,
            "first_name": user.first_name,
            "role": "admin" if user.has_perm("core.access_all_modules") else "custom",
            "modules": current_modules(user),
            "view_only": readonly,
            "is_active": user.is_active,
        },
    }
    return render(request, "core/user_form.html", context)


@manage_users_required
def user_reset_password(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        password = request.POST.get("password") or ""
        if len(password) < 6:
            messages.error(request, "Password must be at least 6 characters.")
        else:
            user.set_password(password)
            user.save()
            messages.success(request, f"Password reset for '{user.username}'.")
    return redirect(reverse("core:user_list"))


@manage_users_required
def user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        if user.pk == request.user.pk:
            messages.error(request, "You cannot deactivate your own account.")
        else:
            user.is_active = not user.is_active
            user.save(update_fields=["is_active"])
            messages.success(request, f"'{user.username}' is now {'active' if user.is_active else 'inactive'}.")
    return redirect(reverse("core:user_list"))
