"""`migrate` dan keyin repodagi Qalqon a'zolari arxivini (data/qalqon_azolar.zip) avtomatik yuklash.

Har bir bazada arxivning har bir versiyasi faqat BIR MARTA yuklanadi: avval demo ma'lumotlar
o'chiriladi, keyin a'zolar (rasmlari, shaxsiy ma'lumotlari va parollari bilan) qo'shiladi.
Keyingi `migrate` larda qayta yuklanmaydi — a'zolar o'zgartirgan parollar saqlanib qoladi.
Arxiv fayli yangilansa (boshqa checksum), yangi versiya bir marta yuklanadi.
O'chirib qo'yish: QALQON_INITIAL_DATA="" muhit o'zgaruvchisi.
"""
import hashlib
import io
import sys
from pathlib import Path

from django.conf import settings
from django.core.management import call_command


def bundle_path():
    value = getattr(settings, "QALQON_INITIAL_DATA", None)
    return Path(value) if value else None


def load_initial_data(sender=None, verbosity=1, **kwargs):
    if sys.argv[1:2] == ["test"]:
        return
    path = bundle_path()
    if not path or not path.exists():
        return
    from .bundle import import_bundle
    from .models import DataImport

    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    if DataImport.objects.filter(name=path.name, checksum=checksum).exists():
        return
    call_command("clear_demo_data", yes=True, stdout=io.StringIO())
    result = import_bundle(path)
    DataImport.objects.create(name=path.name, checksum=checksum)
    if verbosity:
        print(f"Qalqon: demo ma'lumotlar o'chirildi; {path.name} yuklandi — "
              f"qo'shildi {result['created']}, yangilandi {result['updated']} a'zo.")
