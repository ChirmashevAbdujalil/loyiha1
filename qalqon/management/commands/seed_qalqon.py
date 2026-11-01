import datetime as dt
import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Faculty, User
from qalqon.models import Building, Duty, DutyMember, MemberProfile, Violation

BUILDINGS = [
    ("1-son talabalar turar joyi", "TTJ-1", Building.Kind.DORM, 41.338210, 69.334410),
    ("2-son talabalar turar joyi", "TTJ-2", Building.Kind.DORM, 41.340120, 69.338950),
    ("3-son talabalar turar joyi", "TTJ-3", Building.Kind.DORM, 41.336470, 69.341020),
    ("Bosh o'quv binosi", "Bosh bino", Building.Kind.STUDY, 41.338900, 69.329700),
]

MEMBERS = [
    ("Aliyev", "Sherzod"), ("Bakirova", "Feruza"), ("Davronov", "Ulug'bek"), ("Egamberdiyeva", "Sevara"),
    ("Fayzullayev", "Doston"), ("G'aniyev", "Islom"), ("Hamroyeva", "Malika"), ("Ibragimov", "Javlon"),
    ("Jo'rayev", "Asadbek"), ("Komilova", "Dildora"), ("Latipov", "Behruz"), ("Mahmudov", "Shohruh"),
    ("Normatova", "Zuhra"), ("Olimov", "Sanjar"), ("Po'latov", "Abbos"), ("Qosimova", "Mohinur"),
]

STUDENTS = [
    "Rasulov Akmal", "Saidov Bobur", "Toshpo'latov Jahongir", "Umarov Diyor", "Valiyev Rustam",
    "Xasanov Otabek", "Yo'ldoshev Sardor", "Zokirov Nodir", "Abdurahmonov Elyor", "Baxtiyorov Firdavs",
    "Choriyev Ziyod", "Ermatov Lochin",
]


class Command(BaseCommand):
    help = "Qalqon uchun demo ma'lumotlar: binolar, admin, sardor, a'zolar, naryadlar va qonunbuzarliklar."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="demo1234")

    @transaction.atomic
    def handle(self, password, **options):
        rnd = random.Random(7)
        faculties = list(Faculty.objects.all())
        if not faculties:
            faculties = [Faculty.objects.create(name=n, short_name=s) for n, s in (
                ("Iqtisodiyot fakulteti", "IQT"), ("Pedagogika fakulteti", "PED"),
                ("Filologiya fakulteti", "FIL"), ("Axborot texnologiyalari fakulteti", "AT"))]

        buildings = [
            Building.objects.get_or_create(name=n, defaults={"short_name": s, "kind": k, "latitude": la,
                                                             "longitude": ln, "radius_m": 120})[0]
            for n, s, k, la, ln in BUILDINGS
        ]
        dorms = [b for b in buildings if b.kind == Building.Kind.DORM]

        def account(username, first, last, role, faculty, **extra):
            user, created = User.objects.get_or_create(username=username, defaults={
                "first_name": first, "last_name": last, "role": role, "faculty": faculty, **extra})
            if created:
                user.set_password(password)
                user.save()
            return user

        account("qalqon_admin", "Bahodir", "Rahimov", User.Role.QALQON_ADMIN, faculties[0])
        leader = account("sardor", "Akbar", "Tojiyev", User.Role.QALQON_LEADER, faculties[0], phone="+998 90 111 22 33")
        MemberProfile.objects.get_or_create(user=leader, defaults={"group_name": "21-01", "course": 4,
                                                                  "direction": "Iqtisodiyot"})
        members = []
        for i, (last, first) in enumerate(MEMBERS):
            fac = faculties[i % len(faculties)]
            m = account(f"qalqon{i + 1}", first, last, User.Role.QALQON_MEMBER, fac,
                        phone=f"+998 9{i % 10} 555 {10 + i:02d} {20 + i:02d}")
            MemberProfile.objects.get_or_create(user=m, defaults={
                "group_name": f"{22 - i % 4}-{i % 6 + 1:02d}", "course": i % 4 + 1,
                "direction": fac.name.replace(" fakulteti", ""), "dormitory": dorms[i % len(dorms)],
                "room": str(100 + i * 7),
            })
            members.append(m)

        if Duty.objects.exists():
            self.stdout.write("Naryadlar allaqachon mavjud — faqat foydalanuvchilar tekshirildi.")
            return

        tutors = list(User.objects.filter(role=User.Role.TUTOR))
        today = timezone.localdate()
        now = timezone.now()
        categories = [c for c, _ in Violation.Category.choices]
        weights = [6, 2, 8, 7, 2, 3, 1, 4, 1, 3, 2]
        for offset in range(-21, 15):
            day = today + dt.timedelta(days=offset)
            for b in rnd.sample(dorms, rnd.randint(1, 2)):
                duty = Duty.objects.create(date=day, start_time=dt.time(18), end_time=dt.time(22), building=b,
                                           latitude=b.latitude, longitude=b.longitude, radius_m=b.radius_m,
                                           created_by=leader)
                for m in rnd.sample(members, 2):
                    dm = DutyMember.objects.create(duty=duty, member=m)
                    if duty.start_dt > now:
                        continue
                    roll = rnd.random()
                    if roll < 0.1:
                        continue  # chiqmagan
                    dm.status = DutyMember.Status.ACTIVE
                    dm.started_at = duty.start_dt + dt.timedelta(minutes=rnd.choice([-5, 0, 3, 8, 25]))
                    dm.start_lat, dm.start_lng = b.latitude, b.longitude
                    dm.start_accuracy, dm.start_distance = rnd.randint(5, 30), rnd.randint(3, 60)
                    if duty.end_dt < now and roll > 0.15:
                        dm.status = DutyMember.Status.FINISHED
                        dm.finished_at = duty.end_dt + dt.timedelta(minutes=rnd.randint(1, 30))
                        dm.finish_lat, dm.finish_lng = b.latitude, b.longitude
                        dm.finish_accuracy, dm.finish_distance = rnd.randint(5, 30), rnd.randint(3, 60)
                    dm.save()
                    bias = {0: 1.6, 1: 0.6, 2: 0.25}.get(dorms.index(b), 1)
                    for _ in range(int(rnd.random() * 3 * bias)):
                        fac = rnd.choice(faculties)
                        fac_tutors = [t for t in tutors if t.faculty_id == fac.pk]
                        Violation.objects.create(
                            duty_member=dm,
                            occurred_at=min(now, duty.start_dt + dt.timedelta(minutes=rnd.randint(10, 230))),
                            category=rnd.choices(categories, weights)[0],
                            student_name=rnd.choice(STUDENTS) + " " + rnd.choice(["o'g'li", "Akmalovich", "Sobirovich"]),
                            faculty=fac, direction=fac.name.replace(" fakulteti", ""),
                            group_name=f"{rnd.randint(21, 24)}-{rnd.randint(1, 9):02d}", course=rnd.randint(1, 4),
                            dormitory=b, room=str(rnd.randint(101, 512)),
                            tutor=rnd.choice(fac_tutors) if fac_tutors else None,
                            tutor_name="" if fac_tutors else "Ko'rsatilmagan",
                            description="Talaba bilan suhbat o'tkazildi, tushuntirish xati olindi.",
                            confirmed_at=dm.finished_at,
                        )
        self.stdout.write(self.style.SUCCESS(
            f"Qalqon demo ma'lumotlari yaratildi. Kirish: qalqon_admin / sardor / qalqon1…qalqon{len(MEMBERS)} — "
            f"parol: {password}"
        ))
