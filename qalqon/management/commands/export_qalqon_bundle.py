from django.core.management.base import BaseCommand

from qalqon import bundle


class Command(BaseCommand):
    help = ("Qalqon a'zolari (rasm, shaxsiy ma'lumot, parol xeshi), fakultetlar va binolarni boshqa serverga "
            "ko'chirish uchun .zip arxivga yozadi. Arxivni Git'ga qo'shmang — unda shaxsiy ma'lumotlar bor.")

    def add_arguments(self, parser):
        parser.add_argument("out", help="Arxiv fayli, masalan qalqon_azolar.zip")

    def handle(self, out, **options):
        n = bundle.export_bundle(out)
        self.stdout.write(self.style.SUCCESS(f"{n} ta a'zo arxivga yozildi: {out}"))
