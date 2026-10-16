import datetime as dt
import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Assignment, Faculty, Notification, Submission, Task, User

FACULTIES = [
    ("Iqtisodiyot fakulteti", "IQT"),
    ("Pedagogika fakulteti", "PED"),
    ("Filologiya fakulteti", "FIL"),
    ("Axborot texnologiyalari fakulteti", "AT"),
]

TUTORS = [
    ("Karimov", "Jasur", "Akmalovich"), ("Rahimova", "Dilnoza", "Shavkatovna"),
    ("Tursunov", "Bekzod", "Olimovich"), ("Yusupova", "Madina", "Rustamovna"),
    ("Abdullayev", "Sardor", "Baxtiyorovich"), ("Qodirova", "Nilufar", "Anvarovna"),
    ("Ergashev", "Otabek", "Ilhomovich"), ("Saidova", "Gulnoza", "Farhodovna"),
    ("Xolmatov", "Aziz", "Rahmatovich"), ("Nazarova", "Shahnoza", "Erkinovna"),
    ("Mirzayev", "Javohir", "Ulug'bekovich"), ("Hasanova", "Zarina", "Komilovna"),
]

TASKS = [
    ("Talabalar turar joyida «Ma'naviyat soati» tadbirini o'tkazish",
     "Har bir guruhda ma'naviyat soatini o'tkazib, fotolavhalar va qisqa hisobotni joylashtiring."),
    ("Ota-onalar bilan onlayn uchrashuv tashkil etish",
     "1-kurs talabalarining ota-onalari bilan uchrashuv o'tkazilib, bayonnoma yuklansin."),
    ("«Yoshlar — kelajak bunyodkori» mavzusida davra suhbati",
     "Davra suhbati o'tkazilib, ijtimoiy tarmoqdagi post havolasi yuborilsin."),
    ("Talabalarning ijtimoiy holatini o'rganish (anketa)",
     "Biriktirilgan guruhlar bo'yicha anketa natijalarini Google Forms havolasi bilan yuboring."),
    ("Kitobxonlik tanlovining fakultet bosqichini o'tkazish",
     "Tanlov natijalari va g'oliblar ro'yxatini ilova qiling."),
    ("Ijara uylarida yashovchi talabalarni o'rganish",
     "Ijarada yashovchi talabalar holatini o'rganib, dalolatnoma tuzing."),
    ("Huquqiy targ'ibot haftaligi doirasida tadbir",
     "Huquq-tartibot organlari vakillari ishtirokida uchrashuv o'tkazing."),
    ("Sport musobaqasida talabalarning ishtirokini ta'minlash",
     "Ishtirokchilar ro'yxati va fotosuratlar havolasini yuboring."),
    ("Mustaqillik bayramiga tayyorgarlik rejasi",
     "Fakultet bo'yicha tadbirlar rejasini ishlab chiqib yuboring."),
    ("Teatr va muzeylarga ekskursiya tashkil etish",
     "Ekskursiyada qatnashgan talabalar soni va fotolavhalar."),
]


class Command(BaseCommand):
    help = "Namoyish uchun demo ma'lumotlar: bo'lim boshlig'i, fakultetlar, tyutorlar, topshiriqlar."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="demo1234")

    @transaction.atomic
    def handle(self, password, **options):
        rnd = random.Random(42)
        head, created = User.objects.get_or_create(
            username="boshliq",
            defaults={"first_name": "Doniyor", "last_name": "Sarimsoqov", "role": User.Role.HEAD, "is_staff": True,
                      "position": "Ma'naviyat va ma'rifat bo'limi boshlig'i"},
        )
        if created:
            head.set_password(password)
            head.save()

        faculties = [Faculty.objects.get_or_create(name=n, defaults={"short_name": s})[0] for n, s in FACULTIES]
        tutors = []
        for i, (last, first, middle) in enumerate(TUTORS):
            username = f"tyutor{i + 1}"
            tutor, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first, "last_name": last, "middle_name": middle,
                    "faculty": faculties[i % len(faculties)], "role": User.Role.TUTOR,
                    "position": f"{i % 4 + 1}-kurs tyutori", "phone": f"+998 9{i % 10} 123 45 {10 + i}",
                },
            )
            if created:
                tutor.set_password(password)
                tutor.save()
            tutors.append(tutor)

        if Task.objects.exists():
            self.stdout.write("Topshiriqlar allaqachon mavjud — faqat foydalanuvchilar tekshirildi.")
            return

        now = timezone.now()
        today = timezone.localdate()
        tz = timezone.get_current_timezone()
        offsets = [-20, -14, -9, -6, -3, -1, 0, 2, 5, 9]
        for (title, desc), off in zip(TASKS, offsets):
            ex = today + dt.timedelta(days=off)
            deadline = dt.datetime.combine(ex + dt.timedelta(days=rnd.choice([0, 1, 2])), dt.time(18, 0), tzinfo=tz)
            created_at = min(now, deadline - dt.timedelta(days=7))
            task = Task.objects.create(title=title, description=desc, execution_date=ex,
                                       deadline=deadline, created_by=head)
            Task.objects.filter(pk=task.pk).update(created_at=created_at)
            for tutor in rnd.sample(tutors, rnd.randint(3, 7)):
                a = Assignment.objects.create(task=task, tutor=tutor)
                Assignment.objects.filter(pk=a.pk).update(created_at=created_at)
                roll = rnd.random()
                if deadline < now:
                    outcome = "approved" if roll < 0.6 else "submitted" if roll < 0.75 else "none"
                else:
                    outcome = "approved" if roll < 0.25 else "submitted" if roll < 0.5 else "none"
                if outcome == "none":
                    continue
                sub_time = min(now - dt.timedelta(hours=1),
                               deadline - dt.timedelta(hours=rnd.randint(-20, 60)))
                sub_time = max(sub_time, created_at + dt.timedelta(hours=1))
                sub = Submission.objects.create(
                    assignment=a, comment="Topshiriq bajarildi, fotolavhalar havolada.",
                    link="https://t.me/example/123", created_at=sub_time,
                )
                a.status = Assignment.Status.SUBMITTED
                a.submitted_at = sub_time
                a.seen_at = sub_time - dt.timedelta(hours=2)
                if outcome == "approved":
                    rev = min(now, sub_time + dt.timedelta(hours=rnd.randint(1, 30)))
                    sub.decision = Submission.Decision.APPROVED
                    sub.reviewed_by = head
                    sub.reviewed_at = rev
                    sub.review_comment = "Qabul qilindi."
                    sub.save()
                    a.status = Assignment.Status.APPROVED
                    a.approved_at = rev
                a.save()
            for a in task.assignments.select_related("tutor"):
                Notification.objects.create(
                    user=a.tutor, kind=Notification.Kind.NEW_TASK, title=f"Yangi topshiriq: {task.title}",
                    url=a.get_absolute_url(), is_read=rnd.random() < 0.6,
                )
        self.stdout.write(self.style.SUCCESS(
            f"Demo ma'lumotlar yaratildi. Kirish: boshliq / {password}, tyutorlar: tyutor1…tyutor{len(TUTORS)} / {password}"
        ))
