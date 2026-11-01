"""Qalqon a'zolari ro'yxatini Word (.docx) jadvalidan o'qish va bazaga yozish.

Kutiladigan jadval (institut ro'yxati shakli):
    T/R | F.I.SH (+ "sardori" belgisi, telefon) | Rasmi | Fakulteti, kurs, yo'nalish, guruh |
    Yashash joyi va pasport ma'lumotlari (pasport, JSHSHIR, manzil)

Ustunlar sarlavha bo'yicha topiladi, shuning uchun tartibi farq qilsa ham ishlaydi.
"""
import datetime as dt
import io
import re
import secrets
from dataclasses import dataclass, field

from django.core.files.base import ContentFile
from django.db import transaction

from core.models import Faculty, User

from .models import MemberProfile
from .services import _norm, make_username

QALQON_ROLES = [User.Role.QALQON_MEMBER, User.Role.QALQON_LEADER, User.Role.QALQON_ADMIN]

# Andijon davlat texnika instituti fakultetlari: rasmiy nom, qisqa nom va hujjatda uchraydigan yozilishlar
FACULTIES = [
    ("Mexanika va kimyo muhandisligi fakulteti", "MKMF", (r"me[xh]anik",)),
    ("Iqtisodiyot va boshqaruv fakulteti", "IBF", (r"iq[td]isodiyot\s+va\s+bosh[qk]aruv",)),
    ("Avtomobilsozlik va transport fakulteti", "ATF", (r"avtomobilsozlik",)),
    ("Qurilish muhandisligi va elektroenergetika fakulteti", "QMEF", (r"qurilish",)),
    ("Intellektual boshqaruv va kompyuter tizimlari fakulteti", "IBKTF",
     (r"intellektual\s+bosh[qk]aruv", r"\bib\s+va\s+kt\b")),
]

# Yo'nalish nomlaridagi imlo xatolarini tuzatish (faqat aniq xatolar)
DIRECTION_FIXES = [
    (r"\btexnalogiya", "texnologiya"), (r"\btexologiya", "texnologiya"),
    (r"\bmehanika", "mexanika"), (r"\belektir\b", "elektr"), (r"\bmextronika", "mexatronika"),
    (r"robototexmika", "robototexnika"), (r"\bsuniy\b", "sun'iy"), (r"\boziq\s+ovqat", "oziq-ovqat"),
    (r"\bqayta\s+ish\s+texnologiya", "qayta ishlash texnologiya"), (r"\byo;l\b", "yoʻl"),
    (r"\bmuhandislik\b(?=\s*$)", "muhandisligi"), (r"\biqdisodiyot", "iqtisodiyot"),
]

APOS = "ʻ"  # o'zbek lotin alifbosidagi oʻ, gʻ belgisi


@dataclass
class MemberRecord:
    row: int
    number: str = ""
    last_name: str = ""
    first_name: str = ""
    middle_name: str = ""
    phone: str = ""
    is_leader: bool = False
    faculty_name: str = ""
    faculty_short: str = ""
    direction: str = ""
    group_name: str = ""
    course: int | None = None
    course_derived: bool = False
    passport: str = ""
    passport_issued: dt.date | None = None
    pinfl: str = ""
    birth_date: dt.date | None = None
    gender: str = ""
    region: str = ""
    district: str = ""
    address: str = ""
    photo: bytes | None = None
    photo_ext: str = ".jpg"
    warnings: list = field(default_factory=list)

    @property
    def full_name(self):
        return " ".join(p for p in (self.last_name, self.first_name, self.middle_name) if p)


# ---------------------------------------------------------------- yordamchilar

def _clean(text):
    text = (text or "").replace("|", " ").replace(" ", " ")
    text = re.sub(r"[’‘`ʼ']", APOS, text)
    return re.sub(r"\s+", " ", text).strip(" ,.;")


def _cap(word):
    return word[:1].upper() + word[1:].lower() if word else word


def _cell_text(cell):
    return "\n".join(p.text for p in cell.paragraphs)


def _cell_images(cell, doc):
    from docx.oxml.ns import qn

    images = []
    for blip in cell._tc.findall(".//" + qn("a:blip")):
        rid = blip.get(qn("r:embed"))
        part = doc.part.related_parts.get(rid)
        if part is not None:
            images.append((part.blob, "." + part.partname.rsplit(".", 1)[-1].lower()))
    return images


