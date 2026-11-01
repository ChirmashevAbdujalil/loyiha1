import datetime as dt
import shutil
import tempfile
from io import BytesIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Faculty, Notification, User

from . import services
from .models import Building, Duty, DutyMember, LocationLog, MemberProfile, Violation, distance_m

MEDIA = tempfile.mkdtemp()
TTJ = (41.338210, 69.334410)
# ~55 m shimolda va ~1.1 km uzoqda
NEAR = (41.338700, 69.334410)
FAR = (41.348210, 69.334410)


def png():
    return SimpleUploadedFile("rasm.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA)
class DutyFlowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.faculty = Faculty.objects.create(name="Iqtisodiyot fakulteti", short_name="IQT")
        self.leader = User.objects.create_user("sardor", password="x12345", role=User.Role.QALQON_LEADER,
                                               first_name="Akbar", last_name="Tojiyev", faculty=self.faculty)
        self.m1 = User.objects.create_user("a1", password="x12345", role=User.Role.QALQON_MEMBER,
                                           first_name="Sherzod", last_name="Aliyev", faculty=self.faculty)
        self.m2 = User.objects.create_user("a2", password="x12345", role=User.Role.QALQON_MEMBER,
                                           first_name="Feruza", last_name="Bakirova", faculty=self.faculty)
        self.ttj = Building.objects.create(name="1-son TTJ", short_name="TTJ-1", latitude=TTJ[0],
                                           longitude=TTJ[1], radius_m=100)

    def _duty(self, date=None, start=dt.time(18), end=dt.time(22)):
        self.client.force_login(self.leader)
        date = date or timezone.localdate()
        r = self.client.post(reverse("qalqon:duty_create"), {
            "date": date.isoformat(), "start_time": start.strftime("%H:%M"), "end_time": end.strftime("%H:%M"),
            "building": self.ttj.pk, "latitude": TTJ[0], "longitude": TTJ[1], "radius_m": 100,
            "members": [self.m1.pk, self.m2.pk],
        })
        self.assertEqual(r.status_code, 302, r.context and r.context["form"].errors)
        return Duty.objects.latest("pk")

    def _at(self, duty, hour, minute=0, day_offset=0):
        moment = dt.datetime.combine(duty.date + dt.timedelta(days=day_offset), dt.time(hour, minute))
        return mock.patch("django.utils.timezone.now", return_value=timezone.make_aware(moment))

    def test_distance(self):
        self.assertAlmostEqual(distance_m(*TTJ, *NEAR), 54.5, delta=2)
        self.assertGreater(distance_m(*TTJ, *FAR), 1000)

    def test_create_range_notifies_members(self):
        self.client.force_login(self.leader)
        today = timezone.localdate()
        self.client.post(reverse("qalqon:duty_create"), {
            "date": today.isoformat(), "date_to": (today + dt.timedelta(days=2)).isoformat(),
            "start_time": "18:00", "end_time": "22:00", "building": self.ttj.pk,
            "latitude": TTJ[0], "longitude": TTJ[1], "radius_m": 100, "members": [self.m1.pk],
        })
        self.assertEqual(Duty.objects.count(), 3)
        self.assertEqual(Notification.objects.filter(user=self.m1, kind="duty").count(), 3)

    def test_full_duty_cycle(self):
        duty = self._duty()
        dm = DutyMember.objects.get(duty=duty, member=self.m1)
        self.client.force_login(self.m1)
        start_url = reverse("qalqon:duty_start", args=[dm.pk])

        # Juda erta — tugma ishlamaydi
        with self._at(duty, 12):
            self.client.post(start_url, {"latitude": NEAR[0], "longitude": NEAR[1], "accuracy": 10})
        dm.refresh_from_db()
        self.assertEqual(dm.status, DutyMember.Status.SCHEDULED)

        # Vaqt to'g'ri, lekin hududdan tashqarida
        with self._at(duty, 18, 2):
            self.client.post(start_url, {"latitude": FAR[0], "longitude": FAR[1], "accuracy": 10})
        dm.refresh_from_db()
        self.assertEqual(dm.status, DutyMember.Status.SCHEDULED)
        self.assertFalse(LocationLog.objects.get().success)

        # GPS aniqligi past
        with self._at(duty, 18, 3):
            self.client.post(start_url, {"latitude": NEAR[0], "longitude": NEAR[1], "accuracy": 900})
        dm.refresh_from_db()
        self.assertEqual(dm.status, DutyMember.Status.SCHEDULED)

        # Hududda — boshlanadi
        with self._at(duty, 18, 4):
            self.client.post(start_url, {"latitude": NEAR[0], "longitude": NEAR[1], "accuracy": 12})
        dm.refresh_from_db()
        self.assertEqual(dm.status, DutyMember.Status.ACTIVE)
        self.assertLess(dm.start_distance, 100)

        # Qonunbuzarlik qayd etish
        with self._at(duty, 19, 30):
            r = self.client.post(reverse("qalqon:violation_add", args=[dm.pk]), {
                "occurred_at": f"{duty.date:%Y-%m-%d}T19:20", "category": "smoking",
                "student_name": "Rasulov Akmal", "faculty": self.faculty.pk, "direction": "Iqtisodiyot",
                "group_name": "22-03", "course": 2, "dormitory": self.ttj.pk, "room": "312",
                "tutor_name": "Karimov J.", "description": "TTJ yo'lagida chekdi",
            })
            self.assertEqual(r.status_code, 302, r.context and r.context["form"].errors)
        v = Violation.objects.get()
        self.assertTrue(Notification.objects.filter(user=self.leader, kind="violation").exists())

        finish_url = reverse("qalqon:duty_finish", args=[dm.pk])
        # 22:00 dan oldin yakunlab bo'lmaydi
        with self._at(duty, 21, 30):
            r = self.client.get(finish_url)
        self.assertEqual(r.status_code, 302)

        # Tasdiqsiz / rasmsiz — yakunlanmaydi
        with self._at(duty, 22, 5):
            self.client.post(finish_url, {"latitude": NEAR[0], "longitude": NEAR[1], "accuracy": 10})
        dm.refresh_from_db()
        self.assertEqual(dm.status, DutyMember.Status.ACTIVE)

        # Hududdan tashqarida — yakunlanmaydi
        with self._at(duty, 22, 6):
            self.client.post(finish_url, {"latitude": FAR[0], "longitude": FAR[1], "accuracy": 10,
                                          "confirm": "on", "photo": png()})
        dm.refresh_from_db()
        self.assertEqual(dm.status, DutyMember.Status.ACTIVE)

        # Hammasi joyida
        with self._at(duty, 22, 7):
            r = self.client.post(finish_url, {"latitude": NEAR[0], "longitude": NEAR[1], "accuracy": 10,
                                              "confirm": "on", "photo": png()})
        self.assertEqual(r.status_code, 302)
        dm.refresh_from_db()
        v.refresh_from_db()
        self.assertEqual(dm.status, DutyMember.Status.FINISHED)
        self.assertTrue(dm.photo)
        self.assertIsNotNone(v.confirmed_at)

        # Sherigi (m2) chiqmagan — statistikada ko'rinadi
        with self._at(duty, 23, 30):
            stats = services.build_stats(duty.date, duty.date)
        self.assertEqual(stats["status_counts"]["finished"], 1)
        self.assertEqual(stats["status_counts"]["missed"], 1)
        self.assertEqual(stats["violations_total"], 1)
        self.assertEqual(stats["by_place"][0]["label"], self.ttj.name)

    def test_start_only_on_duty_day(self):
        duty = self._duty(date=timezone.localdate() + dt.timedelta(days=3))
        dm = DutyMember.objects.get(duty=duty, member=self.m1)
        self.client.force_login(self.m1)
        r = self.client.get(reverse("qalqon:duty_detail", args=[duty.pk]))
        self.assertNotContains(r, "Naryadni boshlash</button>")
        with self._at(duty, 18, 0, day_offset=-1):
            self.assertEqual(dm.start_state, "not_today")
        with self._at(duty, 17, 30):
            self.assertEqual(dm.start_state, "ok")
            r = self.client.get(reverse("qalqon:duty_detail", args=[duty.pk]))
            self.assertContains(r, "Naryadni boshlash</button>")

    def test_other_member_cannot_act(self):
        duty = self._duty()
        dm = DutyMember.objects.get(duty=duty, member=self.m1)
        self.client.force_login(self.m2)
        with self._at(duty, 18, 5):
            r = self.client.post(reverse("qalqon:duty_start", args=[dm.pk]),
                                 {"latitude": NEAR[0], "longitude": NEAR[1], "accuracy": 5})
        self.assertEqual(r.status_code, 403)

    def test_permissions(self):
        self.client.force_login(self.m1)
        for name in ("qalqon:duty_create", "qalqon:stats", "qalqon:member_list", "qalqon:violation_list"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(self.client.get(reverse("qalqon:calendar")).status_code, 200)
        self.client.force_login(self.leader)
        self.assertEqual(self.client.get(reverse("qalqon:stats")).status_code, 200)

    def test_import_members(self):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(["F.I.Sh", "Fakultet", "Yo'nalish", "Guruh", "Kurs", "Telefon"])
        ws.append(["Karimov Jasur Akmalovich", "IQT", "Iqtisodiyot", "21-03", "2", "+998901112233"])
        ws.append(["Yangi Talaba", "Tarix fakulteti", "Tarix", "22-01", 1, ""])
        ws.append(["Karimov Jasur", "IQT", "", "", "", ""])  # dublikat
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        result = services.import_members(services.read_rows(buf))
        self.assertEqual(len(result["created"]), 2)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["new_faculties"], ["Tarix fakulteti"])
        u = User.objects.get(last_name="Karimov")
        self.assertEqual(u.role, User.Role.QALQON_MEMBER)
        self.assertEqual(u.middle_name, "Akmalovich")
        self.assertEqual(u.qalqon_profile.course, 2)
        self.assertTrue(u.check_password(result["created"][0]["password"]))
        self.assertTrue(MemberProfile.objects.filter(user__last_name="Yangi").exists())


class PlatformSeparationTests(TestCase):
    def setUp(self):
        self.head = User.objects.create_user("boss", password="x12345", role=User.Role.HEAD)
        self.member = User.objects.create_user("a1", password="x12345", role=User.Role.QALQON_MEMBER)
        self.tutor = User.objects.create_user("t1", password="x12345", role=User.Role.TUTOR)
        Notification.objects.create(user=self.head, kind="duty", title="Qalqon xabari")
        Notification.objects.create(user=self.head, kind="new_task", title="Ijro xabari")

    def test_sidebar_shows_only_current_platform(self):
        self.client.force_login(self.head)
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Tasdiqlash uchun")
        self.assertNotContains(r, "Binolar va TTJ")
        self.assertContains(r, "platform-switch")
        r = self.client.get(reverse("qalqon:calendar"))
        self.assertContains(r, "Binolar va TTJ")
        self.assertNotContains(r, "Tasdiqlash uchun")

    def test_notifications_are_split(self):
        self.client.force_login(self.head)
        data = self.client.get(reverse("notification_feed") + "?p=qalqon").json()
        self.assertEqual([i["title"] for i in data["items"]], ["Qalqon xabari"])
        data = self.client.get(reverse("notification_feed") + "?p=ijro").json()
        self.assertEqual([i["title"] for i in data["items"]], ["Ijro xabari"])

    def test_single_platform_users(self):
        self.client.force_login(self.member)
        r = self.client.get(reverse("qalqon:calendar"))
        self.assertNotContains(r, "platform-switch")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)
        self.client.force_login(self.tutor)
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "platform-switch")
        self.assertEqual(self.client.get(reverse("qalqon:calendar")).status_code, 403)

    def test_qalqon_login_page(self):
        r = self.client.post(reverse("qalqon:login"), {"username": "a1", "password": "x12345"})
        self.assertRedirects(r, reverse("qalqon:calendar"))


