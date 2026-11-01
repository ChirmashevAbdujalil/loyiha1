import re

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from core.management.commands.seed_demo import FACULTIES as DEMO_FACULTIES
from core.management.commands.seed_demo import TASKS as DEMO_TASKS
from core.models import Faculty, Task, User
from qalqon.management.commands.seed_qalqon import BUILDINGS as DEMO_BUILDINGS
from qalqon.models import Building, Duty

DEMO_USERNAME_RE = r"^(tyutor\d+|qalqon\d+|qalqon_admin|sardor)$"


class Command(BaseCommand):
    help = (
        "seed_demo va seed_qalqon yaratgan demo ma'lumotlarni o'chiradi: demo tyutorlar, Qalqon a'zolari, "
        "topshiriqlar, naryadlar, qonunbuzarliklar, binolar va fakultetlar. Haqiqiy ma'lumotlarga tegmaydi."
    )

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Tasdiq so'ramasdan o'chirish")

    def handle(self, yes, **options):
        users = User.objects.filter(username__regex=DEMO_USERNAME_RE, is_superuser=False)
        tasks = Task.objects.filter(title__in=[t for t, _ in DEMO_TASKS])
        duties = Duty.objects.filter(Q(created_by__in=users) | Q(duty_members__member__in=users)).distinct()
        building_names = [b[0] for b in DEMO_BUILDINGS]

        self.stdout.write("O'chiriladi:")
        self.stdout.write(f"  demo foydalanuvchilar: {users.count()}")
        self.stdout.write(f"  demo topshiriqlar: {tasks.count()}")
        self.stdout.write(f"  demo naryadlar (qonunbuzarliklari bilan): {duties.count()}")
        self.stdout.write(f"  demo binolar: {Building.objects.filter(name__in=building_names).count()} (ishlatilmagan bo'lsa)")
        self.stdout.write(f"  demo fakultetlar: {len(DEMO_FACULTIES)} tagacha (ularga hech kim biriktirilmagan bo'lsa)")
        if not yes and input("Davom etilsinmi? [ha/yo'q]: ").strip().lower() not in ("ha", "h", "yes", "y"):
            self.stdout.write("Bekor qilindi.")
            return

        with transaction.atomic():
            for duty in duties:
                for dm in duty.duty_members.all():
                    if dm.photo:
                        dm.photo.delete(save=False)
                    for v in dm.violations.all():
                        if v.photo:
                            v.photo.delete(save=False)
            n_duties = duties.count()
            Duty.objects.filter(pk__in=list(duties.values_list("pk", flat=True))).delete()

            for task in tasks:
                for f in task.files.all():
                    f.file.delete(save=False)
            n_tasks = tasks.count()
            tasks.delete()

            n_users = users.count()
            users.delete()

            # O'chirilgan obyektlarga ishora qiluvchi bildirishnomalar
            from core.models import Assignment, Notification

            stale = []
            for n in Notification.objects.exclude(url=""):
                m = re.match(r"^/ijro/(\d+)/", n.url)
                d = re.match(r"^/qalqon/naryadlar/(\d+)/", n.url)
                if (m and not Assignment.objects.filter(pk=m.group(1)).exists()) or \
                        (d and not Duty.objects.filter(pk=d.group(1)).exists()):
                    stale.append(n.pk)
            Notification.objects.filter(pk__in=stale).delete()

            removed_buildings = []
            for b in Building.objects.filter(name__in=building_names):
                if not b.duties.exists() and not b.violations.exists():
                    removed_buildings.append(b.name)
                    b.delete()

            removed_faculties = []
            for name, _short in DEMO_FACULTIES:
                f = Faculty.objects.filter(name=name).first()
                if f and not f.tutors.exists() and not f.qalqon_violations.exists():
                    removed_faculties.append(f.name)
                    f.delete()

        self.stdout.write(self.style.SUCCESS(
            f"O'chirildi: {n_users} foydalanuvchi, {n_tasks} topshiriq, {n_duties} naryad, "
            f"{len(removed_buildings)} bino, {len(removed_faculties)} fakultet."
        ))
        head = User.objects.filter(username="boshliq").first()
        if head and head.check_password("demo1234"):
            self.stdout.write(self.style.WARNING(
                "Diqqat: «boshliq» hisobining paroli hali ham demo1234. O'zgartiring: "
                "python manage.py changepassword boshliq"
            ))
