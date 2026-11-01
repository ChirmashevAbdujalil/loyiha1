"""Qalqon a'zolarini bir serverdan boshqasiga ko'chirish uchun arxiv (.zip).

Arxivda: a'zolar (parol xeshi bilan — loginlar va parollar har ikki serverda bir xil ishlaydi),
shaxsiy ma'lumotlari, rasmlari, fakultetlar va binolar. Arxivda shaxsiy ma'lumotlar bor —
uni Git'ga qo'shmang va faqat ishonchli kanal orqali uzating.
"""
import datetime as dt
import json
import os
import zipfile

from django.core.files.base import ContentFile
from django.db import transaction

from core.models import Faculty, User

from .models import Building, MemberProfile

FORMAT = "qalqon-bundle-v1"
QALQON_ROLES = [User.Role.QALQON_MEMBER, User.Role.QALQON_LEADER, User.Role.QALQON_ADMIN]
USER_FIELDS = ["username", "password", "first_name", "last_name", "middle_name", "role", "phone", "position",
               "email", "is_active"]
PROFILE_FIELDS = ["direction", "group_name", "course", "room", "note", "gender", "passport", "pinfl",
                  "region", "district", "address"]
DATE_FIELDS = ["birth_date", "passport_issued"]
BUILDING_FIELDS = ["name", "short_name", "kind", "address", "radius_m", "is_active"]


def export_bundle(path):
    members = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        users = User.objects.filter(role__in=QALQON_ROLES).select_related("faculty", "qalqon_profile",
                                                                        "qalqon_profile__dormitory")
        for u in users:
            item = {f: getattr(u, f) for f in USER_FIELDS}
            item["faculty"] = u.faculty.name if u.faculty else None
            p = getattr(u, "qalqon_profile", None)
            if p:
                item["profile"] = {f: getattr(p, f) for f in PROFILE_FIELDS}
                item["profile"].update({f: getattr(p, f).isoformat() if getattr(p, f) else None for f in DATE_FIELDS})
                item["profile"]["dormitory"] = p.dormitory.name if p.dormitory else None
                if p.photo:
                    name = f"photos/{u.username}{os.path.splitext(p.photo.name)[1] or '.jpg'}"
                    with p.photo.open("rb") as fh:
                        zf.writestr(name, fh.read())
                    item["profile"]["photo"] = name
            members.append(item)
        data = {
            "format": FORMAT,
            "created": dt.datetime.now().isoformat(timespec="seconds"),
            "faculties": [{"name": f.name, "short_name": f.short_name} for f in Faculty.objects.all()
                          if f.tutors.filter(role__in=QALQON_ROLES).exists()],
            "buildings": [dict({k: getattr(b, k) for k in BUILDING_FIELDS},
                               latitude=str(b.latitude), longitude=str(b.longitude))
                          for b in Building.objects.all()],
            "members": members,
        }
        zf.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=1))
    return len(members)


@transaction.atomic
def import_bundle(path):
    result = {"created": 0, "updated": 0, "faculties": 0, "buildings": 0}
    with zipfile.ZipFile(path) as zf:
        data = json.loads(zf.read("data.json"))
        if data.get("format") != FORMAT:
            raise ValueError("Bu Qalqon arxivi emas yoki versiyasi mos emas.")
        for f in data["faculties"]:
            _, created = Faculty.objects.get_or_create(name=f["name"], defaults={"short_name": f["short_name"]})
            result["faculties"] += created
        for b in data["buildings"]:
            _, created = Building.objects.update_or_create(name=b["name"], defaults={k: v for k, v in b.items()
                                                                                    if k != "name"})
            result["buildings"] += created
        for item in data["members"]:
            profile_data = item.get("profile") or {}
            user = None
            if profile_data.get("pinfl"):
                p = MemberProfile.objects.filter(pinfl=profile_data["pinfl"]).select_related("user").first()
                user = p.user if p else None
            user = user or User.objects.filter(username=item["username"]).first()
            created = user is None
            if user is not None and user.role not in QALQON_ROLES:
                raise ValueError(f"«{item['username']}» logini bazada boshqa rol bilan band.")
            user = user or User(username=item["username"])
            for f in USER_FIELDS:
                if f == "username" and not created:
                    continue
                setattr(user, f, item[f])
            user.faculty = Faculty.objects.filter(name=item["faculty"]).first() if item["faculty"] else None
            user.save()
            profile, _ = MemberProfile.objects.get_or_create(user=user)
            for f in PROFILE_FIELDS:
                if f in profile_data:
                    setattr(profile, f, profile_data[f] if profile_data[f] is not None else
                            (None if f == "course" else ""))
            for f in DATE_FIELDS:
                value = profile_data.get(f)
                setattr(profile, f, dt.date.fromisoformat(value) if value else None)
            if profile_data.get("dormitory"):
                profile.dormitory = Building.objects.filter(name=profile_data["dormitory"]).first()
            if profile_data.get("photo"):
                if profile.photo:
                    profile.photo.delete(save=False)
                ext = os.path.splitext(profile_data["photo"])[1]
                profile.photo.save(f"{user.pk}{ext}", ContentFile(zf.read(profile_data["photo"])), save=False)
            profile.save()
            result["created" if created else "updated"] += 1
    return result
