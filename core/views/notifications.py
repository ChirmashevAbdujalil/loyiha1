from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..models import Notification
from ..utils import uz_datetime


@login_required
def notification_list(request):
    notifications = request.user.notifications.all()[:200]
    return render(request, "notifications/list.html", {"notifications": notifications})


@login_required
def notification_open(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    if not n.is_read:
        n.is_read = True
        n.save(update_fields=["is_read"])
    return redirect(n.url or "notification_list")


@login_required
@require_POST
def notification_read_all(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    messages.success(request, "Barcha bildirishnomalar o'qilgan deb belgilandi.")
    return redirect(request.POST.get("next") or "notification_list")


@login_required
def notification_feed(request):
    """Sarlavhadagi qo'ng'iroqcha uchun (har 30 soniyada so'raladi)."""
    unread = request.user.notifications.filter(is_read=False)
    latest = [
        {
            "id": n.pk,
            "title": n.title,
            "message": n.message,
            "kind": n.kind,
            "time": uz_datetime(n.created_at),
            "url": reverse("notification_open", args=[n.pk]),
        }
        for n in unread[:8]
    ]
    return JsonResponse({"unread": unread.count(), "items": latest})


@login_required
def profile(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Parol muvaffaqiyatli o'zgartirildi.")
        return redirect("profile")
    return render(request, "profile.html", {"form": form})
