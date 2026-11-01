"""Qalqon: joylashuvni tekshirish, bildirishnomalar, statistika va a'zolarni import qilish."""
import datetime as dt
import re
import secrets
from collections import Counter, defaultdict

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.models import Faculty, Notification, User

from .models import Building, Duty, DutyMember, LocationLog, MemberProfile, Violation


# ------------------------------------------------------------ joylashuv

def check_location(dm, action, lat, lng, accuracy, user_agent=""):
    """A'zo turgan joy naryad hududida ekanini tekshiradi va jurnalga yozadi.

    Qaytaradi: (ok: bool, distance_m: float, xabar: str)
    """
    duty = dm.duty
    distance = duty.distance_to(lat, lng)
    max_acc = getattr(settings, "QALQON_MAX_GPS_ACCURACY", 150)
    if accuracy is not None and accuracy > max_acc:
        ok = False
        message = (f"GPS aniqligi past (±{accuracy:.0f} m). Ochiq joyga chiqib, "
                   f"bir necha soniyadan keyin qayta urining (talab: ±{max_acc} m).")
    elif distance > duty.radius_m:
        ok = False
        message = (f"Siz naryad hududidan tashqaridasiz: binogacha {distance:.0f} m, "
                   f"ruxsat etilgan radius {duty.radius_m} m.")
    else:
        ok = True
        message = f"Joylashuv tasdiqlandi ({distance:.0f} m)."
    LocationLog.objects.create(
        duty_member=dm, action=action, latitude=round(lat, 6), longitude=round(lng, 6),
        accuracy=accuracy, distance=distance, success=ok, message=message[:255],
        user_agent=(user_agent or "")[:300],
    )
    return ok, distance, message


# ------------------------------------------------------------ bildirishnomalar

def notify_duty_assigned(duty_members):
    Notification.objects.bulk_create([
        Notification(
            user=dm.member,
            kind=Notification.Kind.DUTY,
            title=f"Naryad: {dm.duty.date:%d.%m.%Y}, {dm.duty.start_time:%H:%M}–{dm.duty.end_time:%H:%M}",
            message=f"Joy: {dm.duty.building.name}",
            url=reverse("qalqon:duty_detail", args=[dm.duty_id]),
        )
        for dm in duty_members
    ])


def notify_duty_changed(duty, removed_members=(), notify_current=True):
    rows = [] if not notify_current else [
        Notification(
            user=dm.member, kind=Notification.Kind.DUTY,
            title=f"Naryad o'zgartirildi: {duty.date:%d.%m.%Y}",
            message=f"{duty.start_time:%H:%M}–{duty.end_time:%H:%M}, {duty.building.name}",
            url=reverse("qalqon:duty_detail", args=[duty.pk]),
        )
        for dm in duty.duty_members.select_related("member")
    ]
    rows += [
        Notification(
            user=u, kind=Notification.Kind.DUTY,
            title=f"Siz {duty.date:%d.%m.%Y} kungi naryaddan olib tashlandingiz",
            message=duty.building.name, url=reverse("qalqon:my_duties"),
        )
        for u in removed_members
    ]
    Notification.objects.bulk_create(rows)


def notify_violation(violation):
    duty = violation.duty_member.duty
    if duty.created_by_id == violation.duty_member.member_id:
        return
    Notification.objects.create(
        user=duty.created_by, kind=Notification.Kind.VIOLATION,
        title=f"Qonunbuzarlik: {violation.get_category_display()}",
        message=f"{violation.student_name} ({violation.faculty.label}, {violation.course}-kurs) — "
                f"{violation.duty_member.member.full_name} naryadida",
        url=reverse("qalqon:duty_detail", args=[duty.pk]),
    )


# ------------------------------------------------------------ statistika

def _bars(counter, labels=None, limit=None):
    items = counter.most_common(limit)
    top = items[0][1] if items else 0
    total = sum(counter.values())
    return [
        {
            "key": key,
            "label": (labels or {}).get(key, key),
            "count": count,
            "pct": round(count * 100 / top) if top else 0,
            "share": round(count * 100 / total) if total else 0,
        }
        for key, count in items
    ]