def _find_columns(header_cells):
    cols = {}
    for i, text in enumerate(header_cells):
        t = _norm(text)
        if "f.i.sh" in t or "f.i.o" in t or "fish" in t:
            cols.setdefault("name", i)
        elif "rasm" in t or "surat" in t:
            cols.setdefault("photo", i)
        elif "fakultet" in t:
            cols.setdefault("study", i)
        elif "pasport" in t or "yashash" in t:
            cols.setdefault("personal", i)
    missing = {"name", "study", "personal"} - set(cols)
    if missing:
        raise ValueError("Jadvalda kerakli ustunlar topilmadi: F.I.SH, Fakulteti, Yashash joyi va pasport.")
    return cols


# ---------------------------------------------------------------- ustunlarni ajratish

PHONE_RE = re.compile(r"\(?\b(\d{2})\)?[\s-]*(\d{3})[\s-]*(\d{2})[\s-]*(\d{2})\b")


def parse_name(text, rec):
    raw = text
    # Ism "Sardor", "Sardorbek" bo'lishi mumkin — faqat "... sardori" lavozimini hisobga olamiz
    if re.search(r"(guruhi|qalqon\W*)\s*sardori|\bsardori\b", raw, re.I):
        rec.is_leader = True
    m = PHONE_RE.search(raw)
    if m:
        rec.phone = "+998 {} {} {} {}".format(*m.groups())
        raw = raw[: m.start()] + " " + raw[m.end():]
    # "“Qalqon” jamoatchilik guruhi sardori" kabi qatorlarni olib tashlaymiz
    raw = re.sub(r"[“”\"«»]?\s*qalqon\s*[“”\"«»]?.*?(sardori|a.?zosi)", " ", raw, flags=re.I | re.S)
    words = _clean(raw).split()
    if not words:
        rec.warnings.append("F.I.Sh topilmadi")
        return
    suffix = ""
    if words[-1].lower().replace(APOS, "") in ("ogli", "qizi"):
        suffix = "qizi" if words[-1].lower() == "qizi" else f"o{APOS}g{APOS}li"
        words = words[:-1]
    words = [_cap(w) for w in words]
    rec.last_name = words[0]
    rec.first_name = words[1] if len(words) > 1 else ""
    rec.middle_name = " ".join(words[2:] + ([suffix] if suffix else []))
    if not rec.phone:
        rec.warnings.append("telefon raqami yo'q")


GROUP_RE = re.compile(r"(?<![\d.])([KkКк])?\s*[-–]?\s*(\d{2})\s*[-/–\s]\s*(\d{2})(?!\d)(\s*[-–]?\s*gu?ru[hx]\w*)?", re.I)
COURSE_RE = re.compile(r"(\d)\s*[-–]?\s*(bosqich|boskich|kurs)\w*", re.I)


def match_faculty(text):
    low = _norm(text)
    for name, short, patterns in FACULTIES:
        if any(re.search(p, low) for p in patterns):
            return name, short
    return None, None


def parse_study(text, rec, academic_year_start):
    raw = _clean(text)
    name, short = match_faculty(raw)
    m = re.search(r"fakulteti?\b\.?", raw, re.I)
    if name:
        rec.faculty_name, rec.faculty_short = name, short
    elif m:
        rec.faculty_name = _cap(raw[: m.end()].strip(" ."))
        rec.warnings.append(f"fakultet ro'yxatda yo'q, yangi qo'shiladi: «{rec.faculty_name}»")
    else:
        rec.warnings.append("fakultet aniqlanmadi")
    rest = raw[m.end():] if m else raw

    cm = COURSE_RE.search(rest)
    if cm:
        rec.course = int(cm.group(1))
        rest = rest[: cm.start()] + " " + rest[cm.end():]

    gm = GROUP_RE.search(rest)
    if gm:
        rec.group_name = f"K-{gm.group(2)}-{gm.group(3)}"
        year = 2000 + int(gm.group(3))
        if year > academic_year_start:
            rec.warnings.append(f"guruh raqamidagi yil ({gm.group(3)}) noto'g'ri ko'rinadi: {rec.group_name}")
        if rec.course is None:
            derived = academic_year_start - year + 1
            if 1 <= derived <= 6:
                rec.course, rec.course_derived = derived, True
        rest = rest[: gm.start()] + " " + rest[gm.end():]
    else:
        rec.warnings.append("guruh ko'rsatilmagan")
    if rec.course is None:
        rec.warnings.append("kurs aniqlanmadi")

    direction = re.sub(r"\b(talabasi|guru[hx]\w*)\b", " ", rest, flags=re.I)
    direction = re.sub(r"\by[oʻ]{1,2}\s?nalish\w*\b", " ", direction, flags=re.I)
    direction = _clean(direction)
    for pattern, repl in DIRECTION_FIXES:
        direction = re.sub(pattern, repl, direction, flags=re.I)
    rec.direction = _cap(direction[:1]) + direction[1:] if direction else ""
    if not rec.direction:
        rec.warnings.append("yo'nalish ko'rsatilmagan")


