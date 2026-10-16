from datetime import timedelta

from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from core.models import Assignment, Notification
from core.utils import uz_datetime


class Command(BaseCommand):
    help = (
        "Muddati yaqinlashgan (default: 24 soat ichida) va hali yopilmagan ijrolar bo'yicha "
        "tyutorlarga eslatma yuboradi. Cron orqali soatiga bir marta ishga tushirish tavsiya etiladi."
    )

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, hours, **options):
        now = timezone.now()
        soon = Assignment.objects.filter(
            status__in=[Assignment.Status.PENDING, Assignment.Status.REJECTED],
            task__deadline__gt=now,
            task__deadline__lte=now + timedelta(hours=hours),
            tutor__is_active=True,
        ).select_related("task", "tutor")
        sent = 0
        for a in soon:
            url = reverse("assignment_detail", args=[a.pk])
            # Bir ijro bo'yicha faqat bitta eslatma
            if Notification.objects.filter(user=a.tutor, kind=Notification.Kind.REMINDER, url=url).exists():
                continue
            Notification.objects.create(
                user=a.tutor,
                kind=Notification.Kind.REMINDER,
                title=f"Muddat yaqinlashmoqda: {a.task.title}",
                message=f"Ijro muddati: {uz_datetime(a.task.deadline)}",
                url=url,
            )
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"{sent} ta eslatma yuborildi."))
