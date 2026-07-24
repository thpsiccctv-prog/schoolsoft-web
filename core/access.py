import os
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def is_online_deployment():
    """True on Render (online read-only deployment); False on desktop EXE."""
    return bool(os.environ.get("RENDER_EXTERNAL_HOSTNAME"))


MODULE_PERMISSIONS = {
    "dashboard": "access_dashboard",
    "students": "access_students",
    "fee_collection": "access_fee_collection",
    "receipts": "access_receipts",
    "dues": "access_dues",
    "collection": "access_collection",
    "fee_setup": "access_fee_setup",
    "marks": "access_marks",
    "staff": "access_staff",
    "transport": "access_transport",
    "school_profile": "access_school_profile",
    "accounts": "access_accounts",
    "inventory": "access_inventory",
    "family": "access_family",
}

# Membership in this group marks a user as "view / print only": they keep read
# access to whatever modules they are granted, but every write action (create,
# edit, delete, save) is blocked. Seeded by migration 0008.
READONLY_GROUP = "SchoolSoft Read Only"


def user_is_readonly(user):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return False
    return user.groups.filter(name=READONLY_GROUP).exists()


def user_can_manage_users(user):
    """Only full administrators may open the Users & Permissions screen."""
    if not getattr(user, "is_authenticated", False):
        return False
    return user.is_superuser or user.has_perm("core.access_all_modules")


def user_can_access(user, module):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    codename = MODULE_PERMISSIONS.get(module)
    if not codename:
        return False
    return user.has_perm(f"core.{codename}") or user.has_perm("core.access_all_modules")


def module_required(module, write=False):
    """Guard a view by module access.

    write=True additionally blocks read-only (Viewer) users, so create / edit /
    delete pages cannot be reached by someone who may only view and print.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not user_can_access(request.user, module):
                return render(
                    request,
                    "core/permission_denied.html",
                    {"module_name": module.replace("_", " ").title()},
                    status=403,
                )
            if write and user_is_readonly(request.user):
                return render(
                    request,
                    "core/permission_denied.html",
                    {
                        "module_name": module.replace("_", " ").title(),
                        "readonly": True,
                    },
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def manage_users_required(view_func):
    """Guard the in-app Users & Permissions screen (administrators only)."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_manage_users(request.user):
            return render(
                request,
                "core/permission_denied.html",
                {"module_name": "Users & Permissions"},
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def admin_only_required(module_name):
    """Guard a view so only full administrators (superuser or
    access_all_modules) can reach it - not assignable to any role preset.
    Used for Discipline Records: owner wants this strictly Admin/Principal
    only, unlike the per-module MODULE_PERMISSIONS which fee/exam/staff/
    viewer roles can be granted."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not user_can_manage_users(request.user):
                return render(
                    request,
                    "core/permission_denied.html",
                    {"module_name": module_name},
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def access_context(request):
    user = getattr(request, "user", None)
    return {
        "access": {
            module: user_can_access(user, module)
            for module in MODULE_PERMISSIONS
        },
        "can_manage_users": user_can_manage_users(user) if user is not None else False,
        "is_readonly": user_is_readonly(user) if user is not None else False,
        "is_online_deployment": is_online_deployment(),
    }
