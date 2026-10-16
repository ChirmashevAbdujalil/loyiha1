import os

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Faculty(models.Model):
    name = models.CharField("Fakultet nomi", max_length=255, unique=True)
    short_name = models.CharField("Qisqa nomi", max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Fakultet"
        verbose_name_plural = "Fakultetlar"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def label(self):
        return self.short_name or self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        HEAD = "head", "Bo'lim boshlig'i"
        TUTOR = "tutor", "Tyutor"

    role = models.CharField("Rol", max_length=10, choices=Role.choices, default=Role.TUTOR)
    middle_name = models.CharField("Otasining ismi", max_length=150, blank=True)
    phone = models.CharField("Telefon", max_length=30, blank=True)
    position = models.CharField("Lavozimi", max_length=255, blank=True)
    faculty = models.ForeignKey(
        Faculty,
        verbose_name="Fakultet",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tutors",
    )

    class Meta:
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name

    @property
    def is_head(self):
        return self.role == self.Role.HEAD or self.is_superuser

    @property
    def is_tutor(self):
        return self.role == self.Role.TUTOR and not self.is_superuser

    @property
    def full_name(self):
        name = f"{self.last_name} {self.first_name}".strip()
        return name or self.username

    @property
    def short_name(self):
        """Familiya I. — kalendar katakchalari uchun."""
        if self.last_name and self.first_name:
            return f"{self.last_name} {self.first_name[0]}."
        return self.full_name

    @property
    def initials(self):
        parts = [p for p in (self.last_name, self.first_name) if p]
        if not parts:
            return self.username[:2].upper()
        return "".join(p[0] for p in parts[:2]).upper()


class Task(models.Model):
    title = models.CharField("Topshiriq mavzusi", max_length=500)
    description = models.TextField("Topshiriq mazmuni", blank=True)
    execution_date = models.DateField("Ijro kuni")
    deadline = models.DateTimeField("Ijro muddati")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_tasks"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Topshiriq"
        verbose_name_plural = "Topshiriqlar"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} {self.title}"

    @property
    def number(self):
        return f"№{self.pk:04d}" if self.pk else "№—"

    def get_absolute_url(self):
        return reverse("task_detail", args=[self.pk])

    @property
    def is_overdue(self):
        return timezone.now() > self.deadline


def task_file_path(instance, filename):
    return f"tasks/{instance.task_id}/{filename}"


def submission_file_path(instance, filename):
    return f"submissions/{instance.submission.assignment_id}/{filename}"


class TaskFile(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to=task_file_path)
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name

    @property
    def extension(self):
        return os.path.splitext(self.original_name)[1].lstrip(".").lower()


class Assignment(models.Model):
    """Topshiriqning bitta tyutorga biriktirilishi (ijro)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Bajarilmoqda"
        SUBMITTED = "submitted", "Tasdiqlashda"
        APPROVED = "approved", "Bajarildi"
        REJECTED = "rejected", "Qaytarilgan"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="assignments")
    tutor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignments"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    seen_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ijro"
        verbose_name_plural = "Ijrolar"
        unique_together = [("task", "tutor")]
        ordering = ["task__deadline"]

    def __str__(self):
        return f"{self.task} → {self.tutor}"

    def get_absolute_url(self):
        return reverse("assignment_detail", args=[self.pk])

    # Ko'rinish holati: kalendar va ro'yxatlardagi rang shu bo'yicha.
    @property
    def display_status(self):
        if self.status == self.Status.APPROVED:
            return "approved"
        if self.status == self.Status.SUBMITTED:
            return "submitted"
        if timezone.now() > self.task.deadline:
            return "overdue"
        if self.status == self.Status.REJECTED:
            return "rejected"
        return "pending"

    @property
    def display_status_label(self):
        return STATUS_LABELS[self.display_status]

    @property
    def is_late(self):
        return bool(self.submitted_at and self.submitted_at > self.task.deadline)

    @property
    def can_submit(self):
        return self.status in (self.Status.PENDING, self.Status.REJECTED)

    @property
    def last_submission(self):
        subs = list(self.submissions.all())
        return subs[0] if subs else None


STATUS_LABELS = {
    "approved": "Bajarildi",
    "submitted": "Tasdiqlashda",
    "overdue": "Muddati o'tgan",
    "rejected": "Qaytarilgan",
    "pending": "Bajarilmoqda",
}


class Submission(models.Model):
    """Tyutorning "Ijroni yopish" bo'yicha yuborgan hisoboti."""

    class Decision(models.TextChoices):
        WAITING = "waiting", "Ko'rib chiqilmoqda"
        APPROVED = "approved", "Tasdiqlandi"
        REJECTED = "rejected", "Qaytarildi"

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    comment = models.TextField("Izoh")
    link = models.URLField("Havola", max_length=1000, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    decision = models.CharField(max_length=10, choices=Decision.choices, default=Decision.WAITING)
    review_comment = models.TextField("Bo'lim boshlig'i izohi", blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.assignment} ({self.get_decision_display()})"


class SubmissionFile(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to=submission_file_path)
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)

    def __str__(self):
        return self.original_name

    @property
    def extension(self):
        return os.path.splitext(self.original_name)[1].lstrip(".").lower()


class Notification(models.Model):
    class Kind(models.TextChoices):
        NEW_TASK = "new_task", "Yangi topshiriq"
        SUBMITTED = "submitted", "Ijro yuborildi"
        APPROVED = "approved", "Tasdiqlandi"
        REJECTED = "rejected", "Qaytarildi"
        UPDATED = "updated", "O'zgartirildi"
        REMINDER = "reminder", "Eslatma"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