PINFL_RE = re.compile(r"(?<!\d)(\d{14}|\d{12})(?!\d)")
PASSPORT_RE = re.compile(r"\b([A-Z]{2})\s*(\d{7,9})\b")
DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
REGION_RE = re.compile(r"([A-Za-zʻ\-]+)\s+(viloyati|viloyat)\b|(Qoraqalpog\w*\s+Respublikasi)", re.I)
DISTRICT_RE = re.compile(r"([A-Za-zʻ\-]+)\s+(tumani|tuman|shahri|shaxri|shahar|shaxar)\b", re.I)


def pinfl_info(pinfl):
    """JSHSHIRdan tug'ilgan sana va jinsni aniqlash (1-raqam: 3/5 — erkak, 4/6 — ayol)."""
    if len(pinfl) != 14:
        return None, ""
    century = {"3": 1900, "4": 1900, "5": 2000, "6": 2000}.get(pinfl[0])
    if not century:
        return None, ""
    try:
        born = dt.date(century + int(pinfl[5:7]), int(pinfl[3:5]), int(pinfl[1:3]))
    except ValueError:
        return None, ""
    return born, ("m" if pinfl[0] in "35" else "f")


def parse_personal(text, rec):
    raw = _clean(re.sub(r"jsh?shir", " ", text, flags=re.I))
    dm = DATE_RE.search(raw)
    if dm:
        try:
            rec.passport_issued = dt.date(int(dm.group(3)), int(dm.group(2)), int(dm.group(1)))
        except ValueError:
            pass
        raw = raw[: dm.start()] + " " + raw[dm.end():]
    pm = PASSPORT_RE.search(raw)
    if pm:
        rec.passport = pm.group(1) + pm.group(2)
        if len(pm.group(2)) != 7:
            rec.warnings.append(f"pasport raqami {len(pm.group(2))} xonali (7 bo'lishi kerak): {rec.passport}")
        raw = raw[: pm.start()] + " " + raw[pm.end():]
    else:
        rec.warnings.append("pasport ma'lumoti yo'q")
    jm = PINFL_RE.search(raw)
    if jm:
        rec.pinfl = jm.group(1)
        raw = raw[: jm.start()] + " " + raw[jm.end():]
        if len(rec.pinfl) != 14:
            rec.warnings.append(f"JSHSHIR {len(rec.pinfl)} xonali (14 bo'lishi kerak): {rec.pinfl}")
        rec.birth_date, rec.gender = pinfl_info(rec.pinfl)
    else:
        rec.warnings.append("JSHSHIR yo'q")
    if rec.gender:
        by_name = "f" if rec.middle_name.endswith("qizi") else "m" if rec.middle_name.endswith("li") else ""
        if by_name and by_name != rec.gender:
            rec.warnings.append("JSHSHIRdagi jins otasining ismi qo'shimchasiga mos emas")

    addr = _clean(raw)
    rm = REGION_RE.search(addr)
    if rm:
        rec.region = rm.group(3) and "Qoraqalpogʻiston Respublikasi" or f"{_cap(rm.group(1))} viloyati"
    dmatch = DISTRICT_RE.search(addr, rm.end() if rm else 0)
    if dmatch:
        kind = "tumani" if dmatch.group(2).lower().startswith("tuman") else "shahri"
        rec.district = f"{_cap(dmatch.group(1))} {kind}"
        rest = addr[dmatch.end():]
        rest = re.sub(rf"^\W*{re.escape(dmatch.group(0))}", "", rest, flags=re.I)  # takrorlangan tuman nomi
    elif rm:
        rest = addr[rm.end():]
    else:
        rest = addr
    rec.address = _clean(rest)
    if not rec.region:
        rec.warnings.append("viloyat ko'rsatilmagan")


