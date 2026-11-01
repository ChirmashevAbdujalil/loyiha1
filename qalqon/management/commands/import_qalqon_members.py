from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from qalqon import services


class Command(BaseCommand):
    help = (
        "Qalqon a'zolarini Excel (.xlsx) fayldan bazaga qo'shadi va loginlar/parollar faylini yaratadi. "
        "Ustunlar: Familiya, Ism, Otasining ismi (yoki F.I.Sh), Fakultet, Yo'nalish, Guruh, Kurs, Telefon, TTJ, Xona."
    )

    def add_arguments(self, parser):
        parser.add_argument("file", help="A'zolar ro'yxati (.xlsx)")
        parser.add_argument("--out", help="Loginlar fayli (default: <fayl>_loginlar.xlsx)")
        parser.add_argument("--no-create-faculties", action="store_true",
                            help="Bazada yo'q fakultetlarni yaratmaslik (bunday qatorlar xato hisoblanadi)")

    def handle(self, file, out, no_create_faculties, **options):
        path = Path(file)
        if not path.exists():
            raise CommandError(f"Fayl topilmadi: {path}")
        try:
            rows = services.read_rows(path)
        except ValueError as exc:
            raise CommandError(str(exc))
        result = services.import_members(rows, create_faculties=not no_create_faculties)
        for s in result["skipped"]:
            self.stdout.write(self.style.WARNING(f"  o'tkazildi: {s}"))
        for e in result["errors"]:
            self.stdout.write(self.style.ERROR(f"  xato: {e}"))
        if result["new_faculties"]:
            self.stdout.write(f"Yangi fakultetlar: {', '.join(result['new_faculties'])}")
        if result["created"]:
            out_path = Path(out) if out else path.with_name(path.stem + "_loginlar.xlsx")
            services.credentials_workbook(result["created"]).save(out_path)
            self.stdout.write(self.style.SUCCESS(
                f"{len(result['created'])} ta a'zo qo'shildi. Loginlar va parollar: {out_path}"
            ))
        else:
            self.stdout.write("Yangi a'zo qo'shilmadi.")
