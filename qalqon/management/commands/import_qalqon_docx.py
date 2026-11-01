from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from qalqon import docx_import, services


class Command(BaseCommand):
    help = (
        "Qalqon a'zolari ro'yxatini Word (.docx) jadvalidan bazaga qo'shadi: F.I.Sh, telefon, sardor belgisi, "
        "rasm, fakultet, kurs, yo'nalish, guruh, pasport, JSHSHIR, manzil. Qayta ishga tushirilsa, mavjud "
        "a'zolar yangilanadi (dublikat yaratilmaydi)."
    )

    def add_arguments(self, parser):
        parser.add_argument("file", help="Ro'yxat (.docx)")
        parser.add_argument("--dry-run", action="store_true", help="Faqat o'qib ko'rsatish, bazaga yozmaslik")
        parser.add_argument("--year", type=int, default=2026,
                            help="O'quv yili boshlanishi (guruh raqamidan kursni hisoblash uchun), default 2026")
        parser.add_argument("--reset-passwords", action="store_true",
                            help="Bazada bor a'zolarga ham yangi parol berish")
        parser.add_argument("--out", help="Loginlar fayli (default: <fayl>_loginlar.xlsx)")

    def handle(self, file, dry_run, year, reset_passwords, out, **options):
        path = Path(file)
        if not path.exists():
            raise CommandError(f"Fayl topilmadi: {path}")
        try:
            records = docx_import.parse_docx(path, academic_year_start=year)
        except ValueError as exc:
            raise CommandError(str(exc))

        self.stdout.write(f"Hujjatda {len(records)} ta a'zo topildi.\n")
        for r in records:
            leader = " [SARDOR]" if r.is_leader else ""
            course = f"{r.course}-kurs" + (" (guruhdan)" if r.course_derived else "") if r.course else "kurs —"
            self.stdout.write(f"{r.number:>3}. {r.full_name}{leader} · {r.faculty_short or r.faculty_name} · "
                              f"{r.group_name or 'guruh —'} · {course} · {r.phone or 'tel —'}")
            for w in r.warnings:
                self.stdout.write(self.style.WARNING(f"       ! {w}"))
        if dry_run:
            self.stdout.write("\n--dry-run: bazaga hech narsa yozilmadi.")
            return

        result = docx_import.save_records(records, reset_passwords=reset_passwords)
        if result["new_faculties"]:
            self.stdout.write(f"\nYangi fakultetlar: {', '.join(result['new_faculties'])}")
        self.stdout.write(self.style.SUCCESS(
            f"\nQo'shildi: {len(result['created'])}, yangilandi: {len(result['updated'])}."
        ))
        with_password = [x for x in result["created"] + result["updated"] if x["password"]]
        if with_password:
            out_path = Path(out) if out else path.with_name(path.stem + "_loginlar.xlsx")
            services.credentials_workbook(with_password).save(out_path)
            self.stdout.write(self.style.SUCCESS(f"Loginlar va parollar: {out_path}"))