# ---------------------------------------------------------------- o'qish

def parse_docx(path_or_file, academic_year_start=2026):
    from docx import Document

    doc = Document(path_or_file)
    records = []
    for table in doc.tables:
        if not table.rows:
            continue
        header = [_cell_text(c) for c in table.rows[0].cells]
        try:
            cols = _find_columns(header)
        except ValueError:
            continue
        for i, row in enumerate(table.rows[1:], start=1):
            cells = row.cells
            name_text = _cell_text(cells[cols["name"]])
            if not name_text.strip():
                continue
            rec = MemberRecord(row=i, number=_clean(_cell_text(cells[0])) if cols.get("name") else "")
            parse_name(name_text, rec)
            parse_study(_cell_text(cells[cols["study"]]), rec, academic_year_start)
            parse_personal(_cell_text(cells[cols["personal"]]), rec)
            if "photo" in cols:
                images = _cell_images(cells[cols["photo"]], doc)
                if images:
                    rec.photo, rec.photo_ext = images[0]
                else:
                    rec.warnings.append("rasm yo'q")
            records.append(rec)
    if not records:
        raise ValueError("Hujjatda a'zolar jadvali topilmadi.")
    return records


def _photo_file(blob, max_side=640):
    """Rasmni kichraytirib JPEG ko'rinishida qaytaradi (bazada joy tejash uchun)."""
    try:
        from PIL import Image, ImageOps

        img = ImageOps.exif_transpose(Image.open(io.BytesIO(blob)))
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=86, optimize=True)
        return out.getvalue(), ".jpg"
    except Exception:  # noqa: BLE001 — Pillow bo'lmasa yoki rasm buzuq bo'lsa, aslini saqlaymiz
        return blob, None


# ---------------------------------------------------------------- bazaga yozish

def _find_existing(rec, faculty):
    if rec.pinfl:
        profile = MemberProfile.objects.filter(pinfl=rec.pinfl).select_related("user").first()
        if profile:
            return profile.user
    qs = User.objects.filter(role__in=QALQON_ROLES)
    if rec.phone:
        u = qs.filter(phone=rec.phone).first()
        if u:
            return u
    return qs.filter(last_name__iexact=rec.last_name, first_name__iexact=rec.first_name, faculty=faculty).first()


@transaction.atomic
def save_records(records, reset_passwords=False):
    result = {"created": [], "updated": [], "new_faculties": []}
    for rec in records:
        faculty = None
        if rec.faculty_name:
            faculty = Faculty.objects.filter(name__iexact=rec.faculty_name).first()
            if faculty is None:
                faculty = Faculty.objects.create(name=rec.faculty_name, short_name=rec.faculty_short)
                result["new_faculties"].append(faculty.name)
        user = _find_existing(rec, faculty)
        password = None
        if user is None:
            password = f"{secrets.randbelow(10 ** 8):08d}"
            user = User(username=make_username(rec.last_name, rec.first_name))
            user.set_password(password)
            created = True
        else:
            created = False
            if reset_passwords:
                password = f"{secrets.randbelow(10 ** 8):08d}"
                user.set_password(password)
        user.last_name, user.first_name, user.middle_name = rec.last_name, rec.first_name, rec.middle_name
        user.phone = rec.phone or user.phone
        user.faculty = faculty or user.faculty
        if rec.is_leader:
            user.role = User.Role.QALQON_LEADER
        elif created or user.role not in QALQON_ROLES:
            user.role = User.Role.QALQON_MEMBER
        user.position = "Qalqon jamoatchilik guruhi sardori" if rec.is_leader else "Qalqon jamoatchilik guruhi a'zosi"
        user.is_active = True
        user.save()

        profile, _ = MemberProfile.objects.get_or_create(user=user)
        for name in ("direction", "group_name", "course", "passport", "passport_issued", "pinfl",
                     "birth_date", "gender", "region", "district", "address"):
            value = getattr(rec, name)
            if value not in (None, ""):
                setattr(profile, name, value)
        if rec.photo:
            blob, ext = _photo_file(rec.photo)
            if profile.photo:
                profile.photo.delete(save=False)
            profile.photo.save(f"{user.pk}{ext or rec.photo_ext}", ContentFile(blob), save=False)
        profile.save()
        (result["created"] if created else result["updated"]).append(
            {"user": user, "password": password, "record": rec}
        )
    return result
