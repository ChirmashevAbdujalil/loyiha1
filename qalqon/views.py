"""Qalqon: kalendar, naryadlar, naryadni boshlash / yakunlash, qonunbuzarliklar."""
import datetime as dt
import mimetypes
from collections import Counter

from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Faculty, User
from core.utils import WEEKDAYS, WEEKDAYS_SHORT, month_grid, month_title, parse_date, shift_month

from . import services
from .decorators import qalqon_required, staff_required
from .forms import DutyForm, FinishForm, LocationForm, ViolationForm
from .models import Building, Duty, DutyMember, LocationLog, Violation, qalqon_conf

# Kalendar katagidagi naryad rangi — eng "muhim" holat bo'yicha
DUTY_PRIORITY = {"missed": 0, "unfinished": 1, "active": 2, "today": 3, "scheduled": 4, "finished": 5}


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _calendar_url(day):
    return f"{reverse('qalqon:calendar')}?y={day.year}&m={day.month}&date={day:%Y-%m-%d}"


def _duty_status(duty_members):
    if not duty_members:
        return "scheduled"
    return min((dm.display_status for dm in duty_members), key=lambda s: DUTY_PRIORITY[s])


# ---------------------------------------------------------------- kalendar

@qalqon_required
def calendar(request):
    today = timezone.localdate()
    year = _int(request.GET.get("y"), today.year)
    month = _int(request.GET.get("m"), today.month)
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        year, month = today.year, today.month
    selected = parse_date(request.GET.get("date"))
    if selected is None:
        selected = today if (today.year, today.month) == (year, month) else dt.date(year, month, 1)
    member_id = _int(request.GET.get("member"))
    building_id = _int(request.GET.get("building"))
    mine = request.GET.get("mine") == "1"

    weeks = month_grid(year, month)
    duties = (
        Duty.objects.filter(date__range=(weeks[0][0], weeks[-1][-1]))
        .select_related("building")
        .prefetch_related("duty_members__member__qalqon_profile", "duty_members__duty")
        .order_by("date", "start_time")
    )
    if building_id:
        duties = duties.filter(building_id=building_id)
    if mine:
        duties = duties.filter(duty_members__member=request.user)
    if member_id:
        duties = duties.filter(duty_members__member_id=member_id)
    duties = list(duties.distinct())

    by_day = {}
    for d in duties:
        d.dms = list(d.duty_members.all())
        d.status = _duty_status(d.dms)
        d.is_mine = any(dm.member_id == request.user.pk for dm in d.dms)
        by_day.setdefault(d.date, []).append(d)

    calendar_weeks = [
        [
            {
                "date": day,
                "in_month": day.month == month,
                "is_today": day == today,
                "is_selected": day == selected,
                "is_weekend": day.weekday() >= 5,
                "duties": by_day.get(day, [])[:3],
                "more": max(0, len(by_day.get(day, [])) - 3),
            }
            for day in week
        ]
        for week in weeks
    ]

    day_duties = by_day.get(selected, [])
    month_dms = [dm for d in duties if d.date.month == month for dm in d.dms]
    my_today = (
        DutyMember.objects.filter(member=request.user, duty__date=today).select_related("duty", "duty__building").first()
    )

    prev_y, prev_m = shift_month(year, month, -1)
    next_y, next_m = shift_month(year, month, 1)
    return render(request, "qalqon/calendar.html", {
        "title": month_title(year, month),
        "weeks": calendar_weeks,
        "weekdays": list(zip(WEEKDAYS, WEEKDAYS_SHORT)),
        "prev": {"y": prev_y, "m": prev_m},
        "next": {"y": next_y, "m": next_m},
        "today": today,
        "selected": selected,
        "day_duties": day_duties,
        "month_duties": sum(1 for d in duties if d.date.month == month),
        "month_counts": Counter(dm.display_status for dm in month_dms),
        "buildings": Building.objects.filter(is_active=True),
        "building_id": building_id,
        "selected_member": User.objects.filter(pk=member_id).first() if member_id else None,
        "mine": mine,
        "my_today": my_today,
    })