def build_stats(date_from, date_to, building_id=None, faculty_id=None):
    duties = Duty.objects.filter(date__range=(date_from, date_to)).select_related("building")
    if building_id:
        duties = duties.filter(building_id=building_id)
    duty_members = list(
        DutyMember.objects.filter(duty__in=duties).select_related("duty", "duty__building", "member", "member__faculty")
    )
    if faculty_id:
        duty_members_for_members = [dm for dm in duty_members if dm.member.faculty_id == faculty_id]
    else:
        duty_members_for_members = duty_members

    violations = list(
        Violation.objects.filter(duty_member__duty__in=duties)
        .select_related("faculty", "dormitory", "tutor", "duty_member__member", "duty_member__duty__building")
    )
    if faculty_id:
        violations = [v for v in violations if v.faculty_id == faculty_id]

    status_counts = Counter(dm.display_status for dm in duty_members_for_members)
    past = status_counts["finished"] + status_counts["missed"] + status_counts["unfinished"]
    late_starts = sum(1 for dm in duty_members_for_members if dm.is_late_start)

    # Joylar (TTJ / bino) — qonunbuzarliklar soni
    place_counter = Counter(v.place.pk for v in violations)
    buildings = {b.pk: b for b in Building.objects.all()}
    by_place = _bars(place_counter, {pk: b.name for pk, b in buildings.items()})

    # TTJ intizom reytingi: qonunbuzarlik / naryad
    duties_per_building = Counter(d.building_id for d in duties)
    dorm_rows = []
    for b in buildings.values():
        if b.kind != Building.Kind.DORM:
            continue
        if building_id and b.pk != building_id:
            continue
        v_count = place_counter.get(b.pk, 0)
        d_count = duties_per_building.get(b.pk, 0)
        dorm_rows.append({
            "building": b,
            "violations": v_count,
            "duties": d_count,
            "per_duty": round(v_count / d_count, 2) if d_count else None,
        })
    dorm_rows.sort(key=lambda r: (r["violations"], -(r["duties"])))
    max_v = max((r["violations"] for r in dorm_rows), default=0)
    for i, r in enumerate(dorm_rows, 1):
        r["rank"] = i
        r["pct"] = round(r["violations"] * 100 / max_v) if max_v else 0
        if r["violations"] == 0:
            r["level"] = "good"
        elif max_v and r["violations"] >= max_v * 0.66:
            r["level"] = "bad"
        else:
            r["level"] = "mid"

    category_labels = dict(Violation.Category.choices)
    faculty_names = {f.pk: f.name for f in Faculty.objects.all()}

    # Kimning naryadida qanday qonunbuzarliklar
    per_recorder = defaultdict(lambda: {"member": None, "total": 0, "categories": Counter()})
    for v in violations:
        row = per_recorder[v.duty_member.member_id]
        row["member"] = v.duty_member.member
        row["total"] += 1
        row["categories"][v.category] += 1
    recorder_rows = sorted(per_recorder.values(), key=lambda r: -r["total"])
    for r in recorder_rows:
        r["categories"] = [(category_labels[k], c) for k, c in r["categories"].most_common()]

    # Takroriy qonunbuzarlar
    offenders = defaultdict(list)
    for v in violations:
        key = (re.sub(r"\s+", " ", v.student_name.strip().lower()), v.group_name.strip().lower())
        offenders[key].append(v)
    repeat_offenders = sorted(
        ({"name": vs[0].student_name, "faculty": vs[0].faculty, "group": vs[0].group_name,
          "course": vs[0].course, "count": len(vs), "last": max(x.occurred_at for x in vs),
          "categories": ", ".join(sorted({x.get_category_display() for x in vs}))}
         for vs in offenders.values() if len(vs) > 1),
        key=lambda r: -r["count"],
    )

    # A'zolar faolligi
    member_rows = {}
    for dm in duty_members_for_members:
        row = member_rows.setdefault(dm.member_id, {
            "member": dm.member, "total": 0, "finished": 0, "missed": 0, "unfinished": 0, "late": 0, "violations": 0,
        })
        row["total"] += 1
        st = dm.display_status
        if st in ("finished", "missed", "unfinished"):
            row[st] += 1
        if dm.is_late_start:
            row["late"] += 1
    for v in violations:
        if v.duty_member.member_id in member_rows:
            member_rows[v.duty_member.member_id]["violations"] += 1
    member_rows = sorted(member_rows.values(), key=lambda r: (-r["finished"], r["missed"], r["member"].last_name))
    for r in member_rows:
        done = r["finished"] + r["missed"] + r["unfinished"]
        r["rate"] = round(r["finished"] * 100 / done) if done else None

    # Kunlar kesimida
    days = (date_to - date_from).days + 1
    day_counter = Counter(timezone.localtime(v.occurred_at).date() for v in violations)
    trend = []
    if days <= 92:
        top = max(day_counter.values(), default=0)
        for i in range(days):
            d = date_from + dt.timedelta(days=i)
            c = day_counter.get(d, 0)
            trend.append({"date": d, "count": c, "pct": round(c * 100 / top) if top else 0})

    hour_counter = Counter(timezone.localtime(v.occurred_at).hour for v in violations)
    hours = [{"label": f"{h:02d}:00", "count": c} for h, c in sorted(hour_counter.items())]
    top_h = max((h["count"] for h in hours), default=0)
    for h in hours:
        h["pct"] = round(h["count"] * 100 / top_h) if top_h else 0

    tutor_counter = Counter(v.tutor_display or "—" for v in violations)

    return {
        "duties_total": duties.count(),
        "assignments_total": len(duty_members_for_members),
        "status_counts": status_counts,
        "discipline_rate": round(status_counts["finished"] * 100 / past) if past else None,
        "late_starts": late_starts,
        "violations_total": len(violations),
        "students_total": len(offenders),
        "by_category": _bars(Counter(v.category for v in violations), category_labels),
        "by_place": by_place,
        "by_faculty": _bars(Counter(v.faculty_id for v in violations), faculty_names),
        "by_course": _bars(Counter(v.course for v in violations), {i: f"{i}-kurs" for i in range(1, 8)}),
        "by_tutor": _bars(tutor_counter, limit=15),
        "dorm_rows": dorm_rows,
        "recorder_rows": recorder_rows,
        "repeat_offenders": repeat_offenders,
        "member_rows": member_rows,
        "trend": trend,
        "hours": hours,
        "violations": violations,
    }


