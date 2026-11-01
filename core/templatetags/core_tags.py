from django import template
from django.utils import timezone

from .. import utils

register = template.Library()


@register.filter
def uz_date(value):
    return utils.uz_date(value)


@register.filter
def uz_date_wd(value):
    return utils.uz_date(value, with_weekday=True)


@register.filter
def uz_datetime(value):
    return utils.uz_datetime(value)


@register.filter
def short_date(value):
    return utils.short_date(value)


@register.filter
def filesize(value):
    return utils.human_size(value or 0)


@register.filter
def get(mapping, key):
    try:
        return mapping.get(key, 0)
    except AttributeError:
        return 0


@register.filter
def file_icon(ext):
    ext = (ext or "").lower()
    if ext in ("pdf",):
        return "file-text"
    if ext in ("doc", "docx", "odt", "rtf", "txt"):
        return "file-type"
    if ext in ("xls", "xlsx", "csv", "ods"):
        return "file-spreadsheet"
    if ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"):
        return "file-image"
    if ext in ("zip", "rar", "7z", "tar", "gz"):
        return "file-archive"
    if ext in ("ppt", "pptx"):
        return "presentation"
    return "file"


@register.simple_tag
def time_left(deadline):
    """'2 kun 3 soat qoldi' / '1 kun o'tdi'."""
    delta = deadline - timezone.now()
    seconds = int(delta.total_seconds())
    passed = seconds < 0
    seconds = abs(seconds)
    days, rem = divmod(seconds, 86400)
    hours = rem // 3600
    minutes = (rem % 3600) // 60
    if days:
        text = f"{days} kun" + (f" {hours} soat" if hours else "")
    elif hours:
        text = f"{hours} soat" + (f" {minutes} daq" if minutes else "")
    else:
        text = f"{minutes} daqiqa"
    return f"{text} o'tdi" if passed else f"{text} qoldi"


@register.simple_tag(takes_context=True)
def qs(context, **kwargs):
    """Joriy GET parametrlarini saqlagan holda ba'zilarini almashtirish."""
    query = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            query.pop(key, None)
        else:
            query[key] = value
    encoded = query.urlencode()
    return f"?{encoded}" if encoded else "?"


STATUS_ICONS = {
    "approved": "check-circle-2",
    "submitted": "clock",
    "overdue": "alert-circle",
    "rejected": "rotate-ccw",
    "pending": "arrow-right-circle",
}


@register.filter
def status_icon(status):
    return STATUS_ICONS.get(status, "circle")


@register.filter
def status_label(status):
    from ..models import STATUS_LABELS

    return STATUS_LABELS.get(status, status)


_static_versions = {}


@register.simple_tag
def vstatic(path):
    """{% static %} + ?v=<fayl o'zgargan vaqt> — yangilanishdan keyin brauzer eski faylni keshdan olmaydi."""
    import os

    from django.conf import settings
    from django.contrib.staticfiles import finders
    from django.templatetags.static import static

    version = None if settings.DEBUG else _static_versions.get(path)
    if version is None:
        found = finders.find(path)
        if not found and settings.STATIC_ROOT:
            candidate = os.path.join(settings.STATIC_ROOT, path)
            found = candidate if os.path.exists(candidate) else None
        version = str(int(os.path.getmtime(found))) if found else "0"
        _static_versions[path] = version
    return f"{static(path)}?v={version}"
