from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def can_view_qalqon(user):
    return user.is_authenticated and (user.is_qalqon_staff or user.is_qalqon_member)


def _make(check):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not check(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


qalqon_required = _make(can_view_qalqon)
staff_required = _make(lambda u: u.is_qalqon_staff)  # sardor yoki admin
admin_required = _make(lambda u: u.is_qalqon_admin)