# ------------------------------------------------------------ import

CYR = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюяўқғҳ",
    ["a", "b", "v", "g", "d", "e", "yo", "j", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
     "u", "f", "x", "ts", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya", "o", "q", "g", "h"],
))

HEADER_ALIASES = {
    "fio": ["f.i.sh", "fish", "f.i.o", "fio", "ф.и.ш", "ф.и.о", "talaba", "a'zo", "ism familiya", "familiya ism"],
    "last_name": ["familiya", "фамилия", "familiyasi"],
    "first_name": ["ism", "исм", "имя", "ismi"],
    "middle_name": ["otasining ismi", "sharifi", "отасининг исми", "отчество"],
    "faculty": ["fakultet", "факультет", "fakulteti"],
    "direction": ["yo'nalish", "yonalish", "yo‘nalish", "йўналиш", "направление", "mutaxassislik"],
    "group": ["guruh", "гуруҳ", "группа", "guruhi"],
    "course": ["kurs", "курс", "kursi"],
    "phone": ["telefon", "телефон", "tel", "telefon raqami"],
    "dormitory": ["ttj", "ттж", "yotoqxona"],
    "room": ["xona", "хона", "комната", "xona raqami"],
    "username": ["login", "логин"],
    "password": ["parol", "пароль"],
    "role": ["rol", "lavozim", "роль"],
}


def _norm(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower().replace("ʻ", "'").replace("‘", "'").replace("’", "'"))


def _ascii(text):
    text = _norm(text)
    out = "".join(CYR.get(ch, ch) for ch in text)
    return re.sub(r"[^a-z0-9]", "", out)


def make_username(last_name, first_name):
    base = (_ascii(last_name) + ("." + _ascii(first_name)[:1] if first_name else "")) or "qalqon"
    base = base[:28]
    username, n = base, 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"{base}{n}"
    return username


def _find_faculty(name, faculties, create):
    key = _norm(name)
    if not key:
        return None, False
    for f in faculties:
        if key in (_norm(f.name), _norm(f.short_name)) or (len(key) > 4 and key in _norm(f.name)):
            return f, False
    if not create:
        return None, False
    f = Faculty.objects.create(name=str(name).strip())
    faculties.append(f)
    return f, True


