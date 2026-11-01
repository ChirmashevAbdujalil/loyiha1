"""Ijro tizimi va Qalqon — ikki alohida platforma.

Har bir sahifa bitta platformaga tegishli: menyu, logotip, bildirishnomalar
shu platforma bo'yicha ko'rsatiladi. Umumiy sahifalar (bildirishnomalar, profil,
fakultetlar) foydalanuvchi oxirgi marta qaysi platformada bo'lgan bo'lsa, o'sha
platforma ko'rinishida ochiladi.
"""

IJRO = "ijro"
QALQON = "qalqon"

# Qalqon platformasiga tegishli bildirishnoma turlari
QALQON_KINDS = ("duty", "violation")

SHARED_URLS = {
    "notification_list", "notification_feed", "notification_open", "notification_read_all",
    "profile", "faculty_list", "faculty_edit", "faculty_delete",
}
SESSION_KEY = "platform"


def available(user):
    """Foydalanuvchi kira oladigan platformalar."""
    if not user.is_authenticated:
        return []
    result = []
    if not user.is_qalqon_only:
        result.append(IJRO)
    if user.is_qalqon_staff or user.is_qalqon_member:
        result.append(QALQON)
    return result


def current(request):
    user = request.user
    platforms = available(user)
    if not platforms:
        return IJRO
    if len(platforms) == 1:
        return platforms[0]
    match = getattr(request, "resolver_match", None)
    requested = request.GET.get("p")
    if requested in platforms:
        platform = requested
    elif match and match.namespace == QALQON:
        platform = QALQON
    elif match and match.url_name in SHARED_URLS:
        platform = request.session.get(SESSION_KEY, IJRO)
    else:
        platform = IJRO
    if platform not in platforms:
        platform = platforms[0]
    if request.session.get(SESSION_KEY) != platform:
        request.session[SESSION_KEY] = platform
    return platform


def notifications_for(user, platform):
    qs = user.notifications.all()
    if platform == QALQON:
        return qs.filter(kind__in=QALQON_KINDS)
    if QALQON in available(user):
        return qs.exclude(kind__in=QALQON_KINDS)
    return qs


def home_url(platform):
    from django.urls import reverse

    return reverse("qalqon:calendar") if platform == QALQON else reverse("dashboard")
