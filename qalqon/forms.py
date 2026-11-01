import datetime as dt
import os

from django import forms
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from core.models import Faculty, User

from .models import Building, Duty, MemberProfile, Violation

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def validate_image(f, required=True):
    if not f:
        if required:
            raise forms.ValidationError("Rasm yuklang.")
        return f
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        raise forms.ValidationError("Faqat rasm fayli (JPG, PNG, WEBP, HEIC) yuklash mumkin.")
    if f.size > settings.QALQON_MAX_PHOTO_SIZE:
        raise forms.ValidationError("Rasm hajmi 15 MB dan oshmasligi kerak.")
    return f


class BuildingForm(forms.ModelForm):
    class Meta:
        model = Building
        fields = ["name", "short_name", "kind", "address", "latitude", "longitude", "radius_m", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Masalan: 1-son talabalar turar joyi"}),
            "short_name": forms.TextInput(attrs={"placeholder": "Masalan: TTJ-1"}),
            "latitude": forms.NumberInput(attrs={"step": "0.000001", "placeholder": "41.311081"}),
            "longitude": forms.NumberInput(attrs={"step": "0.000001", "placeholder": "69.240562"}),
        }


class MemberProfileForm(forms.ModelForm):
    class Meta:
        model = MemberProfile
        fields = ["photo", "direction", "group_name", "course", "dormitory", "room", "birth_date", "gender",
                  "passport", "passport_issued", "pinfl", "region", "district", "address", "note"]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "passport_issued": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "passport": forms.TextInput(attrs={"placeholder": "AD1234567"}),
            "pinfl": forms.TextInput(attrs={"placeholder": "14 xonali raqam", "inputmode": "numeric"}),
            "region": forms.TextInput(attrs={"placeholder": "Andijon viloyati"}),
            "district": forms.TextInput(attrs={"placeholder": "Buloqboshi tumani"}),
            "photo": forms.FileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dormitory"].queryset = Building.objects.filter(kind=Building.Kind.DORM)
        self.fields["dormitory"].empty_label = "— TTJda yashamaydi —"
        self.fields["course"].widget = forms.Select(choices=[("", "— Kurs —")] + [(i, f"{i}-kurs") for i in range(1, 8)])

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if isinstance(photo, UploadedFile):
            validate_image(photo, required=False)
        return photo

    def clean_pinfl(self):
        value = (self.cleaned_data.get("pinfl") or "").strip()
        if value and not value.isdigit():
            raise forms.ValidationError("JSHSHIR faqat raqamlardan iborat bo'ladi.")
        return value

    def clean_passport(self):
        return (self.cleaned_data.get("passport") or "").replace(" ", "").upper()