# ---------------------------------------------------------------- a'zo sahifasi

@qalqon_required
def my_duties(request):
    dms = list(
        DutyMember.objects.filter(member=request.user)
        .select_related("duty", "duty__building")
        .annotate(v_count=Count("violations"))
        .order_by("-duty__date", "-duty__start_time")
    )
    today = timezone.localdate()
    current = [dm for dm in dms if dm.status == DutyMember.Status.ACTIVE and dm.display_status == "active"]
    current += [dm for dm in dms if dm.duty.date == today and dm not in current]
    upcoming = sorted([dm for dm in dms if dm.duty.date > today], key=lambda x: (x.duty.date, x.duty.start_time))
    history = [dm for dm in dms if dm.duty.date < today and dm not in current]
    counts = Counter(dm.display_status for dm in dms)
    return render(request, "qalqon/my_duties.html", {
        "current": current, "upcoming": upcoming, "history": history, "counts": counts, "total": len(dms),
    })


# ---------------------------------------------------------------- naryadlar (sardor)

@staff_required
def duty_list(request):
    today = timezone.localdate()
    date_from = parse_date(request.GET.get("from"), today - dt.timedelta(days=30))
    date_to = parse_date(request.GET.get("to"), today + dt.timedelta(days=30))
    building_id = _int(request.GET.get("building"))
    duties = (
        Duty.objects.filter(date__range=(date_from, date_to))
        .select_related("building", "created_by")
        .prefetch_related("duty_members__member", "duty_members__duty")
        .annotate(v_count=Count("duty_members__violations", distinct=True))
        .order_by("-date", "start_time")
    )
    if building_id:
        duties = duties.filter(building_id=building_id)
    duties = list(duties)
    for d in duties:
        d.dms = list(d.duty_members.all())
        d.status = _duty_status(d.dms)
        d.counts = sorted(Counter(dm.display_status for dm in d.dms).items(), key=lambda x: DUTY_PRIORITY[x[0]])
    return render(request, "qalqon/duty_list.html", {
        "duties": duties, "date_from": date_from, "date_to": date_to,
        "buildings": Building.objects.all(), "building_id": building_id,
    })


def _member_groups(form, busy_ids=()):
    selected = {str(v) for v in (form["members"].value() or [])}
    groups = {}
    for u in form.fields["members"].queryset:
        u.checked = str(u.pk) in selected
        u.busy = u.pk in busy_ids
        u.profile = getattr(u, "qalqon_profile", None)
        groups.setdefault(u.faculty, []).append(u)
    return list(groups.items())


def _form_context(form, duty=None):
    return {
        "form": form,
        "duty": duty,
        "groups": _member_groups(form),
        "faculties": Faculty.objects.all(),
        "buildings_json": [
            {"id": b.pk, "lat": float(b.latitude), "lng": float(b.longitude), "radius": b.radius_m, "name": b.name}
            for b in Building.objects.filter(is_active=True)
        ],
    }


@staff_required
def duty_create(request):
    form = DutyForm(request.POST or None)
    if not request.POST:
        if request.GET.get("date"):
            form.initial["date"] = request.GET["date"]
        if request.GET.get("building"):
            form.initial["building"] = request.GET["building"]
    if request.method == "POST" and form.is_valid():
        members = list(form.cleaned_data["members"])
        created = []
        with transaction.atomic():
            for day in form.dates():
                duty = Duty.objects.create(
                    date=day,
                    created_by=request.user,
                    **{f: form.cleaned_data[f] for f in
                       ("start_time", "end_time", "building", "latitude", "longitude", "radius_m", "note")},
                )
                dms = [DutyMember.objects.create(duty=duty, member=m) for m in members]
                services.notify_duty_assigned(dms)
                created.append(duty)
        if len(created) == 1:
            messages.success(request, f"Naryad qo'yildi: {len(members)} ta a'zoga bildirishnoma yuborildi.")
            return redirect(created[0])
        messages.success(request, f"{len(created)} kunga naryad qo'yildi ({len(members)} ta a'zo).")
        return redirect(_calendar_url(created[0].date))
    return render(request, "qalqon/duty_form.html", _form_context(form))


