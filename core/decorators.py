from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def head_required(view):
    """Faqat bo'lim boshlig'i (yoki superuser) uchun."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_head:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def faculty_manager_required(view):
    """Fakultetlar ma'lumotnomasi: bo'lim boshlig'i va Qalqon sardori/admini."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_head or request.user.is_qalqon_staff):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
