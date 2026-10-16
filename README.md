# Ijro intizomi — Ma'naviyat bo'limi uchun tyutorlar ijro nazorati tizimi

Ma'naviyat va ma'rifat bo'limi boshlig'i tyutorlarga ijro topshiriqlarini yuboradi, tyutorlar
ijroni yopadi (izoh + havola + fayl), bo'lim boshlig'i ko'rib chiqib tasdiqlaydi yoki qaytaradi.
Barcha jarayon kalendarda ko'rinadi va istalgan sana-soat holatiga rangli hisobot shakllanadi.

## Imkoniyatlar

**Bo'lim boshlig'i**
- **Fakultetlar** ma'lumotnomasi — avval fakultetlar qo'shiladi.
- **Tyutorlar** — fakultetga biriktirib qo'shiladi (F.I.Sh, lavozim, telefon, login/parol).
  Fakultet bo'yicha filtr, qidiruv, har bir tyutorning ijro statistikasi.
- **Yangi topshiriq** — mavzu, mazmun, **ijro kuni**, **ijro muddati** (sana + soat),
  bir nechta **fayl** (drag & drop) va **bir nechta tyutorni** tanlash (fakultet bo'yicha
  guruhlangan, "fakultetni to'liq tanlash", qidiruv). Yuborilganda har bir tyutorga
  **bildirishnoma** boradi.
- **Bosh sahifa — oy kesimidagi kalendar.** Har bir kunda o'sha kunga topshirig'i bor
  **tyutorlarning familiya-ismi** chiqadi (holat rangida: muddati o'tgan / tasdiqlashda /
  bajarilmoqda / qaytarilgan / bajarildi). **Ismni bosganda** o'ng panelda shu tyutorga
  o'sha kunda biriktirilgan topshiriqlar ko'rinadi. Kalendarni "Ijro kuni" yoki "Muddat"
  bo'yicha, fakultet bo'yicha ko'rish mumkin.
- **Tasdiqlash uchun** — tyutorlar yopgan ijrolar navbati: izoh, havola, fayllar;
  "Tasdiqlash" yoki izoh bilan "Qaytarish".
- **Hisobotlar** — davr, fakultet, tyutor va **holat sanasi-soati** bo'yicha.
  Tyutor × topshiriq jadvali: **yashil — bajardi**, **qizil — bajarmadi**, sariq — tasdiqlashda,
  kulrang — muddati hali kelmagan; kechikib bajarilganlar belgilanadi. Fakultetlar kesimida
  xulosa. **Excel (.xlsx)** yuklab olish (ranglari bilan) va chop etish / PDF.
  Holat vaqti o'tmishga qo'yilsa, hisobot aynan o'sha paytdagi ko'rinishda tiklanadi
  (ijro tarixi saqlanadi).

**Tyutor**
- O'z kalendari va "Mening topshiriqlarim" ro'yxati (bajarilishi kerak / muddati o'tgan /
  tasdiqlashda / bajarilgan).
- Topshiriq sahifasida fayllarni yuklab olish va **"Ijroni yopish"** tugmasi: izoh, havola
  (link) va ixtiyoriy fayllar bilan yuboriladi → bo'lim boshlig'i profiliga tushadi.
- Qaytarilsa — sababini ko'radi va qayta yuboradi.

**Bildirishnomalar** — yangi topshiriq, o'zgartirish, ijro yuborildi, tasdiqlandi/qaytarildi,
muddat eslatmasi. Sarlavhadagi qo'ng'iroqcha har 30 soniyada yangilanadi, yangi
bildirishnoma kelganda ekranda xabar (toast) va brauzer bildirishnomasi chiqadi.

## O'rnatish va ishga tushirish

Python 3.10+ kerak.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py create_head boshliq --first-name Doniyor --last-name Sarimsoqov
python manage.py runserver
```

So'ng brauzerda <http://127.0.0.1:8000> manzilini oching va bo'lim boshlig'i login-paroli
bilan kiring. Tartib: **Fakultetlar → Tyutorlar → Yangi topshiriq**.

### Demo ma'lumotlar bilan tanishish

```bash
python manage.py seed_demo
```

Kirish: `boshliq / demo1234` (bo'lim boshlig'i), `tyutor1 … tyutor12 / demo1234` (tyutorlar).

### Muddat eslatmalari (ixtiyoriy)

Muddatiga 24 soatdan kam qolgan va hali yopilmagan ijrolar bo'yicha tyutorlarga eslatma:

```bash
python manage.py send_reminders            # cron orqali soatiga bir marta
```

### Testlar

```bash
python manage.py test core
```

## Serverga joylash (qisqacha)

Muhit o'zgaruvchilari:

| O'zgaruvchi | Ma'nosi |
|---|---|
| `DJANGO_SECRET_KEY` | maxfiy kalit (albatta o'rnating) |
| `DJANGO_DEBUG` | `0` — production |
| `DJANGO_ALLOWED_HOSTS` | masalan `ijro.example.uz` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | masalan `https://ijro.example.uz` |

```bash
python manage.py collectstatic
gunicorn config.wsgi:application   # yoki uWSGI; statik fayllarni nginx orqali bering
```

Yuklangan fayllar `media/` papkasida saqlanadi va faqat ruxsati bor foydalanuvchilarga
(bo'lim boshlig'i yoki topshiriq biriktirilgan tyutor) tizim orqali beriladi — `media/`ni
nginx orqali ochiq qilmang. Ma'lumotlar bazasi standart holatda SQLite; ko'p foydalanuvchi
uchun PostgreSQL'ga o'tkazish `config/settings.py` dagi `DATABASES` orqali qilinadi.

## Tuzilma

```
config/             Django sozlamalari va URL'lar
core/models.py      Faculty, User (rol: bo'lim boshlig'i / tyutor), Task, TaskFile,
                    Assignment (ijro), Submission (ijroni yopish tarixi), Notification
core/views/         dashboard (kalendar), people (fakultet/tyutor), tasks, reports, notifications
core/services.py    bildirishnomalar va vaqt holatiga ko'ra hisobot hisob-kitobi
core/management/    create_head, seed_demo, send_reminders buyruqlari
templates/, static/ interfeys (HTML, CSS, JS)
```