def _make_docx(rows, with_photo=True):
    """Sinov uchun institut ro'yxati shaklidagi .docx (to'qima ma'lumotlar)."""
    from docx import Document
    from PIL import Image

    doc = Document()
    doc.add_paragraph("“Qalqon” jamoatchilik guruhi a’zolari umumiy roʻyhati")
    table = doc.add_table(rows=1, cols=5)
    for cell, text in zip(table.rows[0].cells, ["T/R", "F.I.SH, Tugʻilgan yili va joyi", "Rasmi",
                                                "Fakulteti,kurs, yoʻnalish va guruhi",
                                                "Yashash joyi va pasport ma’lumotlari"]):
        cell.text = text
    img = BytesIO()
    Image.new("RGB", (40, 50), (120, 80, 60)).save(img, "PNG")
    for i, (name, study, personal) in enumerate(rows, 1):
        cells = table.add_row().cells
        cells[0].text, cells[1].text, cells[3].text, cells[4].text = str(i), name, study, personal
        if with_photo:
            img.seek(0)
            cells[2].paragraphs[0].add_run().add_picture(img)
    out = BytesIO()
    doc.save(out)
    out.seek(0)
    out.name = "azolar.docx"
    return out


SAMPLE_ROWS = [
    ("Sinovov Anvar Bahodir oʻgʻli\n“Qalqon” jamoatchilik guruhi sardori\n(97)-111-22-33",
     "Mexanika va kimyo muhandisligi fakulteti 4-bosqich K-07-23-guruh talabasi",
     "AE1234567\n50101055000017\nAndijon viloyati Buloqboshi tumani Navroʻz MFY 1-uy"),
    ("Namunova Sardorbek Ali ogʻli\n(90)-222-33-44",  # ismida "Sardor" bor, lekin sardor emas
     "Iqdisodiyot va boshqaruv fakulteti Moliya va moliyaviy texnalogiyalar K-16-25 guruh talabasi",
     "AD 7654321\n62706065000011\nFargʻona viloyati Quva tumani Namuna mfy 5-uy"),
    ("Misolova Laylo\n(94)-333-44-55",
     "IB va KT fakulteti | Mextronika va robototexmika yoʻnalishi K 24-25 | guruh talabasi",
     "AD 123456789\n537250000000 | Oltinkol tumani, Namuna MFY"),
]


