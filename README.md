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

## Qalqon jamoatchilik guruhi moduli (`/qalqon/`)

Ijro tizimi va Qalqon — **ikki alohida platforma**: har birining o'z menyusi, logotipi,
kirish sahifasi (`/login/` va `/qalqon/kirish/`) va bildirishnomalari bor. Ikkalasiga ham
huquqi bor foydalanuvchida (bo'lim boshlig'i) menyuning yuqorisida "Ijro | Qalqon"
almashtirgichi chiqadi. Qalqon a'zolari ijro tizimini, tyutorlar Qalqonni ko'rmaydi.
**GPS tekshiruvi** sahifasida (`/qalqon/gps-tekshiruv/`) a'zo telefoni joylashuvni to'g'ri
aniqlayotganini va binolargacha masofani oldindan sinab ko'rishi mumkin.

Uchta rol: **umumiy admin** (bo'lim boshlig'i ham admin huquqiga ega), **sardor** va **a'zo**.

- **A'zolar** fakultetlar kesimida (filtr: fakultet, kurs, rol, qidiruv), ma'lumotlari bilan:
  yo'nalish, guruh, kurs, telefon, TTJ va xona. Qo'lda qo'shish yoki **Excel'dan import**
  (login va parollar avtomatik yaratiladi va Excel ko'rinishida yuklab olinadi).
- **Binolar / TTJlar** — koordinata (xaritadan bosib, qo'lda yoki "hozirgi joylashuvim")
  va ruxsat etilgan radius (metr).
- **Naryad qo'yish** (sardor/admin): sana (yoki sanalar oralig'i — har kunga alohida naryad),
  boshlanish/tugash vaqti, bino, koordinata, radius, ko'rsatma va navbatchi a'zolar
  (fakultet, kurs bo'yicha filtr; o'sha kuni boshqa naryadda bo'lganlar "band" deb belgilanadi).
  A'zolarga bildirishnoma boradi.
- **Kalendar** — oy kesimida hammaga ko'rinadi: har kunda bino, vaqt va navbatchilar,
  holat rangida (rejada / bugun / naryadda / yakunlangan / chiqmagan).
- **Naryadni boshlash** — tugma faqat navbat kuni chiqadi (boshlanishdan 60 daqiqa oldin
  faollashadi). Bosilganda telefon GPS'i orqali a'zoning joylashuvi olinadi va server
  naryad koordinatasi bilan solishtiradi: faqat radius ichida bo'lsa naryad boshlanadi.
- **Qonunbuzarliklar** — naryad davomida: turi, vaqti, talabaning F.I.Sh, fakulteti, yo'nalishi,
  guruhi, kursi, TTJ va xona raqami, tyutori, maxsus izoh, ixtiyoriy rasm. Sardorga bildirishnoma.
- **Naryadni yakunlash** — tugma faqat tugash vaqtidan (masalan 22:00) keyin chiqadi.
  A'zo qonunbuzarliklarni qayta tasdiqlaydi, sherigi bilan tushgan rasmni yuklaydi va
  yana joylashuv tekshiriladi — faqat hudud ichida bo'lsa yakunlanadi.
- **Statistika** (sardor va admin, avtomatik): naryad intizomi, qaysi bino/TTJda qonunbuzarlik
  ko'p, **TTJlar intizom reytingi**, turlar, fakultetlar, kurslar, soatlar va kunlar dinamikasi,
  kimning naryadida qanday qonunbuzarliklar, takroriy qonunbuzarlar, tyutorlar kesimi,
  a'zolarning intizomi. **Excel hisobot** (bir nechta varaq) va chop etish.
- Har bir joylashuv tekshiruvi (muvaffaqiyatli yoki rad etilgan) jurnalga yoziladi —
  sardor naryad sahifasida ko'radi.

> **Muhim:** brauzer GPS'ni faqat **HTTPS** orqali ochilgan saytga beradi. Serverga
> SSL sertifikat o'rnatilishi shart (masalan, Let's Encrypt). Xarita OpenStreetMap
> plitkalaridan foydalanadi (internet kerak); xarita yuklanmasa ham GPS tekshiruvi ishlaydi.

Sozlamalar (muhit o'zgaruvchilari): `QALQON_START_EARLY_MINUTES` (60),
`QALQON_FINISH_GRACE_HOURS` — tugash vaqtidan keyin yakunlash uchun soatlar (6),
`QALQON_MAX_GPS_ACCURACY` — qabul qilinadigan eng yomon GPS aniqligi, metr (150).

### A'zolar ro'yxatini bazaga qo'shish

**Word (.docx) ro'yxatdan** (institutning «Qalqon jamoatchilik guruhi a'zolari umumiy ro'yxati» jadvali —
F.I.Sh va telefon, «sardori» belgisi, rasm, fakultet/kurs/yo'nalish/guruh, pasport, JSHSHIR, manzil):

```bash
python manage.py import_qalqon_docx "Qalqon_jamoatchilik_guruhi.docx" --dry-run   # avval tekshirish
python manage.py import_qalqon_docx "Qalqon_jamoatchilik_guruhi.docx"
```

Rasmlar, pasport, JSHSHIR (undan tug'ilgan sana va jins aniqlanadi) va manzil (viloyat, tuman, ko'cha)
ham saqlanadi; fakultetlar avtomatik yaratiladi. Kurs ko'rsatilmagan bo'lsa, guruh raqamidagi yildan
hisoblanadi (`--year 2026`). Qayta ishga tushirilsa, dublikat yaratilmaydi — ma'lumotlar yangilanadi.
Hujjatdagi yetishmayotgan yoki shubhali ma'lumotlar (12 xonali JSHSHIR, noto'g'ri pasport raqami va h.k.)
ekranga chiqariladi. Xuddi shuni sayt orqali ham qilish mumkin: **Qalqon → A'zolar → Exceldan import**
(.docx ham qabul qilinadi). Pasport va JSHSHIR faqat sardor va admin uchun ko'rinadi.

**Excel (.xlsx) ro'yxatdan:**

```bash
python manage.py import_qalqon_members azolar.xlsx
```

Ustunlar: `Familiya`, `Ism`, `Otasining ismi` (yoki bitta `F.I.Sh`), `Fakultet`, `Yo'nalish`,
`Guruh`, `Kurs`, `Telefon`, `TTJ`, `Xona` (ixtiyoriy: `Login`, `Parol`, `Rol` — "sardor").
Natijada `azolar_loginlar.xlsx` fayli yaratiladi. Xuddi shuni sayt orqali ham qilish mumkin:
**Qalqon → A'zolar → Exceldan import**.

Sardor va admin hisoblari: admin panelda yoki Qalqon → A'zolar → "A'zo qo'shish"da
(umumiy admin rolni tanlay oladi). Demo: `python manage.py seed_qalqon`
(`qalqon_admin`, `sardor`, `qalqon1…qalqon16`, parol `demo1234`).

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
python manage.py test
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
qalqon/             Qalqon moduli: Building, MemberProfile, Duty, DutyMember, Violation, LocationLog;
                    import_qalqon_members va seed_qalqon buyruqlari
templates/, static/ interfeys (HTML, CSS, JS)
```
