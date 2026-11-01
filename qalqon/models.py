import datetime as dt
import math
import os

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import Faculty


latitude_validators = [MinValueValidator(-90), MaxValueValidator(90)]
longitude_validators = [MinValueValidator(-180), MaxValueValidator(180)]


def distance_m(lat1, lng1, lat2, lng2):
    """Ikki nuqta orasidagi masofa (metr) — haversine formulasi."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Building(models.Model):
    class Kind(models.TextChoices):
        DORM = "dorm", "TTJ (talabalar turar joyi)"
        STUDY = "study", "O'quv binosi"
        OTHER = "other", "Boshqa"

    name = models.CharField("Nomi", max_length=255, unique=True)
    short_name = models.CharField("Qisqa nomi", max_length=50, blank=True)
    kind = models.CharField("Turi", max_length=10, choices=Kind.choices, default=Kind.DORM)
    address = models.CharField("Manzil", max_length=500, blank=True)
    latitude = models.DecimalField("Kenglik (latitude)", max_digits=9, decimal_places=6,
                                   validators=latitude_validators)
    longitude = models.DecimalField("Uzunlik (longitude)", max_digits=9, decimal_places=6,
                                    validators=longitude_validators)
    radius_m = models.PositiveIntegerField("Ruxsat etilgan radius (metr)", default=100,
                                           validators=[MinValueValidator(10), MaxValueValidator(5000)])
    is_active = models.BooleanField("Faol", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bino"
        verbose_name_plural = "Binolar"
        ordering = ["kind", "name"]

    def __str__(self):
        return self.name

    @property
    def label(self):
        return self.short_name or self.name


def member_photo_path(instance, filename):
    # Har safar yangi nom — brauzer keshida eski rasm qolib ketmasligi uchun
    import secrets

    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    return f"qalqon/members/{instance.user_id}_{secrets.token_hex(4)}{ext}"


class MemberProfile(models.Model):
    """Qalqon a'zosining talabalik va shaxsiy ma'lumotlari (F.I.Sh, telefon, fakultet — User'da)."""

    class Gender(models.TextChoices):
        MALE = "m", "Erkak"
        FEMALE = "f", "Ayol"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="qalqon_profile")
    photo = models.FileField("Rasmi", upload_to=member_photo_path, blank=True)
    birth_date = models.DateField("Tug'ilgan sanasi", null=True, blank=True)
    gender = models.CharField("Jinsi", max_length=1, choices=Gender.choices, blank=True)
    passport = models.CharField("Pasport seriya va raqami", max_length=20, blank=True)
    passport_issued = models.DateField("Pasport berilgan sana", null=True, blank=True)
    pinfl = models.CharField("JSHSHIR", max_length=14, blank=True, db_index=True)
    region = models.CharField("Viloyat", max_length=100, blank=True)
    district = models.CharField("Tuman / shahar", max_length=100, blank=True)
    address = models.CharField("Yashash manzili", max_length=500, blank=True)
    direction = models.CharField("Yo'nalish", max_length=255, blank=True)
    group_name = models.CharField("Guruh", max_length=50, blank=True)
    course = models.PositiveSmallIntegerField("Kurs", null=True, blank=True,
                                              validators=[MinValueValidator(1), MaxValueValidator(7)])
    dormitory = models.ForeignKey(Building, verbose_name="Yashaydigan TTJ", on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name="+")
    room = models.CharField("Xona", max_length=20, blank=True)
    note = models.CharField("Izoh", max_length=500, blank=True)

    class Meta:
        verbose_name = "A'zo ma'lumoti"
        verbose_name_plural = "A'zolar ma'lumotlari"

    def __str__(self):
        return str(self.user)

    @property
    def age(self):
        if not self.birth_date:
            return None
        today = timezone.localdate()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )

    @property
    def full_address(self):
        return ", ".join(p for p in (self.region, self.district, self.address) if p)


