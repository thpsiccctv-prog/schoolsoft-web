from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


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
}


def user_can_access(user, module):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    codename = MODULE_PERMISSIONS.get(module)
    if not codename:
        return False
    return user.has_perm(f"core.{codename}") or user.has_perm("core.access_all_modules")


def module_required(module):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if user_can_access(request.user, module):
                return view_func(request, *args, **kwargs)
            return render(
                request,
                "core/permission_denied.html",
                {"module_name": module.replace("_", " ").title()},
                status=403,
            )

        return wrapper

    return decorator


def access_context(request):
    user = getattr(request, "user", None)
    return {
        "access": {
            module: user_can_access(user, module)
            for module in MODULE_PERMISSIONS
        }
    }
