"""Qalqon: a'zolar, binolar, qonunbuzarliklar ro'yxati, statistika va eksport (sardor / admin)."""
from collections import Counter
from io import BytesIO

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Faculty, User
from core.utils import month_bounds, parse_date, uz_date, uz_datetime

from . import docx_import, services
from .decorators import admin_required, qalqon_required, staff_required
from .forms import BuildingForm, ImportForm, MemberForm
from .models import Building, DutyMember, MemberProfile, Violation

QALQON_ROLES = [User.Role.QALQON_MEMBER, User.Role.QALQON_LEADER, User.Role.QALQON_ADMIN]


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- a'zolar

@staff_required
def member_list(request):
    users = User.objects.filter(role__in=QALQON_ROLES).select_related("faculty", "qalqon_profile",
                                                                      "qalqon_profile__dormitory")
    faculty_id = _int(request.GET.get("faculty"))
    course = _int(request.GET.get("course"))
    role = request.GET.get("role", "")
    query = request.GET.get("q", "").strip()
    show = request.GET.get("show", "active")
    if faculty_id:
        users = users.filter(faculty_id=faculty_id)
    if course:
        users = users.filter(qalqon_profile__course=course)
    if role in dict(User.Role.choices):
        users = users.filter(role=role)
    if query:
        users = users.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(middle_name__icontains=query)
            | Q(phone__icontains=query) | Q(username__icontains=query)
            | Q(qalqon_profile__group_name__icontains=query) | Q(qalqon_profile__direction__icontains=query)
        )
    if show == "active":
        users = users.filter(is_active=True)
    elif show == "inactive":
        users = users.filter(is_active=False)
    users = list(users.order_by("faculty__name", "last_name", "first_name"))

    stats = {}
    for dm in DutyMember.objects.filter(member__in=users).select_related("duty"):
        s = stats.setdefault(dm.member_id, {"total": 0, "finished": 0, "missed": 0})
        s["total"] += 1
        st = dm.display_status
        if st == "finished":
            s["finished"] += 1
        elif st in ("missed", "unfinished"):
            s["missed"] += 1
    groups = {}
    for u in users:
        u.profile = getattr(u, "qalqon_profile", None)
        u.stats = stats.get(u.pk, {"total": 0, "finished": 0, "missed": 0})
        groups.setdefault(u.faculty, []).append(u)

    return render(request, "qalqon/member_list.html", {
        "groups": groups.items(),
        "total": len(users),
        "faculties": Faculty.objects.annotate(
            n=Count("tutors", filter=Q(tutors__role__in=QALQON_ROLES, tutors__is_active=True))
        ),
        "faculty_id": faculty_id,
        "course": course,
        "role": role,
        "query": query,
        "show": show,
        "roles": [(r, User.Role(r).label) for r in QALQON_ROLES],
        "courses": range(1, 7),
    })


def _check_can_edit(actor, user):
    if user.role not in QALQON_ROLES:
        raise PermissionDenied
    if not actor.is_qalqon_admin and user.role != User.Role.QALQON_MEMBER:
        raise PermissionDenied


@staff_required
def member_create(request):
    if not Faculty.objects.exists():
        messages.info(request, "Avval fakultetlarni qo'shing.")
        return redirect("faculty_list" if request.user.is_head else "qalqon:member_list")
    initial = {}
    if request.GET.get("faculty"):
        initial["faculty"] = request.GET["faculty"]
    form = MemberForm(request.POST or None, request.FILES or None, actor=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"{user.full_name} qo'shildi ({user.get_role_display()}). Login: {user.username}")
        if "add_another" in request.POST:
            return redirect(f"{request.path}?faculty={user.faculty_id}")
        return redirect("qalqon:member_list")
    return render(request, "qalqon/member_form.html", {"form": form})


