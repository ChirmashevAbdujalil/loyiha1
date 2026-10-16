import datetime as dt
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Assignment, Faculty, Notification, Submission, Task, User

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class WorkflowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.head = User.objects.create_user("boss", password="pass12345", role=User.Role.HEAD,
                                             first_name="Doniyor", last_name="Sarimsoqov")
        self.faculty = Faculty.objects.create(name="Iqtisodiyot fakulteti", short_name="IQT")
        self.t1 = User.objects.create_user("t1", password="pass12345", first_name="Jasur",
                                           last_name="Karimov", faculty=self.faculty)
        self.t2 = User.objects.create_user("t2", password="pass12345", first_name="Madina",
                                           last_name="Yusupova", faculty=self.faculty)

    def _create_task(self):
        self.client.force_login(self.head)
        deadline = timezone.localtime() + dt.timedelta(days=2)
        response = self.client.post(reverse("task_create"), {
            "title": "Ma'naviyat soati",
            "description": "Guruhlarda o'tkazilsin",
            "execution_date": timezone.localdate().isoformat(),
            "deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
            "tutors": [self.t1.pk, self.t2.pk],
            "files": [SimpleUploadedFile("buyruq.pdf", b"%PDF-1.4 test", content_type="application/pdf")],
        })
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["form"].errors)
        return Task.objects.get()

    def test_faculty_and_tutor_creation(self):
        self.client.force_login(self.head)
        self.client.post(reverse("faculty_list"), {"name": "Pedagogika fakulteti", "short_name": "PED"})
        fac = Faculty.objects.get(name="Pedagogika fakulteti")
        response = self.client.post(reverse("tutor_create"), {
            "last_name": "Tursunov", "first_name": "Bekzod", "faculty": fac.pk,
            "username": "bekzod", "password": "secret123", "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        tutor = User.objects.get(username="bekzod")
        self.assertEqual(tutor.role, User.Role.TUTOR)
        self.assertEqual(tutor.faculty, fac)
        self.assertTrue(tutor.check_password("secret123"))

    def test_full_cycle(self):
        task = self._create_task()
        self.assertEqual(task.assignments.count(), 2)
        self.assertEqual(task.files.count(), 1)
        self.assertEqual(Notification.objects.filter(kind="new_task").count(), 2)

        # Tyutor ijroni yopadi
        a = Assignment.objects.get(task=task, tutor=self.t1)
        self.client.force_login(self.t1)
        self.assertEqual(self.client.get(reverse("task_file", args=[task.files.get().pk])).status_code, 200)
        response = self.client.post(reverse("assignment_submit", args=[a.pk]), {
            "comment": "Bajarildi", "link": "https://t.me/post/1",
        })
        self.assertEqual(response.status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.status, Assignment.Status.SUBMITTED)
        self.assertTrue(Notification.objects.filter(user=self.head, kind="submitted").exists())

        # Boshqa tyutor bu ijroni ko'ra olmaydi
        self.client.force_login(self.t2)
        self.assertEqual(self.client.get(reverse("assignment_detail", args=[a.pk])).status_code, 403)

        # Bo'lim boshlig'i tasdiqlaydi
        self.client.force_login(self.head)
        self.client.post(reverse("assignment_review", args=[a.pk]), {"action": "approve", "comment": "Yaxshi"})
        a.refresh_from_db()
        self.assertEqual(a.status, Assignment.Status.APPROVED)
        self.assertTrue(Notification.objects.filter(user=self.t1, kind="approved").exists())

        # Hisobot: t1 — bajardi, t2 — muddati kelmagan; muddatdan keyingi holatda — bajarmadi
        data = services.build_report(Assignment.objects.select_related("task", "tutor", "tutor__faculty"),
                                     timezone.now())
        states = {r["tutor"].username: r["cells"][0]["state"] for r in data["rows"]}
        self.assertEqual(states, {"t1": services.REPORT_DONE, "t2": services.REPORT_NOT_DUE})
        later = task.deadline + dt.timedelta(hours=1)
        data = services.build_report(Assignment.objects.select_related("task", "tutor", "tutor__faculty"), later)
        states = {r["tutor"].username: r["cells"][0]["state"] for r in data["rows"]}
        self.assertEqual(states["t2"], services.REPORT_NOT_DONE)

        # Tasdiqdan oldingi vaqt holatida — tasdiqlashda
        sub = Submission.objects.get()
        sub.created_at = sub.reviewed_at - dt.timedelta(hours=1)
        sub.save(update_fields=["created_at"])
        data = services.build_report(Assignment.objects.select_related("task", "tutor", "tutor__faculty"),
                                     sub.reviewed_at - dt.timedelta(minutes=1))
        states = {r["tutor"].username: r["cells"][0]["state"] for r in data["rows"]}
        self.assertEqual(states["t1"], services.REPORT_REVIEW)

        response = self.client.get(reverse("report_export"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])

    def test_reject_requires_comment_and_allows_resubmit(self):
        task = self._create_task()
        a = Assignment.objects.get(task=task, tutor=self.t1)
        self.client.force_login(self.t1)
        self.client.post(reverse("assignment_submit", args=[a.pk]), {"comment": "Tayyor"})
        self.client.force_login(self.head)
        self.client.post(reverse("assignment_review", args=[a.pk]), {"action": "reject", "comment": ""})
        a.refresh_from_db()
        self.assertEqual(a.status, Assignment.Status.SUBMITTED)
        self.client.post(reverse("assignment_review", args=[a.pk]), {"action": "reject", "comment": "Rasm yo'q"})
        a.refresh_from_db()
        self.assertEqual(a.status, Assignment.Status.REJECTED)
        self.client.force_login(self.t1)
        self.client.post(reverse("assignment_submit", args=[a.pk]), {"comment": "Rasm qo'shildi"})
        a.refresh_from_db()
        self.assertEqual(a.status, Assignment.Status.SUBMITTED)
        self.assertEqual(a.submissions.count(), 2)

    def test_tutor_cannot_access_head_pages(self):
        self.client.force_login(self.t1)
        for name in ("task_create", "tutor_list", "faculty_list", "report", "review_queue"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_dashboard_shows_tutor_names(self):
        self._create_task()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Karimov J.")
        self.assertContains(response, "Yusupova M.")
        response = self.client.get(reverse("dashboard"), {"date": timezone.localdate().isoformat(), "tutor": self.t1.pk})
        self.assertContains(response, "Ma&#x27;naviyat soati")
