from .models import Assignment


def sidebar(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    ctx = {"unread_count": user.notifications.filter(is_read=False).count()}
    if user.is_qalqon_staff or user.is_qalqon_member:
        from django.utils import timezone

        from qalqon.models import DutyMember

        ctx["qalqon_today"] = DutyMember.objects.filter(
            member=user, duty__date=timezone.localdate()
        ).exclude(status=DutyMember.Status.FINISHED).count()
    if user.is_qalqon_only:
        return ctx
    if user.is_head:
        ctx["review_count"] = Assignment.objects.filter(status=Assignment.Status.SUBMITTED).count()
    else:
        ctx["open_count"] = user.assignments.filter(
            status__in=[Assignment.Status.PENDING, Assignment.Status.REJECTED]
        ).count()
    return ctx
