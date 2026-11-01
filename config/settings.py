"""
Ijro nazorati tizimi — Django sozlamalari.

Muhit o'zgaruvchilari:
    DJANGO_SECRET_KEY   — maxfiy kalit (production'da albatta o'rnating)
    DJANGO_DEBUG        — "1" bo'lsa debug rejimi (default: 1)
    DJANGO_ALLOWED_HOSTS — vergul bilan ajratilgan hostlar ro'yxati
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-me-7x!q2k9p#l0m3n8b5v",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "qalqon",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.sidebar",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_USER_MODEL = "core.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 6}},
]

LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Yuklangan fayllar. Ular to'g'ridan-to'g'ri URL orqali emas, faqat ruxsat
# tekshiruvidan o'tgan view orqali beriladi.
MEDIA_ROOT = BASE_DIR / "media"
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # bitta fayl uchun

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MESSAGE_TAGS = {
    40: "danger",
}

# ---------------------------------------------------------------- Qalqon
# Naryadni boshlash tugmasi boshlanish vaqtidan necha daqiqa oldin faollashadi
QALQON_START_EARLY_MINUTES = int(os.environ.get("QALQON_START_EARLY_MINUTES", 60))
# Tugash vaqtidan keyin necha soat ichida naryadni yakunlash mumkin
QALQON_FINISH_GRACE_HOURS = int(os.environ.get("QALQON_FINISH_GRACE_HOURS", 6))
# GPS aniqligi shundan yomon (metr) bo'lsa, joylashuv qabul qilinmaydi
QALQON_MAX_GPS_ACCURACY = int(os.environ.get("QALQON_MAX_GPS_ACCURACY", 150))
QALQON_MAX_PHOTO_SIZE = 15 * 1024 * 1024
