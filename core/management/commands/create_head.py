import getpass

from django.core.management.base import BaseCommand, CommandError

from core.models import User


class Command(BaseCommand):
    help = "Bo'lim boshlig'i (ma'naviyat bo'limi boshlig'i) hisobini yaratadi."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")
        parser.add_argument("--password", help="Ko'rsatilmasa, so'raladi.")

    def handle(self, username, first_name, last_name, password, **options):
        if User.objects.filter(username=username).exists():
            raise CommandError(f"«{username}» logini band.")
        if not password:
            password = getpass.getpass("Parol: ")
            if password != getpass.getpass("Parolni takrorlang: "):
                raise CommandError("Parollar mos kelmadi.")
        User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=User.Role.HEAD,
            is_staff=True,
        )
        self.stdout.write(self.style.SUCCESS(f"Bo'lim boshlig'i yaratildi: {username}"))
