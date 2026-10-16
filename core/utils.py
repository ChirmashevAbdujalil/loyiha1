import calendar
import datetime as dt

from django.utils import timezone

MONTHS = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]
WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
WEEKDAYS_SHORT = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]


def uz_date(d, with_weekday=False):
    """2026-yil 15-oktabr (Payshanba)"""
    if d is None:
        return ""
    if isinstance(d, dt.datetime):
        d = timezone.localtime(d).date() if timezone.is_aware(d) else d.date()
    text = f"{d.year}-yil {d.day}-{MONTHS[d.month - 1]}"
    if with_weekday:
        return f"{WEEKDAYS[d.weekday()]}, {text}"
    return text


def uz_datetime(value):
    if value is None:
        return ""
    value = timezone.localtime(value) if timezone.is_aware(value) else value
    return f"{uz_date(value.date())}, {value:%H:%M}"


def short_date(value):
    """15 okt 2026"""
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        value = timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    return f"{value.day} {MONTHS[value.month - 1][:3]} {value.year}"


def month_title(year, month):
    return f"{year}-yil {MONTHS[month - 1]}"


def parse_date(value, default=None):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


def month_bounds(year, month):
    first = dt.date(year, month, 1)
    last = dt.date(year, month, calendar.monthrange(year, month)[1])
    return first, last


def month_grid(year, month):
    """Dushanbadan boshlanadigan to'liq haftalar ro'yxati (sanalar)."""
    cal = calendar.Calendar(firstweekday=0)
    return [list(week) for week in cal.monthdatescalendar(year, month)]


def shift_month(year, month, delta):
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def human_size(num):
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num} B"
