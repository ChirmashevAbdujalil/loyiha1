from django import forms
from django.conf import settings
from django.contrib.auth.password_validation import validate_password

from .models import Faculty, Task, User
from .utils import human_size


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"multiple": True}))
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        files = [super(MultipleFileField, self).clean(f, initial) for f in data if f]
        for f in files:
            if f.size > settings.MAX_UPLOAD_SIZE:
                raise forms.ValidationError(
                    f"«{f.name}» hajmi juda katta ({human_size(f.size)}). "
                    f"Ruxsat etilgan: {human_size(settings.MAX_UPLOAD_SIZE)}."
                )
        return files


class FacultyForm(forms.ModelForm):
    class Meta:
        model = Faculty
        fields = ["name", "short_name"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Masalan: Iqtisodiyot fakulteti"}),
            "short_name": forms.TextInput(attrs={"placeholder": "Masalan: IQT"}),
        }


class TutorForm(forms.ModelForm):
    password = forms.CharField(
        label="Parol",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="Tahrirlashda bo'sh qoldirilsa, parol o'zgarmaydi.",
    )

    class Meta:
        model = User
        fields = [
            "last_name", "first_name", "middle_name", "faculty", "position",
            "phone", "email", "username", "is_active",
        ]
        labels = {
            "last_name": "Familiya",
            "first_name": "Ism",
            "username": "Login",
            "email": "Elektron pochta",
            "is_active": "Faol (tizimga kira oladi)",
        }
        widgets = {
            "phone": forms.TextInput(attrs={"placeholder": "+998 90 123 45 67"}),
            "position": forms.TextInput(attrs={"placeholder": "Masalan: 2-kurs tyutori"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["faculty"].required = True
        self.fields["faculty"].empty_label = "— Fakultetni tanlang —"
        self.fields["username"].help_text = "Lotin harflari, raqamlar va @/./+/-/_ belgilari."
        if not self.instance.pk:
            self.fields["password"].required = True
            self.fields["password"].help_text = "Kamida 6 ta belgi."

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password, self.instance)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.TUTOR
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class TaskForm(forms.ModelForm):
    tutors = forms.ModelMultipleChoiceField(
        label="Ijrochi tyutorlar",
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Kamida bitta tyutorni tanlang."},
    )
    files = MultipleFileField(label="Fayllar")

    class Meta:
        model = Task
        fields = ["title", "description", "execution_date", "deadline"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Topshiriq mavzusini kiriting"}),
            "description": forms.Textarea(
                attrs={"rows": 6, "placeholder": "Topshiriq mazmuni, talablar va ko'rsatmalar…"}
            ),
            "execution_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tutors"].queryset = (
            User.objects.filter(role=User.Role.TUTOR, is_active=True)
            .select_related("faculty")
            .order_by("faculty__name", "last_name", "first_name")
        )
        self.fields["deadline"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]
        if self.instance.pk:
            self.fields["tutors"].initial = list(
                self.instance.assignments.values_list("tutor_id", flat=True)
            )

    def clean(self):
        cleaned = super().clean()
        ex, dl = cleaned.get("execution_date"), cleaned.get("deadline")
        if ex and dl:
            from django.utils import timezone

            if timezone.localtime(dl).date() < ex:
                self.add_error("deadline", "Ijro muddati ijro kunidan oldin bo'lishi mumkin emas.")
        return cleaned


class SubmitForm(forms.Form):
    comment = forms.CharField(
        label="Izoh",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Bajarilgan ish haqida qisqacha izoh…"}),
    )
    link = forms.URLField(
        label="Havola (link)",
        required=False,
        max_length=1000,
        widget=forms.URLInput(attrs={"placeholder": "https://…"}),
        assume_scheme="https",
    )
    files = MultipleFileField(label="Fayllar (ixtiyoriy)")


class ReviewForm(forms.Form):
    action = forms.ChoiceField(choices=[("approve", "Tasdiqlash"), ("reject", "Qaytarish")])
    comment = forms.CharField(
        label="Izoh",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Izoh (qaytarishda majburiy)"}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("action") == "reject" and not cleaned.get("comment", "").strip():
            self.add_error("comment", "Qaytarish sababini yozing.")
        return cleaned