class MemberForm(forms.ModelForm):
    """Qalqon a'zosi / sardor / admin hisobini yaratish va tahrirlash (shaxsiy ma'lumotlar bilan)."""

    password = forms.CharField(
        label="Parol", required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Tahrirlashda bo'sh qoldirilsa, parol o'zgarmaydi.",
    )

    class Meta:
        model = User
        fields = ["last_name", "first_name", "middle_name", "role", "faculty", "phone", "username", "is_active"]
        labels = {"last_name": "Familiya", "first_name": "Ism", "username": "Login",
                  "is_active": "Faol (tizimga kira oladi)", "role": "Roli"}
        widgets = {"phone": forms.TextInput(attrs={"placeholder": "+998 90 123 45 67"})}

    def __init__(self, data=None, files=None, *args, actor=None, **kwargs):
        super().__init__(data, files, *args, **kwargs)
        profile = getattr(self.instance, "qalqon_profile", None) if self.instance.pk else None
        self.profile_form = MemberProfileForm(data, files, instance=profile)
        for name in ("first_name", "last_name", "faculty"):
            self.fields[name].required = True
        self.fields["faculty"].empty_label = "— Fakultetni tanlang —"
        roles = [(User.Role.QALQON_MEMBER, User.Role.QALQON_MEMBER.label)]
        if actor is not None and actor.is_qalqon_admin:
            roles += [
                (User.Role.QALQON_LEADER, User.Role.QALQON_LEADER.label),
                (User.Role.QALQON_ADMIN, User.Role.QALQON_ADMIN.label),
            ]
        self.fields["role"].choices = roles
        if len(roles) == 1:
            self.fields["role"].widget = forms.HiddenInput()
            self.fields["role"].initial = User.Role.QALQON_MEMBER
        if not self.instance.pk:
            self.fields["password"].required = True
            self.fields["password"].help_text = "Kamida 6 ta belgi."
            self.fields["role"].initial = self.fields["role"].initial or User.Role.QALQON_MEMBER

    def is_valid(self):
        main = super().is_valid()
        return self.profile_form.is_valid() and main

    def clean_role(self):
        role = self.cleaned_data["role"]
        if role not in dict(self.fields["role"].choices):
            raise forms.ValidationError("Bu rolni berishga ruxsatingiz yo'q.")
        return role

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password, self.instance)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
        user.save()
        profile = self.profile_form.save(commit=False)
        profile.user = user
        if profile.pinfl and not profile.birth_date:
            from .docx_import import pinfl_info

            profile.birth_date, gender = pinfl_info(profile.pinfl)
            profile.gender = profile.gender or gender
        profile.save()
        return user