@override_settings(MEDIA_ROOT=MEDIA)
class DocxImportTests(TestCase):
    def test_parse(self):
        from .docx_import import parse_docx

        recs = parse_docx(_make_docx(SAMPLE_ROWS))
        a, b, c = recs
        self.assertEqual((a.last_name, a.first_name, a.middle_name), ("Sinovov", "Anvar", "Bahodir oʻgʻli"))
        self.assertTrue(a.is_leader)
        self.assertFalse(b.is_leader)
        self.assertEqual(a.phone, "+998 97 111 22 33")
        self.assertEqual((a.faculty_short, a.group_name, a.course, a.course_derived), ("MKMF", "K-07-23", 4, False))
        self.assertEqual((a.passport, a.pinfl, a.birth_date, a.gender),
                         ("AE1234567", "50101055000017", dt.date(2005, 1, 1), "m"))
        self.assertEqual((a.region, a.district, a.address), ("Andijon viloyati", "Buloqboshi tumani", "Navroʻz MFY 1-uy"))
        self.assertIsNotNone(a.photo)
        self.assertEqual(b.middle_name, "Ali oʻgʻli")
        self.assertEqual((b.faculty_short, b.direction, b.course, b.course_derived),
                         ("IBF", "Moliya va moliyaviy texnologiyalar", 2, True))
        self.assertEqual(b.gender, "f")  # JSHSHIR 6 bilan boshlanadi
        self.assertTrue(any("jins" in w for w in b.warnings))
        self.assertEqual((c.faculty_short, c.direction, c.group_name), ("IBKTF", "Mexatronika va robototexnika", "K-24-25"))
        self.assertTrue(any("9 xonali" in w for w in c.warnings))
        self.assertTrue(any("JSHSHIR 12" in w for w in c.warnings))
        self.assertEqual(c.region, "")

    def test_save_is_idempotent(self):
        from .docx_import import parse_docx, save_records

        result = save_records(parse_docx(_make_docx(SAMPLE_ROWS)))
        self.assertEqual(len(result["created"]), 3)
        self.assertEqual(len(result["new_faculties"]), 3)
        leader = User.objects.get(last_name="Sinovov")
        self.assertEqual(leader.role, User.Role.QALQON_LEADER)
        self.assertTrue(leader.check_password(result["created"][0]["password"]))
        p = leader.qalqon_profile
        self.assertTrue(p.photo)
        self.assertEqual(p.pinfl, "50101055000017")
        self.assertEqual(User.objects.get(last_name="Namunova").role, User.Role.QALQON_MEMBER)

        again = save_records(parse_docx(_make_docx(SAMPLE_ROWS)))
        self.assertEqual((len(again["created"]), len(again["updated"])), (0, 3))
        self.assertEqual(User.objects.filter(role__startswith="qalqon").count(), 3)

    def test_web_upload_and_detail(self):
        boss = User.objects.create_user("boss", password="x12345", role=User.Role.QALQON_ADMIN)
        self.client.force_login(boss)
        r = self.client.post(reverse("qalqon:member_import"), {"file": _make_docx(SAMPLE_ROWS)})
        self.assertContains(r, "Qo'shildi: 3")
        u = User.objects.get(last_name="Sinovov")
        r = self.client.get(reverse("qalqon:member_detail", args=[u.pk]))
        self.assertContains(r, "AE1234567")
        self.assertContains(r, "Buloqboshi tumani")
        self.assertEqual(self.client.get(reverse("qalqon:member_photo", args=[u.pk])).status_code, 200)
        # Oddiy a'zo pasport ma'lumotlarini ko'ra olmaydi
        self.client.force_login(User.objects.get(last_name="Namunova"))
        self.assertEqual(self.client.get(reverse("qalqon:member_detail", args=[u.pk])).status_code, 403)
