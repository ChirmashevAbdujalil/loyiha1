from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from qalqon import bundle


class Command(BaseCommand):
    help = ("export_qalqon_bundle yaratgan .zip arxivdan Qalqon a'zolarini (rasm va shaxsiy ma'lumotlari bilan), "
            "fakultetlar va binolarni yuklaydi. Loginlar va parollar arxiv yaratilgan serverdagi bilan bir xil "
            "bo'ladi. Qayta yuklansa, mavjud a'zolar yangilanadi.")

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--clear-demo", action="store_true", help="Avval demo ma'lumotlarni o'chirish")

    def handle(self, file, clear_demo, **options):
        if not Path(file).exists():
            raise CommandError(f"Fayl topilmadi: {file}")
        if clear_demo:
            call_command("clear_demo_data", yes=True, stdout=self.stdout)
        try:
            result = bundle.import_bundle(file)
        except (ValueError, KeyError) as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(
            f"Qo'shildi: {result['created']}, yangilandi: {result['updated']} a'zo; "
            f"yangi fakultetlar: {result['faculties']}, yangi binolar: {result['buildings']}."
        ))