def read_rows(path_or_file):
    from openpyxl import load_workbook

    wb = load_workbook(path_or_file, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header_idx, mapping = None, {}
    for i, row in enumerate(rows[:10]):
        cand = {}
        for j, cell in enumerate(row):
            key = _norm(cell)
            for field, aliases in HEADER_ALIASES.items():
                if key in aliases and field not in cand:
                    cand[field] = j
        if ("fio" in cand or "last_name" in cand) and len(cand) >= 2:
            header_idx, mapping = i, cand
            break
    if header_idx is None:
        raise ValueError("Sarlavha qatori topilmadi. Kamida «F.I.Sh» (yoki «Familiya», «Ism») va "
                         "«Fakultet» ustunlari bo'lishi kerak.")
    data = []
    for row in rows[header_idx + 1:]:
        if not any(c not in (None, "") for c in row):
            continue
        rec = {field: (row[j] if j < len(row) else None) for field, j in mapping.items()}
        if "fio" in rec and not rec.get("last_name"):
            parts = str(rec.pop("fio") or "").split()
            rec["last_name"] = parts[0] if parts else ""
            rec["first_name"] = parts[1] if len(parts) > 1 else ""
            rec["middle_name"] = " ".join(parts[2:])
        data.append(rec)
    return data


@transaction.atomic
def import_members(rows, create_faculties=True, default_role=User.Role.QALQON_MEMBER):
    """Qatorlar ro'yxatidan a'zolarni yaratadi. Qaytaradi: natija lug'ati (credentials bilan)."""
    faculties = list(Faculty.objects.all())
    dorms = list(Building.objects.filter(kind=Building.Kind.DORM))
    result = {"created": [], "skipped": [], "errors": [], "new_faculties": []}
    role_map = {"sardor": User.Role.QALQON_LEADER, "admin": User.Role.QALQON_ADMIN}
    for n, rec in enumerate(rows, 1):
        last = str(rec.get("last_name") or "").strip()
        first = str(rec.get("first_name") or "").strip()
        if not last:
            result["errors"].append(f"{n}-qator: familiya yo'q")
            continue
        faculty, created_fac = _find_faculty(rec.get("faculty"), faculties, create_faculties)
        if created_fac:
            result["new_faculties"].append(faculty.name)
        if faculty is None:
            result["errors"].append(f"{n}-qator ({last} {first}): fakultet topilmadi — «{rec.get('faculty') or ''}»")
            continue
        middle = str(rec.get("middle_name") or "").strip()
        group = str(rec.get("group") or "").strip()
        exists = User.objects.filter(
            last_name__iexact=last, first_name__iexact=first, faculty=faculty,
            role__in=[User.Role.QALQON_MEMBER, User.Role.QALQON_LEADER, User.Role.QALQON_ADMIN],
        ).first()
        if exists:
            result["skipped"].append(f"{last} {first} — allaqachon bazada (login: {exists.username})")
            continue
        username = str(rec.get("username") or "").strip() or make_username(last, first)
        if User.objects.filter(username=username).exists():
            username = make_username(last, first)
        password = str(rec.get("password") or "").strip() or f"{secrets.randbelow(10**8):08d}"
        role = role_map.get(_norm(rec.get("role")), default_role)
        user = User.objects.create_user(
            username=username, password=password, first_name=first, last_name=last, middle_name=middle,
            faculty=faculty, phone=str(rec.get("phone") or "").strip(), role=role,
        )
        course = rec.get("course")
        try:
            course = int(str(course).strip().split("-")[0]) if course not in (None, "") else None
        except ValueError:
            course = None
        dorm = None
        if rec.get("dormitory"):
            key = _norm(rec["dormitory"])
            dorm = next((d for d in dorms if key in (_norm(d.name), _norm(d.short_name))), None)
        MemberProfile.objects.create(
            user=user, direction=str(rec.get("direction") or "").strip(), group_name=group,
            course=course if course and 1 <= course <= 7 else None, dormitory=dorm,
            room=str(rec.get("room") or "").strip(),
        )
        result["created"].append({"user": user, "password": password})
    return result


def credentials_workbook(created):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Loginlar"
    ws.append(["№", "F.I.Sh", "Fakultet", "Roli", "Login", "Parol"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1E1B4B")
    for i, item in enumerate(created, 1):
        u = item["user"]
        ws.append([i, f"{u.full_name} {u.middle_name}".strip(), u.faculty.name if u.faculty else "",
                   u.get_role_display(), u.username, item["password"]])
    for col, width in zip("ABCDEF", (5, 38, 32, 26, 20, 14)):
        ws.column_dimensions[col].width = width
    return wb
