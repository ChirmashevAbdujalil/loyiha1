from django import template
from django.urls import reverse
from django.utils.html import format_html

from ..models import DUTY_STATUS_LABELS

register = template.Library()

ICONS = {
    "finished": "check-circle-2",
    "active": "radio",
    "unfinished": "alert-triangle",
    "missed": "x-circle",
    "today": "map-pin",
    "scheduled": "calendar-clock",
}


@register.filter
def duty_icon(status):
    return ICONS.get(status, "circle")


@register.filter
def duty_label(status):
    return DUTY_STATUS_LABELS.get(status, status)


@register.filter
def meters(value):
    if value is None:
        return "—"
    return f"{value:.0f} m" if value < 1000 else f"{value / 1000:.2f} km"


@register.simple_tag
def member_avatar(user, size=""):
    """A'zo rasmi (bo'lsa) yoki ism-familiya bosh harflari."""
    cls = f"avatar {size}".strip()
    url = member_photo_url(user)
    if url:
        return format_html('<img class="{} avatar-img" src="{}" alt="" loading="lazy">', cls, url)
    return format_html('<span class="{}">{}</span>', cls, user.initials)


@register.simple_tag
def member_photo_url(user):
    """Rasm manzili; ?v= fayl nomidan — rasm almashtirilsa, brauzer yangisini yuklaydi."""
    import hashlib

    profile = getattr(user, "qalqon_profile", None)
    if profile is None or not profile.photo:
        return ""
    version = hashlib.md5(profile.photo.name.encode()).hexdigest()[:8]
    return f"{reverse('qalqon:member_photo', args=[user.pk])}?v={version}"
