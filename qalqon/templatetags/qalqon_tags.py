from django import template

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