class Duty(models.Model):
    """Naryad: sana, vaqt, joy (koordinata + radius) va navbatchi a'zolar."""

    date = models.DateField("Naryad sanasi")
    start_time = models.TimeField("Boshlanish vaqti", default=dt.time(18, 0))
    end_time = models.TimeField("Tugash vaqti", default=dt.time(22, 0))
    building = models.ForeignKey(Building, verbose_name="Bino", on_delete=models.PROTECT, related_name="duties")
    latitude = models.DecimalField("Kenglik (latitude)", max_digits=9, decimal_places=6,
                                   validators=latitude_validators)
    longitude = models.DecimalField("Uzunlik (longitude)", max_digits=9, decimal_places=6,
                                    validators=longitude_validators)
    radius_m = models.PositiveIntegerField("Ruxsat etilgan radius (metr)", default=100,
                                           validators=[MinValueValidator(10), MaxValueValidator(5000)])
    note = models.TextField("Ko'rsatma / izoh", blank=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through="DutyMember", related_name="qalqon_duties")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Naryad"
        verbose_name_plural = "Naryadlar"
        ordering = ["-date", "start_time"]

    def __str__(self):
        return f"{self.date:%d.%m.%Y} {self.start_time:%H:%M}–{self.end_time:%H:%M} · {self.building}"

    def get_absolute_url(self):
        return reverse("qalqon:duty_detail", args=[self.pk])

    @property
    def number(self):
        return f"N-{self.pk:04d}" if self.pk else "N-—"

    @property
    def start_dt(self):
        return timezone.make_aware(dt.datetime.combine(self.date, self.start_time))

    @property
    def end_dt(self):
        end_date = self.date if self.end_time > self.start_time else self.date + dt.timedelta(days=1)
        return timezone.make_aware(dt.datetime.combine(end_date, self.end_time))

    @property
    def start_window_opens(self):
        return self.start_dt - dt.timedelta(minutes=getattr(settings, "QALQON_START_EARLY_MINUTES", 60))

    @property
    def finish_window_closes(self):
        return self.end_dt + dt.timedelta(hours=getattr(settings, "QALQON_FINISH_GRACE_HOURS", 6))

    @property
    def phase(self):
        now = timezone.now()
        if now < self.start_dt:
            return "upcoming"
        if now < self.end_dt:
            return "running"
        return "past"

    def distance_to(self, lat, lng):
        return distance_m(float(self.latitude), float(self.longitude), float(lat), float(lng))

    @property
    def map_url(self):
        return f"https://www.google.com/maps?q={self.latitude},{self.longitude}"


def duty_photo_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    return f"qalqon/duty_{instance.duty_id}/member_{instance.member_id}{ext}"


class DutyMember(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Rejalashtirilgan"
        ACTIVE = "active", "Naryadda"
        FINISHED = "finished", "Yakunlangan"

    duty = models.ForeignKey(Duty, on_delete=models.CASCADE, related_name="duty_members")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="duty_memberships")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)

    started_at = models.DateTimeField(null=True, blank=True)
    start_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    start_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    start_accuracy = models.FloatField(null=True, blank=True)
    start_distance = models.FloatField(null=True, blank=True)

    finished_at = models.DateTimeField(null=True, blank=True)
    finish_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    finish_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    finish_accuracy = models.FloatField(null=True, blank=True)
    finish_distance = models.FloatField(null=True, blank=True)
    photo = models.FileField(upload_to=duty_photo_path, blank=True)
    finish_note = models.TextField("Yakuniy izoh", blank=True)

    class Meta:
        verbose_name = "Naryaddagi a'zo"
        verbose_name_plural = "Naryaddagi a'zolar"
        unique_together = [("duty", "member")]
        ordering = ["member__last_name", "member__first_name"]

    def __str__(self):
        return f"{self.duty} → {self.member}"

    def get_absolute_url(self):
        return reverse("qalqon:duty_detail", args=[self.duty_id])

    @property
    def display_status(self):
        now = timezone.now()
        if self.status == self.Status.FINISHED:
            return "finished"
        if self.status == self.Status.ACTIVE:
            return "unfinished" if now > self.duty.finish_window_closes else "active"
        if now > self.duty.end_dt:
            return "missed"
        if timezone.localdate() == self.duty.date:
            return "today"
        return "scheduled"

    @property
    def display_status_label(self):
        return DUTY_STATUS_LABELS[self.display_status]

    @property
    def is_late_start(self):
        return bool(self.started_at and self.started_at > self.duty.start_dt + dt.timedelta(minutes=10))

    # ---- tugmalar qachon chiqadi
    @property
    def start_state(self):
        """'ok' | 'not_today' | 'too_early' | 'too_late' | 'done'"""
        if self.status != self.Status.SCHEDULED:
            return "done"
        now = timezone.now()
        if timezone.localdate() != self.duty.date and now < self.duty.start_window_opens:
            return "not_today"
        if now < self.duty.start_window_opens:
            return "too_early"
        if now >= self.duty.end_dt:
            return "too_late"
        return "ok"

    @property
    def finish_state(self):
        """'ok' | 'not_started' | 'too_early' | 'too_late' | 'done'"""
        if self.status == self.Status.FINISHED:
            return "done"
        if self.status != self.Status.ACTIVE:
            return "not_started"
        now = timezone.now()
        if now < self.duty.end_dt:
            return "too_early"
        if now > self.duty.finish_window_closes:
            return "too_late"
        return "ok"

    @property
    def can_add_violation(self):
        return self.status == self.Status.ACTIVE and timezone.now() <= self.duty.finish_window_closes