@staff_required
def member_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    _check_can_edit(request.user, user)
    form = MemberForm(request.POST or None, request.FILES or None, instance=user, actor=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ma'lumotlar saqlandi.")
        return redirect("qalqon:member_detail", pk=user.pk)
    return render(request, "qalqon/member_form.html", {"form": form, "member": user})


@staff_required
def member_detail(request, pk):
    user = get_object_or_404(User.objects.select_related("faculty"), pk=pk, role__in=QALQON_ROLES)
    dms = list(
        DutyMember.objects.filter(member=user).select_related("duty", "duty__building")
        .annotate(v_count=Count("violations")).order_by("-duty__date")
    )
    counts = Counter(dm.display_status for dm in dms)
    return render(request, "qalqon/member_detail.html", {
        "member": user, "profile": getattr(user, "qalqon_profile", None), "dms": dms, "counts": counts,
        "violations_total": sum(dm.v_count for dm in dms),
    })


@staff_required
@require_POST
def member_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    _check_can_edit(request.user, user)
    if user.duty_memberships.exists():
        user.is_active = False
        user.save(update_fields=["is_active"])
        messages.warning(request, f"{user.full_name} naryadlarda qatnashgan — statistika saqlanishi uchun "
                                  "nofaol holatga o'tkazildi.")
    else:
        name = user.full_name
        user.delete()
        messages.success(request, f"{name} o'chirildi.")
    return redirect("qalqon:member_list")


@staff_required
def member_import(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    result = None
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        try:
            if upload.name.lower().endswith(".docx"):
                records = docx_import.parse_docx(upload)
                saved = docx_import.save_records(records)
                result = {
                    "created": saved["created"], "updated": saved["updated"], "skipped": [], "errors": [],
                    "new_faculties": saved["new_faculties"],
                    "warnings": [(r.number, r.full_name, w) for r in records for w in r.warnings],
                }
            else:
                rows = services.read_rows(upload)
                result = services.import_members(rows, create_faculties=bool(request.POST.get("create_faculties")))
        except Exception as exc:  # noqa: BLE001 — foydalanuvchiga tushunarli xabar
            form.add_error("file", f"Faylni o'qib bo'lmadi: {exc}")
        else:
            if result["created"]:
                # Loginlar faylini sessiyada saqlaymiz — bir marta yuklab olish uchun
                request.session["qalqon_credentials"] = [
                    {"id": c["user"].pk, "password": c["password"]} for c in result["created"] if c["password"]
                ]
            messages.success(request, f"{len(result['created'])} ta a'zo qo'shildi"
                                      + (f", {len(result['updated'])} tasi yangilandi." if result.get("updated") else "."))
    return render(request, "qalqon/member_import.html", {"form": form, "result": result})


@staff_required
def member_import_credentials(request):
    creds = request.session.get("qalqon_credentials") or []
    users = {u.pk: u for u in User.objects.filter(pk__in=[c["id"] for c in creds]).select_related("faculty")}
    created = [{"user": users[c["id"]], "password": c["password"]} for c in creds if c["id"] in users]
    if not created:
        messages.error(request, "Yuklab olinadigan loginlar yo'q.")
        return redirect("qalqon:member_import")
    wb = services.credentials_workbook(created)
    return _xlsx_response(wb, f"qalqon_loginlar_{timezone.localtime():%Y-%m-%d_%H-%M}.xlsx")


@staff_required
def member_import_template(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "A'zolar"
    ws.append(["Familiya", "Ism", "Otasining ismi", "Fakultet", "Yo'nalish", "Guruh", "Kurs", "Telefon",
               "TTJ", "Xona"])
    ws.append(["Karimov", "Jasur", "Akmalovich", "Iqtisodiyot fakulteti", "Iqtisodiyot", "21-03", 2,
               "+998901234567", "TTJ-1", "312"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1E1B4B")
    for col in "ABCDEFGHIJ":
        ws.column_dimensions[col].width = 20
    return _xlsx_response(wb, "qalqon_azolar_shablon.xlsx")


# ---------------------------------------------------------------- binolar

@staff_required
def building_list(request):
    buildings = Building.objects.annotate(
        duty_count=Count("duties", distinct=True),
        violation_count=Count("violations", distinct=True),
    )
    return render(request, "qalqon/building_list.html", {"buildings": buildings})


@staff_required
def building_form(request, pk=None):
    building = get_object_or_404(Building, pk=pk) if pk else None
    form = BuildingForm(request.POST or None, instance=building)
    if request.method == "POST" and form.is_valid():
        b = form.save()
        messages.success(request, f"«{b.name}» saqlandi.")
        return redirect("qalqon:building_list")
    return render(request, "qalqon/building_form.html", {"form": form, "building": building})


@staff_required
@require_POST
def building_delete(request, pk):
    b = get_object_or_404(Building, pk=pk)
    if b.duties.exists() or b.violations.exists():
        b.is_active = False
        b.save(update_fields=["is_active"])
        messages.warning(request, f"«{b.name}» naryadlarda ishlatilgan — nofaol holatga o'tkazildi.")
    else:
        b.delete()
        messages.success(request, f"«{b.name}» o'chirildi.")
    return redirect("qalqon:building_list")


# ---------------------------------------------------------------- filtrlar

def _period(request):
    today = timezone.localdate()
    first, last = month_bounds(today.year, today.month)
    date_from = parse_date(request.GET.get("from"), first)
    date_to = parse_date(request.GET.get("to"), last)
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def _violation_queryset(request):
    date_from, date_to = _period(request)
    qs = Violation.objects.filter(duty_member__duty__date__range=(date_from, date_to)).select_related(
        "faculty", "dormitory", "tutor", "duty_member__member", "duty_member__duty__building",
    )
    f = {
        "from": date_from, "to": date_to,
        "faculty": _int(request.GET.get("faculty")),
        "building": _int(request.GET.get("building")),
        "category": request.GET.get("category", ""),
        "course": _int(request.GET.get("course")),
        "q": request.GET.get("q", "").strip(),
    }
    if f["faculty"]:
        qs = qs.filter(faculty_id=f["faculty"])
    if f["building"]:
        qs = qs.filter(Q(dormitory_id=f["building"]) | Q(dormitory__isnull=True, duty_member__duty__building_id=f["building"]))
    if f["category"] in dict(Violation.Category.choices):
        qs = qs.filter(category=f["category"])
    if f["course"]:
        qs = qs.filter(course=f["course"])
    if f["q"]:
        qs = qs.filter(Q(student_name__icontains=f["q"]) | Q(group_name__icontains=f["q"])
                       | Q(room__icontains=f["q"]) | Q(description__icontains=f["q"]))
    return qs.order_by("-occurred_at"), f


@staff_required
def violation_list(request):
    qs, f = _violation_queryset(request)
    return render(request, "qalqon/violation_list.html", {
        "violations": qs[:500], "count": qs.count(), "f": f,
        "faculties": Faculty.objects.all(), "buildings": Building.objects.all(),
        "categories": Violation.Category.choices, "courses": range(1, 7),
        "query": request.GET.urlencode(),
    })


@staff_required
def violation_export(request):
    from openpyxl import Workbook

    qs, f = _violation_queryset(request)
    wb = Workbook()
    ws = wb.active
    ws.title = "Qonunbuzarliklar"
    _title(ws, "Qonunbuzarliklar ro'yxati", f"{uz_date(f['from'])} — {uz_date(f['to'])}", 15)
    headers = ["№", "Sana, vaqt", "Turi", "Talaba F.I.Sh", "Fakultet", "Yo'nalish", "Guruh", "Kurs", "TTJ",
               "Xona", "Tyutori", "Izoh", "Naryad joyi", "Qayd etgan a'zo", "Tasdiqlangan"]
    _header(ws, headers, 4)
    for i, v in enumerate(qs, 1):
        ws.append([
            i, timezone.localtime(v.occurred_at).strftime("%d.%m.%Y %H:%M"), v.get_category_display(),
            v.student_name, v.faculty.name, v.direction, v.group_name, v.course,
            v.dormitory.name if v.dormitory else "", v.room, v.tutor_display, v.description,
            v.duty_member.duty.building.name, v.duty_member.member.full_name, "ha" if v.confirmed_at else "yo'q",
        ])
    _widths(ws, [5, 16, 24, 30, 26, 20, 10, 6, 18, 8, 26, 50, 22, 26, 12])
    return _xlsx_response(wb, f"qonunbuzarliklar_{f['from']:%Y%m%d}_{f['to']:%Y%m%d}.xlsx")


# ---------------------------------------------------------------- statistika

@staff_required
def stats(request):
    date_from, date_to = _period(request)
    building_id = _int(request.GET.get("building"))
    faculty_id = _int(request.GET.get("faculty"))
    data = services.build_stats(date_from, date_to, building_id, faculty_id)
    data.pop("violations")
    data["violator_faculties"] = sorted({r["faculty"] for r in data["violators"]}, key=lambda f: f.name)
    return render(request, "qalqon/stats.html", {
        **data,
        "date_from": date_from, "date_to": date_to,
        "building_id": building_id, "faculty_id": faculty_id,
        "buildings": Building.objects.all(), "faculties": Faculty.objects.all(),
        "query": request.GET.urlencode(),
        "generated_at": timezone.now(),
    })


@staff_required
def stats_export(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    date_from, date_to = _period(request)
    data = services.build_stats(date_from, date_to, _int(request.GET.get("building")),
                                _int(request.GET.get("faculty")))
    period = f"{uz_date(date_from)} — {uz_date(date_to)} · {uz_datetime(timezone.now())} holatiga"
    wb = Workbook()

    ws = wb.active
    ws.title = "Umumiy"
    _title(ws, "Qalqon jamoatchilik guruhi — umumiy statistika", period, 4)
    sc = data["status_counts"]
    rows = [
        ("Naryadlar soni", data["duties_total"]),
        ("Navbatchiliklar (a'zo × naryad)", data["assignments_total"]),
        ("Yakunlangan", sc.get("finished", 0)),
        ("Chiqmagan", sc.get("missed", 0)),
        ("Boshlangan, yakunlanmagan", sc.get("unfinished", 0)),
        ("Kechikib boshlangan", data["late_starts"]),
        ("Intizom darajasi, %", data["discipline_rate"] if data["discipline_rate"] is not None else "—"),
        ("Qonunbuzarliklar", data["violations_total"]),
        ("Qonunbuzar talabalar", data["students_total"]),
    ]
    for r, (k, v) in enumerate(rows, 4):
        ws.cell(row=r, column=1, value=k).font = Font(bold=True)
        ws.cell(row=r, column=2, value=v)
    _widths(ws, [38, 14])

    green = PatternFill("solid", fgColor="DCF5E4")
    red = PatternFill("solid", fgColor="FDE2E1")
    amber = PatternFill("solid", fgColor="FDEED9")

    ws = wb.create_sheet("TTJ reytingi")
    _title(ws, "TTJlar intizom reytingi", period, 5)
    _header(ws, ["O'rin", "TTJ", "Qonunbuzarliklar", "Naryadlar", "Naryadga nisbatan"], 4)
    for r in data["dorm_rows"]:
        ws.append([r["rank"], r["building"].name, r["violations"], r["duties"],
                   r["per_duty"] if r["per_duty"] is not None else "—"])
        fill = {"good": green, "bad": red}.get(r["level"], amber)
        for c in ws[ws.max_row]:
            c.fill = fill
    _widths(ws, [8, 34, 18, 12, 20])

    for title, key in (("Turlar", "by_category"), ("Binolar", "by_place"), ("Fakultetlar", "by_faculty"),
                       ("Kurslar", "by_course"), ("Tyutorlar", "by_tutor")):
        ws = wb.create_sheet(title)
        _title(ws, f"Qonunbuzarliklar — {title.lower()} kesimida", period, 3)
        _header(ws, [title[:-3] if title.endswith("lar") else title, "Soni", "Ulushi, %"], 4)
        for row in data[key]:
            ws.append([str(row["label"]), row["count"], row["share"]])
        _widths(ws, [40, 10, 12])

    ws = wb.create_sheet("A'zolar faolligi")
    _title(ws, "A'zolarning naryad intizomi", period, 9)
    _header(ws, ["A'zo", "Fakultet", "Naryadlar", "Yakunlagan", "Chiqmagan", "Yakunlamagan", "Kechikkan",
                 "Qayd etgan qonunbuzarlik", "Intizom, %"], 4)
    for r in data["member_rows"]:
        ws.append([r["member"].full_name, r["member"].faculty.name if r["member"].faculty else "", r["total"],
                   r["finished"], r["missed"], r["unfinished"], r["late"], r["violations"],
                   r["rate"] if r["rate"] is not None else "—"])
        if r["rate"] is not None:
            ws.cell(row=ws.max_row, column=9).fill = green if r["rate"] >= 80 else amber if r["rate"] >= 50 else red
    _widths(ws, [30, 28, 11, 12, 12, 14, 11, 16, 12])

    ws = wb.create_sheet("Takroriy qonunbuzarlar")
    _title(ws, "Bir necha marta qayd etilgan talabalar", period, 6)
    _header(ws, ["Talaba", "Fakultet", "Guruh", "Kurs", "Soni", "Turlari"], 4)
    for r in data["repeat_offenders"]:
        ws.append([r["name"], r["faculty"].name, r["group"], r["course"], r["count"], r["categories"]])
    _widths(ws, [32, 28, 10, 6, 8, 50])

    ws = wb.create_sheet("Qonunbuzar talabalar")
    _title(ws, "Qonunbuzarlik qilgan talabalar", period, 14)
    _header(ws, ["№", "Talaba F.I.Sh", "Fakultet", "Yo'nalish", "Guruh", "Kurs", "TTJ", "Xona", "Tyutori",
                 "Soni", "Qonunbuzarlik turlari", "Birinchi", "Oxirgi", "Qayd etgan a'zolar"], 4)
    for i, r in enumerate(data["violators"], 1):
        ws.append([
            i, r["name"], r["faculty"].name, r["direction"], r["group"], r["course"],
            r["dormitory"].name if r["dormitory"] else "", r["room"], r["tutor"], r["count"],
            "; ".join(f"{label} ({c})" for label, c in r["categories"]),
            timezone.localtime(r["first"]).strftime("%d.%m.%Y %H:%M"),
            timezone.localtime(r["last"]).strftime("%d.%m.%Y %H:%M"),
            ", ".join(r["recorders"]),
        ])
        if r["count"] > 1:
            ws.cell(row=ws.max_row, column=10).fill = red
    _widths(ws, [5, 32, 30, 24, 10, 6, 22, 8, 26, 7, 44, 16, 16, 34])

    ws = wb.create_sheet("Qonunbuzarliklar")
    _header(ws, ["Sana", "Turi", "Talaba", "Fakultet", "Guruh", "Kurs", "TTJ", "Xona", "Tyutor", "Izoh",
                 "Qayd etgan"], 1)
    for v in data["violations"]:
        ws.append([timezone.localtime(v.occurred_at).strftime("%d.%m.%Y %H:%M"), v.get_category_display(),
                   v.student_name, v.faculty.name, v.group_name, v.course, v.place.name, v.room, v.tutor_display,
                   v.description, v.duty_member.member.full_name])
    _widths(ws, [16, 24, 30, 26, 10, 6, 20, 8, 26, 50, 26])

    return _xlsx_response(wb, f"qalqon_statistika_{date_from:%Y%m%d}_{date_to:%Y%m%d}.xlsx")


# ---------------------------------------------------------------- excel yordamchilari

def _title(ws, title, subtitle, cols):
    from openpyxl.styles import Font

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(cols, 2))
    ws["A1"] = title
    ws["A1"].font = Font(size=14, bold=True, color="1E1B4B")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(cols, 2))
    ws["A2"] = subtitle
    ws["A2"].font = Font(size=10, color="475467")


def _header(ws, headers, row):
    from openpyxl.styles import Alignment, Font, PatternFill

    for col, text in enumerate(headers, 1):
        c = ws.cell(row=row, column=col, value=text)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1E1B4B")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = f"A{row + 1}"  # ws.cell() bo'sh qator yaratib yuborardi


def _widths(ws, widths):
    from openpyxl.utils import get_column_letter

    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _xlsx_response(wb, filename):
    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(buffer.getvalue(),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response



@qalqon_required
def member_photo(request, pk):
    """A'zo rasmi — faqat Qalqon foydalanuvchilariga."""
    import mimetypes

    from django.http import FileResponse, Http404

    profile = get_object_or_404(MemberProfile, user_id=pk)
    if not profile.photo:
        raise Http404
    try:
        handle = profile.photo.open("rb")
    except FileNotFoundError:
        raise Http404
    response = FileResponse(handle, content_type=mimetypes.guess_type(profile.photo.name)[0] or "image/jpeg")
    response["Cache-Control"] = "private, max-age=3600"
    return response


@admin_required
def settings_view(request):
    from .forms import QalqonSettingsForm
    from .models import LocationLog, QalqonSettings

    obj = QalqonSettings.load()
    form = QalqonSettingsForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Sozlamalar saqlandi va darhol kuchga kirdi.")
        return redirect("qalqon:settings")
    # Oxirgi rad etilgan joylashuv tekshiruvlari — chegarani to'g'ri tanlash uchun
    recent = LocationLog.objects.select_related("duty_member__member").order_by("-created_at")[:30]
    return render(request, "qalqon/settings.html", {"form": form, "recent": recent})