@staff_required
def duty_edit(request, pk):
    duty = get_object_or_404(Duty, pk=pk)
    form = DutyForm(request.POST or None, instance=duty)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            selected = {u.pk: u for u in form.cleaned_data["members"]}
            existing = {dm.member_id: dm for dm in duty.duty_members.select_related("member")}
            removed, kept = [], []
            for mid, dm in existing.items():
                if mid in selected:
                    continue
                if dm.status != DutyMember.Status.SCHEDULED:
                    kept.append(dm.member.full_name)
                else:
                    removed.append(dm.member)
                    dm.delete()
            new = [DutyMember.objects.create(duty=duty, member=u) for mid, u in selected.items() if mid not in existing]
            services.notify_duty_changed(duty, removed)
        messages.success(request, "Naryad saqlandi.")
        if kept:
            messages.warning(request, "Naryadni boshlagan a'zolar olib tashlanmadi: " + ", ".join(kept))
        if new:
            messages.info(request, f"{len(new)} ta yangi a'zo qo'shildi.")
        return redirect(duty)
    return render(request, "qalqon/duty_form.html", _form_context(form, duty))


@staff_required
@require_POST
def duty_delete(request, pk):
    duty = get_object_or_404(Duty, pk=pk)
    if duty.duty_members.exclude(status=DutyMember.Status.SCHEDULED).exists():
        messages.error(request, "Bu naryad boshlangan — uni o'chirib bo'lmaydi.")
        return redirect(duty)
    services.notify_duty_changed(
        duty, [dm.member for dm in duty.duty_members.select_related("member")], notify_current=False
    )
    d = duty.date
    duty.delete()
    messages.success(request, "Naryad o'chirildi.")
    return redirect(_calendar_url(d))


@staff_required
def busy_members(request):
    """Tanlangan sanada boshqa naryadda bo'lgan a'zolar (forma uchun)."""
    day = parse_date(request.GET.get("date"))
    exclude = _int(request.GET.get("exclude"))
    if not day:
        return JsonResponse({"busy": []})
    qs = DutyMember.objects.filter(duty__date=day)
    if exclude:
        qs = qs.exclude(duty_id=exclude)
    return JsonResponse({"busy": list(qs.values_list("member_id", flat=True))})


# ---------------------------------------------------------------- naryad sahifasi

def _get_duty_for(request, pk):
    duty = get_object_or_404(Duty.objects.select_related("building", "created_by"), pk=pk)
    is_staff = request.user.is_qalqon_staff
    my_dm = duty.duty_members.filter(member=request.user).select_related("duty", "duty__building").first()
    return duty, is_staff, my_dm


@qalqon_required
def duty_detail(request, pk):
    duty, is_staff, my_dm = _get_duty_for(request, pk)
    dms = list(
        duty.duty_members.select_related("member", "member__faculty", "member__qalqon_profile", "duty")
        .annotate(v_count=Count("violations"))
    )
    if is_staff:
        violations = Violation.objects.filter(duty_member__duty=duty)
    elif my_dm:
        violations = my_dm.violations.all()
    else:
        violations = Violation.objects.none()
    violations = violations.select_related("faculty", "dormitory", "tutor", "duty_member__member")
    logs = []
    if is_staff:
        logs = LocationLog.objects.filter(duty_member__duty=duty).select_related("duty_member__member")[:50]
    return render(request, "qalqon/duty_detail.html", {
        "duty": duty,
        "dms": dms,
        "my_dm": my_dm,
        "is_staff": is_staff,
        "violations": violations,
        "logs": logs,
        "status": _duty_status(dms),
        "max_accuracy": qalqon_conf()["max_gps_accuracy"],
    })


