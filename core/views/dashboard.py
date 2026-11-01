import datetime as dt
from collections import Counter, defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from ..models import Assignment, Faculty, User
from ..utils import WEEKDAYS, WEEKDAYS_SHORT, month_grid, month_title, parse_date, shift_month

# Kalendar katakchasida bir tyutorning bir nechta ijrosi bo'lsa, eng "xavfli"
# holat rangi ko'rsatiladi.
STATUS_PRIORITY = {"overdue": 0, "rejected": 1, "pending": 2, "submitted": 3, "approved": 4}
MAX_NAMES_IN_CELL = 4


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _base_queryset(request, faculty_id):
    qs = Assignment.objects.select_related("task", "tutor", "tutor__faculty")
    if request.user.is_head:
        qs = qs.filter(tutor__is_active=True)
        if faculty_id:
            qs = qs.filter(tutor__faculty_id=faculty_id)
    else:
        qs = qs.filter(tutor=request.user)
    return qs


def _day_of(assignment, by):
    if by == "deadline":
        return timezone.localtime(assignment.task.deadline).date()
    return assignment.task.execution_date


@login_required
def dashboard(request):
    if request.user.is_qalqon_only:
        return redirect("qalqon:calendar")
    today = timezone.localdate()
    by = "deadline" if request.GET.get("by") == "deadline" else "exec"
    year = _int(request.GET.get("y"), today.year)
    month = _int(request.GET.get("m"), today.month)
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        year, month = today.year, today.month

    selected = parse_date(request.GET.get("date"))
    if selected is None:
        selected = today if (today.year, today.month) == (year, month) else dt.date(year, month, 1)
    faculty_id = _int(request.GET.get("faculty"), None) if request.user.is_head else None
    tutor_id = _int(request.GET.get("tutor"), None)
    query = request.GET.get("q", "").strip()

    weeks = month_grid(year, month)
    grid_start, grid_end = weeks[0][0], weeks[-1][-1]

    qs = _base_queryset(request, faculty_id)
    if by == "deadline":
        month_qs = qs.filter(task__deadline__date__range=(grid_start, grid_end))
    else:
        month_qs = qs.filter(task__execution_date__range=(grid_start, grid_end))

    by_day = defaultdict(list)
    for a in month_qs:
        by_day[_day_of(a, by)].append(a)

    calendar_weeks = []
    for week in weeks:
        row = []
        for day in week:
            items = by_day.get(day, [])
            counts = Counter(a.display_status for a in items)
            cell = {
                "date": day,
                "in_month": day.month == month,
                "is_today": day == today,
                "is_selected": day == selected,
                "is_weekend": day.weekday() >= 5,
                "counts": counts,
                "total": len(items),
            }
            if request.user.is_head:
                per_tutor = {}
                for a in items:
                    entry = per_tutor.setdefault(a.tutor_id, {"tutor": a.tutor, "count": 0, "status": "approved"})
                    entry["count"] += 1
                    if STATUS_PRIORITY[a.display_status] < STATUS_PRIORITY[entry["status"]]:
                        entry["status"] = a.display_status
                names = sorted(per_tutor.values(), key=lambda e: (STATUS_PRIORITY[e["status"]], e["tutor"].last_name))
                cell["names"] = names[:MAX_NAMES_IN_CELL]
                cell["more"] = max(0, len(names) - MAX_NAMES_IN_CELL)
            else:
                ordered = sorted(items, key=lambda a: STATUS_PRIORITY[a.display_status])
                cell["tasks"] = ordered[:3]
                cell["more"] = max(0, len(ordered) - 3)
            row.append(cell)
        calendar_weeks.append(row)

    # O'ng panel — tanlangan kun ijrolari
    if by == "deadline":
        day_qs = qs.filter(task__deadline__date=selected)
    else:
        day_qs = qs.filter(task__execution_date=selected)
    selected_tutor = None
    if tutor_id and request.user.is_head:
        selected_tutor = User.objects.filter(pk=tutor_id, role=User.Role.TUTOR).select_related("faculty").first()
        if selected_tutor:
            day_qs = day_qs.filter(tutor=selected_tutor)
    if query:
        day_qs = day_qs.filter(
            Q(task__title__icontains=query)
            | Q(task__description__icontains=query)
            | Q(tutor__first_name__icontains=query)
            | Q(tutor__last_name__icontains=query)
            | Q(task__pk=_int(query.lstrip("№#0") or "0", 0))
        )
    day_items = sorted(day_qs, key=lambda a: (STATUS_PRIORITY[a.display_status], a.task.deadline, a.tutor.last_name))
    day_counts = Counter(a.display_status for a in day_items)

    # Yuqoridagi statistika — joriy oy
    month_items = [a for d, items in by_day.items() if d.month == month for a in items]
    month_counts = Counter(a.display_status for a in month_items)

    prev_y, prev_m = shift_month(year, month, -1)
    next_y, next_m = shift_month(year, month, 1)
    context = {
        "year": year,
        "month": month,
        "title": month_title(year, month),
        "weeks": calendar_weeks,
        "weekdays": list(zip(WEEKDAYS, WEEKDAYS_SHORT)),
        "prev": {"y": prev_y, "m": prev_m},
        "next": {"y": next_y, "m": next_m},
        "today": today,
        "selected": selected,
        "selected_tutor": selected_tutor,
        "day_items": day_items,
        "day_counts": day_counts,
        "month_counts": month_counts,
        "month_total": len(month_items),
        "by": by,
        "query": query,
        "faculty_id": faculty_id,
        "faculties": Faculty.objects.all() if request.user.is_head else [],
    }
    return render(request, "dashboard.html", context)
