from . import platform as pf
from .models import Assignment


def sidebar(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    current = pf.current(request)
    platforms = pf.available(user)
    ctx = {
        "platform": current,
        "platforms": platforms,
        "unread_count": pf.notifications_for(user, current).filter(is_read=False).count(),
    }
    if len(platforms) > 1:
        other = pf.QALQON if current == pf.IJRO else pf.IJRO
        ctx["other_platform"] = other
        ctx["other_unread"] = pf.notifications_for(user, other).filter(is_read=False).count()

    if current == pf.QALQON:
        from django.utils import timezone

        from qalqon.models import DutyMember

        ctx["qalqon_today"] = DutyMember.objects.filter(
            member=user, duty__date=timezone.localdate()
        ).exclude(status=DutyMember.Status.FINISHED).count()
    elif user.is_head:
        ctx["review_count"] = Assignment.objects.filter(status=Assignment.Status.SUBMITTED).count()
    else:
        ctx["open_count"] = user.assignments.filter(
            status__in=[Assignment.Status.PENDING, Assignment.Status.REJECTED]
        ).count()
    return ctx