def _own_dm(request, pk):
    dm = get_object_or_404(DutyMember.objects.select_related("duty", "duty__building", "member"), pk=pk)
    if dm.member_id != request.user.pk:
        raise PermissionDenied
    return dm


START_MESSAGES = {
    "not_today": "Naryadni faqat navbat kuni boshlash mumkin.",
    "too_early": "Naryadni boshlashga hali erta.",
    "too_late": "Naryad vaqti tugagan — uni endi boshlab bo'lmaydi.",
    "done": "Naryad allaqachon boshlangan.",
}


@qalqon_required
@require_POST
def duty_start(request, pk):
    dm = _own_dm(request, pk)
    state = dm.start_state
    if state != "ok":
        messages.error(request, START_MESSAGES[state])
        return redirect(dm)
    form = LocationForm(request.POST)
    if not form.is_valid():
        for errs in form.errors.values():
            messages.error(request, errs[0])
        return redirect(dm)
    lat, lng, acc = form.cleaned_data["latitude"], form.cleaned_data["longitude"], form.cleaned_data["accuracy"]
    ok, distance, msg = services.check_location(
        dm, "start", lat, lng, acc, request.META.get("HTTP_USER_AGENT", "")
    )
    if not ok:
        messages.error(request, "Naryad boshlanmadi. " + msg)
        return redirect(dm)
    dm.status = DutyMember.Status.ACTIVE
    dm.started_at = timezone.now()
    dm.start_lat, dm.start_lng = round(lat, 6), round(lng, 6)
    dm.start_accuracy, dm.start_distance = acc, distance
    dm.save()
    messages.success(request, f"Naryad boshlandi! {msg} Qonunbuzarliklarni shu sahifada qayd eting.")
    return redirect(dm)


FINISH_MESSAGES = {
    "not_started": "Naryad boshlanmagan.",
    "too_early": "Naryadni faqat tugash vaqtidan keyin yakunlash mumkin.",
    "too_late": "Naryadni yakunlash muddati o'tib ketgan. Sardorga murojaat qiling.",
    "done": "Naryad allaqachon yakunlangan.",
}


@qalqon_required
def duty_finish(request, pk):
    dm = _own_dm(request, pk)
    state = dm.finish_state
    if state != "ok":
        messages.error(request, FINISH_MESSAGES[state])
        return redirect(dm)
    violations = dm.violations.select_related("faculty", "dormitory", "tutor")
    form = FinishForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if form.is_valid():
            cd = form.cleaned_data
            ok, distance, msg = services.check_location(
                dm, "finish", cd["latitude"], cd["longitude"], cd["accuracy"],
                request.META.get("HTTP_USER_AGENT", ""),
            )
            if ok:
                now = timezone.now()
                with transaction.atomic():
                    dm.status = DutyMember.Status.FINISHED
                    dm.finished_at = now
                    dm.finish_lat, dm.finish_lng = round(cd["latitude"], 6), round(cd["longitude"], 6)
                    dm.finish_accuracy, dm.finish_distance = cd["accuracy"], distance
                    dm.photo = cd["photo"]
                    dm.finish_note = cd["finish_note"]
                    dm.save()
                    dm.violations.update(confirmed_at=now)
                messages.success(request, f"Naryad yakunlandi. Rahmat! {msg}")
                return redirect(dm)
            form.add_error(None, "Naryad yakunlanmadi. " + msg)
    return render(request, "qalqon/duty_finish.html", {
        "dm": dm, "duty": dm.duty, "form": form, "violations": violations,
        "max_accuracy": qalqon_conf()["max_gps_accuracy"],
    })


# ---------------------------------------------------------------- qonunbuzarliklar

def _editable_violation(request, pk):
    v = get_object_or_404(Violation.objects.select_related("duty_member__duty__building"), pk=pk)
    if v.duty_member.member_id != request.user.pk or not v.duty_member.can_add_violation:
        raise PermissionDenied
    return v


