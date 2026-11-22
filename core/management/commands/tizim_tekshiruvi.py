"""Server xatolari (500) ning eng ko'p uchraydigan sabablarini tekshiradi.

    python manage.py tizim_tekshiruvi
"""
import importlib
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = "Tizimni tekshiradi: migratsiyalar, kutubxonalar, shablonlar, fayllar va sozlamalar."
    # Kodda xato bo'lsa ham buyruq ishlashi kerak — Django'ning o'z tekshiruvlari (urls) bu yerda o'tkazilmaydi
    requires_system_checks = []

    def ok(self, text):
        self.stdout.write(self.style.SUCCESS("  ✓ ") + text)

    def bad(self, text, fix=""):
        self.errors += 1
        self.stdout.write(self.style.ERROR("  ✗ ") + text)
        if fix:
            self.stdout.write("      → " + fix)

    def warn(self, text, fix=""):
        self.stdout.write(self.style.WARNING("  ! ") + text)
        if fix:
            self.stdout.write("      → " + fix)

    def section(self, title):
        self.stdout.write("\n" + self.style.MIGRATE_HEADING(title))

    def handle(self, **options):
        self.errors = 0
        self.check_packages()
        self.check_migrations()
        self.check_tables()
        self.check_code()
        self.check_templates()
        self.check_face()
        self.check_files()
        self.check_settings()
        self.show_last_error()
        self.stdout.write("")
        if self.errors:
            self.stdout.write(self.style.ERROR(f"Topilgan xatolar: {self.errors}. Yuqoridagi «→» ko'rsatmalarini bajaring."))
        else:
            self.stdout.write(self.style.SUCCESS("Xato topilmadi. 500 davom etsa, logs/errors.log faylidagi oxirgi xatoni yuboring."))

    # ------------------------------------------------------------------
    def check_packages(self):
        self.section("1. Kutubxonalar")
        for module, pip_name in (("django", "Django"), ("openpyxl", "openpyxl"), ("docx", "python-docx"),
                                 ("PIL", "Pillow"), ("numpy", "numpy"), ("cv2", "opencv-python-headless")):
            try:
                mod = importlib.import_module(module)
                self.ok(f"{pip_name} {getattr(mod, '__version__', '')}")
            except Exception as exc:  # noqa: BLE001
                self.bad(f"{pip_name} o'rnatilmagan yoki buzilgan: {exc}", "pip install -r requirements.txt")

    def check_migrations(self):
        self.section("2. Ma'lumotlar bazasi migratsiyalari")
        try:
            from django.db.migrations.executor import MigrationExecutor

            executor = MigrationExecutor(connections["default"])
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        except Exception as exc:  # noqa: BLE001
            self.bad(f"Migratsiyalarni tekshirib bo'lmadi: {exc}", "python manage.py migrate")
            return
        if plan:
            names = ", ".join(f"{m.app_label}.{m.name}" for m, _ in plan)
            self.bad(f"Bajarilmagan migratsiyalar bor: {names}", "python manage.py migrate")
        else:
            self.ok("Barcha migratsiyalar bajarilgan")

    def check_tables(self):
        self.section("3. Jadvallar va ustunlar")
        failed = 0
        for model in list(apps.get_app_config("core").get_models()) + list(apps.get_app_config("qalqon").get_models()):
            try:
                model.objects.order_by().first()
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.bad(f"{model._meta.label}: {str(exc).splitlines()[0]}", "python manage.py migrate")
        if not failed:
            self.ok("Barcha jadvallar o'qilmoqda")

    def check_code(self):
        self.section("4. Python fayllari va manzillar (urls)")
        modules = ["core.views", "core.platform", "qalqon.models", "qalqon.views", "qalqon.manage_views",
                   "qalqon.services", "qalqon.forms", "qalqon.face", "qalqon.face_views", "qalqon.urls", "config.urls"]
        for name in modules:
            try:
                importlib.import_module(name)
            except ModuleNotFoundError as exc:
                if exc.name == name:
                    self.bad(f"{name.replace('.', '/')}.py fayli yo'q", "Faylni qo'llanma/arxiv bo'yicha joylang")
                else:
                    self.bad(f"{name}: {exc}")
            except Exception as exc:  # noqa: BLE001 — sintaksis/chekinish xatolari shu yerda chiqadi
                self.bad(f"{name}: {type(exc).__name__}: {exc}", "Ko'rsatilgan fayl va qatorni tekshiring")
        try:
            from django.urls import get_resolver, reverse

            get_resolver().url_patterns
            for name in ("dashboard", "qalqon:calendar", "qalqon:settings", "qalqon:face_challenge"):
                reverse(name, args=[1]) if name == "qalqon:face_challenge" else reverse(name)
            self.ok("Manzillar to'g'ri yuklanmoqda")
        except Exception as exc:  # noqa: BLE001
            self.bad(f"Manzillar (urls): {exc}", "qalqon/urls.py faylini tekshiring")

    def check_templates(self):
        self.section("5. Shablonlar (HTML)")
        from django.template import engines

        engine = engines["django"]
        failed = 0
        for directory in [Path(d) for d in settings.TEMPLATES[0]["DIRS"]]:
            for path in sorted(directory.rglob("*.html")):
                rel = path.relative_to(directory).as_posix()
                try:
                    engine.get_template(rel)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    self.bad(f"templates/{rel}: {exc}", "Shablondagi o'zgartirishni qo'llanma bilan solishtiring")
        if not failed:
            self.ok("Barcha shablonlar xatosiz")

    def check_face(self):
        self.section("6. Yuz tekshiruvi")
        try:
            from qalqon import face
            from qalqon.models import qalqon_conf
        except Exception as exc:  # noqa: BLE001
            self.bad(f"Yuz tekshiruvi moduli yuklanmadi: {exc}")
            return
        for path in (face.DETECTOR_MODEL, face.RECOGNIZER_MODEL):
            if not path.exists():
                self.bad(f"Model fayli yo'q: {path}", "qalqon/face_models/ papkasiga model fayllarini qo'ying")
            elif path.stat().st_size < 100_000:
                self.bad(f"Model fayli buzilgan (juda kichik): {path.name}", "Faylni qayta yuklab oling")
        if face.available():
            self.ok("Modellar yuklandi")
        try:
            enabled = qalqon_conf()["face_check_enabled"]
            self.ok(f"Sozlamalarda yuz tekshiruvi {'yoqilgan' if enabled else 'o' + chr(39) + 'chirilgan'}")
        except Exception as exc:  # noqa: BLE001
            self.bad(f"Sozlamalarni o'qib bo'lmadi: {exc}", "python manage.py migrate")

    def check_files(self):
        self.section("7. Fayllar va papkalar")
        for label, path in (("Yuklangan fayllar (MEDIA_ROOT)", Path(settings.MEDIA_ROOT)),
                            ("Xatolar jurnali (logs)", Path(getattr(settings, "LOG_DIR", settings.BASE_DIR / "logs")))):
            try:
                path.mkdir(parents=True, exist_ok=True)
                probe = path / ".yozish_tekshiruvi"
                probe.write_text("ok")
                probe.unlink()
                self.ok(f"{label}: {path} — yozish mumkin")
            except Exception as exc:  # noqa: BLE001
                self.bad(f"{label}: {path} — yozib bo'lmaydi ({exc})",
                         "Papkaga server foydalanuvchisiga yozish huquqini bering (masalan: chown -R www-data)")
        if not settings.DEBUG:
            root = Path(settings.STATIC_ROOT)
            for rel in ("css/app.css", "js/app.js", "js/qalqon.js"):
                target, source = root / rel, Path(settings.BASE_DIR) / "static" / rel
                if not target.exists():
                    self.bad(f"static: {rel} STATIC_ROOT da yo'q", "python manage.py collectstatic --noinput")
                elif source.exists() and source.stat().st_mtime > target.stat().st_mtime + 1:
                    self.warn(f"static: {rel} eskirgan (yangi versiya yig'ilmagan)", "python manage.py collectstatic --noinput")

    def check_settings(self):
        self.section("8. Sozlamalar")
        self.ok(f"DEBUG = {settings.DEBUG}")
        if not settings.DEBUG:
            if "django-insecure" in settings.SECRET_KEY:
                self.warn("SECRET_KEY standart (xavfsiz emas)", "DJANGO_SECRET_KEY muhit o'zgaruvchisini o'rnating")
            if not settings.CSRF_TRUSTED_ORIGINS:
                self.warn("DJANGO_CSRF_TRUSTED_ORIGINS bo'sh — https saytda formalar 403 berishi mumkin",
                          "masalan: DJANGO_CSRF_TRUSTED_ORIGINS=https://sizning-sayt.uz")
        self.ok(f"ALLOWED_HOSTS = {settings.ALLOWED_HOSTS}")

    def show_last_error(self):
        path = Path(getattr(settings, "LOG_DIR", settings.BASE_DIR / "logs")) / "errors.log"
        if not path.exists() or path.stat().st_size == 0:
            return
        self.section("9. Oxirgi qayd etilgan server xatosi (logs/errors.log)")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        starts = [i for i, line in enumerate(lines) if " ERROR " in line]
        block = lines[starts[-1]:] if starts else lines[-25:]
        if len(block) > 12:
            block = block[:6] + ["..."] + block[-6:]
        for line in block:
            self.stdout.write("    " + line)