class DutyForm(forms.ModelForm):
    date_to = forms.DateField(
        label="Oxirgi sana (ixtiyoriy)", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Ko'rsatilsa, boshlang'ich sanadan shu sanagacha har kunga alohida naryad qo'yiladi.",
    )
    members = forms.ModelMultipleChoiceField(
        label="Navbatchi a'zolar", queryset=User.objects.none(), widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Kamida bitta a'zoni tanlang."},
    )

    class Meta:
        model = Duty
        fields = ["date", "start_time", "end_time", "building", "latitude", "longitude", "radius_m", "note"]
        labels = {"date": "Naryad sanasi"}
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "start_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "end_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "latitude": forms.NumberInput(attrs={"step": "0.000001"}),
            "longitude": forms.NumberInput(attrs={"step": "0.000001"}),
            "note": forms.Textarea(attrs={"rows": 3, "placeholder": "Navbatchilar uchun ko'rsatma (ixtiyoriy)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["building"].queryset = Building.objects.filter(is_active=True)
        self.fields["building"].empty_label = "— Binoni tanlang —"
        self.fields["members"].queryset = (
            User.objects.filter(role__in=[User.Role.QALQON_MEMBER, User.Role.QALQON_LEADER], is_active=True)
            .select_related("faculty", "qalqon_profile")
            .order_by("faculty__name", "last_name", "first_name")
        )
        if not self.instance.pk and not self.is_bound:
            self.initial.setdefault("date", timezone.localdate().isoformat())
        if self.instance.pk:
            del self.fields["date_to"]
            self.fields["members"].initial = list(self.instance.duty_members.values_list("member_id", flat=True))

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end and start == end:
            self.add_error("end_time", "Tugash vaqti boshlanish vaqtidan farq qilishi kerak.")
        date_from, date_to = cleaned.get("date"), cleaned.get("date_to")
        if date_from and date_to:
            if date_to < date_from:
                self.add_error("date_to", "Oxirgi sana boshlang'ich sanadan oldin bo'lishi mumkin emas.")
            elif (date_to - date_from).days > 62:
                self.add_error("date_to", "Bir martada ko'pi bilan 2 oylik naryad qo'yish mumkin.")
        return cleaned

    def dates(self):
        first = self.cleaned_data["date"]
        last = self.cleaned_data.get("date_to") or first
        return [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]


class LocationForm(forms.Form):
    latitude = forms.FloatField(min_value=-90, max_value=90, widget=forms.HiddenInput,
                                error_messages={"required": "Joylashuv aniqlanmadi. GPS'ni yoqing va qayta urining."})
    longitude = forms.FloatField(min_value=-180, max_value=180, widget=forms.HiddenInput,
                                 error_messages={"required": "Joylashuv aniqlanmadi."})
    accuracy = forms.FloatField(required=False, min_value=0, widget=forms.HiddenInput)


class FinishForm(LocationForm):
    photo = forms.FileField(label="Sherigingiz bilan tushgan rasm",
                            error_messages={"required": "Naryad yakunidagi rasmni yuklang."})
    confirm = forms.BooleanField(
        label="Naryad davomida qayd etilgan qonunbuzarliklar to'g'riligini tasdiqlayman",
        error_messages={"required": "Qonunbuzarliklar ro'yxatini tasdiqlang."},
    )
    finish_note = forms.CharField(label="Yakuniy izoh (ixtiyoriy)", required=False,
                                  widget=forms.Textarea(attrs={"rows": 2}))

    def clean_photo(self):
        return validate_image(self.cleaned_data.get("photo"))


class ViolationForm(forms.ModelForm):
    class Meta:
        model = Violation
        fields = ["occurred_at", "category", "student_name", "faculty", "direction", "group_name", "course",
                  "dormitory", "room", "tutor", "tutor_name", "description", "photo"]
        widgets = {
            "occurred_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "student_name": forms.TextInput(attrs={"placeholder": "Familiya Ism Otasining ismi"}),
            "group_name": forms.TextInput(attrs={"placeholder": "Masalan: 21-03"}),
            "room": forms.TextInput(attrs={"placeholder": "Masalan: 312"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Nima sodir bo'ldi, qanday chora ko'rildi…"}),
        }

    def __init__(self, *args, duty=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.duty = duty
        self.fields["occurred_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["faculty"].queryset = Faculty.objects.all()
        self.fields["faculty"].empty_label = "— Fakultet —"
        self.fields["dormitory"].queryset = Building.objects.filter(kind=Building.Kind.DORM)
        self.fields["dormitory"].empty_label = "— TTJ —"
        self.fields["tutor"].queryset = (
            User.objects.filter(role=User.Role.TUTOR, is_active=True).select_related("faculty")
            .order_by("faculty__name", "last_name")
        )
        self.fields["tutor"].empty_label = "— Tyutorni tanlang —"
        self.fields["tutor"].label_from_instance = lambda u: f"{u.full_name} ({u.faculty.label if u.faculty else '—'})"
        self.fields["category"].choices = [("", "— Turini tanlang —")] + list(Violation.Category.choices)
        self.fields["course"].widget = forms.Select(choices=[("", "— Kurs —")] + [(i, f"{i}-kurs") for i in range(1, 8)])
        if not self.instance.pk:
            self.initial.setdefault("occurred_at", timezone.localtime().strftime("%Y-%m-%dT%H:%M"))
            if duty and duty.building.kind == Building.Kind.DORM:
                self.initial.setdefault("dormitory", duty.building.pk)

    def clean_photo(self):
        return validate_image(self.cleaned_data.get("photo"), required=False)

    def clean_occurred_at(self):
        value = self.cleaned_data["occurred_at"]
        if self.duty:
            lo = self.duty.start_window_opens
            hi = self.duty.finish_window_closes
            if not (lo <= value <= hi):
                raise forms.ValidationError("Vaqt naryad davriga to'g'ri kelishi kerak.")
        if value > timezone.now() + dt.timedelta(minutes=5):
            raise forms.ValidationError("Kelajakdagi vaqtni kiritib bo'lmaydi.")
        return value

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("tutor") and not (cleaned.get("tutor_name") or "").strip():
            self.add_error("tutor", "Tyutorni tanlang yoki ismini yozing.")
        return cleaned


class ImportForm(forms.Form):
    file = forms.FileField(label="Ro'yxat fayli (.xlsx yoki .docx)")

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith((".xlsx", ".docx")):
            raise forms.ValidationError("Faqat Excel (.xlsx) yoki Word (.docx) fayl qabul qilinadi.")
        return f