@qalqon_required
def violation_add(request, pk):
    dm = _own_dm(request, pk)
    if not dm.can_add_violation:
        messages.error(request, "Qonunbuzarlikni faqat naryad davomida (boshlangandan keyin) kiritish mumkin.")
        return redirect(dm)
    form = ViolationForm(request.POST or None, request.FILES or None, duty=dm.duty)
    if request.method == "POST" and form.is_valid():
        v = form.save(commit=False)
        v.duty_member = dm
        v.save()
        services.notify_violation(v)
        messages.success(request, f"Qonunbuzarlik qayd etildi: {v.student_name}.")
        if "add_another" in request.POST:
            return redirect("qalqon:violation_add", pk=dm.pk)
        return redirect(dm)
    return render(request, "qalqon/violation_form.html", {"form": form, "dm": dm, "duty": dm.duty,
                                                           "tutor_faculties": _tutor_faculty_map()})


@qalqon_required
def violation_edit(request, pk):
    v = _editable_violation(request, pk)
    dm = v.duty_member
    form = ViolationForm(request.POST or None, request.FILES or None, instance=v, duty=dm.duty)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Qonunbuzarlik ma'lumotlari saqlandi.")
        return redirect(_safe_next(request, dm.get_absolute_url()))
    return render(request, "qalqon/violation_form.html", {"form": form, "dm": dm, "duty": dm.duty, "violation": v,
                                                           "tutor_faculties": _tutor_faculty_map()})


@qalqon_required
@require_POST
def violation_delete(request, pk):
    v = _editable_violation(request, pk)
    dm = v.duty_member
    if v.photo:
        v.photo.delete(save=False)
    v.delete()
    messages.success(request, "Qonunbuzarlik o'chirildi.")
    return redirect(_safe_next(request, dm.get_absolute_url()))


def _safe_next(request, default):
    nxt = request.POST.get("next") or ""
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else default


def _tutor_faculty_map():
    return {u.pk: u.faculty_id for u in User.objects.filter(role=User.Role.TUTOR).only("pk", "faculty_id")}


# ---------------------------------------------------------------- fayllar

def _serve(field):
    if not field:
        raise Http404
    try:
        handle = field.open("rb")
    except FileNotFoundError:
        raise Http404("Fayl topilmadi")
    name = field.name.rsplit("/", 1)[-1]
    return FileResponse(handle, content_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
                        filename=name)


@qalqon_required
def duty_photo(request, pk):
    dm = get_object_or_404(DutyMember, pk=pk)
    if not (request.user.is_qalqon_staff or dm.member_id == request.user.pk):
        raise PermissionDenied
    return _serve(dm.photo)


@qalqon_required
def violation_photo(request, pk):
    v = get_object_or_404(Violation.objects.select_related("duty_member"), pk=pk)
    if not (request.user.is_qalqon_staff or v.duty_member.member_id == request.user.pk):
        raise PermissionDenied
    return _serve(v.photo)


# ---------------------------------------------------------------- kirish va GPS tekshiruvi

class QalqonLoginView(LoginView):
    """Qalqon platformasining alohida kirish sahifasi."""

    template_name = "qalqon/login.html"
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        user = self.request.user
        if user.is_qalqon_staff or user.is_qalqon_member:
            return reverse("qalqon:calendar")
        return reverse("dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session["platform"] = "qalqon"
        return response


@qalqon_required
def gps_check(request):
    """A'zo telefoni joylashuvni to'g'ri aniqlayotganini sinash sahifasi (hech narsa saqlanmaydi)."""
    buildings = [
        {"name": b.name, "lat": float(b.latitude), "lng": float(b.longitude), "radius": b.radius_m}
        for b in Building.objects.filter(is_active=True)
    ]
    return render(request, "qalqon/gps_check.html", {
        "buildings_json": buildings, "max_accuracy": qalqon_conf()["max_gps_accuracy"],
    })