DUTY_STATUS_LABELS = {
    "finished": "Yakunlangan",
    "active": "Naryadda",
    "unfinished": "Yakunlanmagan",
    "missed": "Chiqmagan",
    "today": "Bugun",
    "scheduled": "Rejalashtirilgan",
}


class LocationLog(models.Model):
    """Naryadni boshlash / yakunlash uchun har bir joylashuv tekshiruvi (audit)."""

    class Action(models.TextChoices):
        START = "start", "Boshlash"
        FINISH = "finish", "Yakunlash"

    duty_member = models.ForeignKey(DutyMember, on_delete=models.CASCADE, related_name="location_logs")
    action = models.CharField(max_length=10, choices=Action.choices)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True)
    distance = models.FloatField(null=True, blank=True)
    success = models.BooleanField(default=False)
    message = models.CharField(max_length=255, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


def violation_photo_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    return f"qalqon/violations/{timezone.now():%Y/%m}/{instance.duty_member_id}_{timezone.now():%H%M%S%f}{ext}"


class Violation(models.Model):
    class Category(models.TextChoices):
        SMOKING = "smoking", "Chekish (nos, vape)"
        ALCOHOL = "alcohol", "Spirtli ichimlik"
        LATE = "late", "Belgilangan vaqtdan kech qaytish"
        NOISE = "noise", "Shovqin, tinchlikni buzish"
        FIGHT = "fight", "Janjal, mushtlashuv"
        GUEST = "guest", "Begona shaxsni olib kirish"
        PROPERTY = "property", "Mulkka zarar yetkazish"
        SANITARY = "sanitary", "Sanitariya qoidalarini buzish"
        GAMBLING = "gambling", "Qimor o'yinlari"
        APPEARANCE = "appearance", "Odob-axloq, kiyinish qoidalari"
        OTHER = "other", "Boshqa"

    duty_member = models.ForeignKey(DutyMember, on_delete=models.CASCADE, related_name="violations")
    occurred_at = models.DateTimeField("Sodir bo'lgan vaqt", default=timezone.now)
    category = models.CharField("Qonunbuzarlik turi", max_length=12, choices=Category.choices)
    student_name = models.CharField("Talabaning F.I.Sh", max_length=255)
    faculty = models.ForeignKey(Faculty, verbose_name="Fakulteti", on_delete=models.PROTECT,
                                related_name="qalqon_violations")
    direction = models.CharField("Yo'nalishi", max_length=255, blank=True)
    group_name = models.CharField("Guruhi", max_length=50)
    course = models.PositiveSmallIntegerField("Kursi", validators=[MinValueValidator(1), MaxValueValidator(7)])
    dormitory = models.ForeignKey(Building, verbose_name="TTJ", on_delete=models.PROTECT,
                                  related_name="violations", null=True, blank=True)
    room = models.CharField("TTJ xona raqami", max_length=20, blank=True)
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Tyutori", on_delete=models.SET_NULL,
                              null=True, blank=True, related_name="qalqon_student_violations")
    tutor_name = models.CharField("Tyutori (ro'yxatda bo'lmasa)", max_length=255, blank=True)
    description = models.TextField("Maxsus izoh")
    photo = models.FileField("Rasm (ixtiyoriy)", upload_to=violation_photo_path, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Qonunbuzarlik"
        verbose_name_plural = "Qonunbuzarliklar"
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.student_name} — {self.get_category_display()}"

    @property
    def tutor_display(self):
        return self.tutor.full_name if self.tutor else self.tutor_name

    @property
    def place(self):
        """Statistika uchun joy: talabaning TTJsi, bo'lmasa naryad binosi."""
        return self.dormitory or self.duty_member.duty.building


class DataImport(models.Model):
    """Repodagi boshlang'ich ma'lumotlar arxivi qaysi bazaga allaqachon yuklanganini eslab qoladi."""

    name = models.CharField(max_length=255)
    checksum = models.CharField(max_length=64)
    loaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("name", "checksum")]

    def __str__(self):
        return f"{self.name} ({self.loaded_at:%Y-%m-%d %H:%M})"
