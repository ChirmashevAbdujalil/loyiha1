"""Jonli yuz tekshiruvi: topshiriq berish, kadrlarni tekshirish, natijani sessiyada saqlash."""
import logging
import secrets
import time
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import face
from .decorators import qalqon_required
from .models import DutyMember, FaceCheck, MemberProfile, qalqon_conf

logger = logging.getLogger("qalqon.face")

CHALLENGE_TTL = 180      # topshiriq berilgandan keyin kadrlar shu soniya ichida yuborilishi kerak
PASS_TTL = 600           # yuz tasdiqlangach, naryadni shu soniya ichida boshlash/yakunlash kerak
MAX_ATTEMPTS = 8         # 15 daqiqada shuncha urinish
MAX_FRAME_BYTES = 2 * 1024 * 1024


def face_required():
    return qalqon_conf()["face_check_enabled"]


def _key(kind, dm, action):
    return f"face_{kind}:{dm.pk}:{action}"


def _own(request, pk, action):
    dm = get_object_or_404(DutyMember.objects.select_related("duty", "member"), pk=pk)
    if dm.member_id != request.user.pk:
        raise PermissionDenied
    if action not in ("start", "finish"):
        raise PermissionDenied
    state = dm.start_state if action == "start" else dm.finish_state
    return dm, state == "ok"


@qalqon_required
@require_POST
def face_challenge(request, pk):
    action = request.POST.get("action", "")
    dm, allowed = _own(request, pk, action)
    if not allowed:
        return JsonResponse({"ok": False, "message": "Hozir bu amalni bajarib bo'lmaydi."}, status=400)
    since = timezone.now() - timedelta(minutes=15)
    if FaceCheck.objects.filter(duty_member=dm, created_at__gte=since).count() >= MAX_ATTEMPTS:
        return JsonResponse({"ok": False, "message": "Urinishlar ko'p bo'ldi. 15 daqiqadan keyin qayta urining "
                                                     "yoki sardorga murojaat qiling."}, status=429)
    reason = face.unavailable_reason()
    if reason:
        return JsonResponse({"ok": False, "message": f"Serverda yuz tekshiruvi sozlanmagan: {reason} "
                                                     f"Sardorga xabar bering (yoki Qalqon → Sozlamalarda yuz "
                                                     f"tekshiruvini vaqtincha o'chirsin)."}, status=503)
    steps = face.new_challenge()
    nonce = secrets.token_urlsafe(16)
    request.session[_key("challenge", dm, action)] = {"nonce": nonce, "steps": steps, "t": time.time()}
    return JsonResponse({"ok": True, "nonce": nonce, "steps": [{"key": s, "text": face.STEPS[s]} for s in steps]})


@qalqon_required
@require_POST
def face_verify(request, pk):
    action = request.POST.get("action", "")
    dm, allowed = _own(request, pk, action)
    if not allowed:
        return JsonResponse({"ok": False, "message": "Hozir bu amalni bajarib bo'lmaydi."}, status=400)
    challenge = request.session.pop(_key("challenge", dm, action), None)
    if not challenge or challenge["nonce"] != request.POST.get("nonce") \
            or time.time() - challenge["t"] > CHALLENGE_TTL:
        return JsonResponse({"ok": False, "message": "Tekshiruv muddati o'tdi — qaytadan boshlang."}, status=400)
    frames = []
    for i in range(len(challenge["steps"])):
        f = request.FILES.get(f"frame_{i}")
        if f is None or f.size > MAX_FRAME_BYTES:
            return JsonResponse({"ok": False, "message": "Kamera kadrlari to'liq kelmadi."}, status=400)
        frames.append(f.read())

    profile = MemberProfile.objects.filter(user=dm.member).first()
    try:
        reference = face.reference_feature(profile)
        verdict = face.verify(frames, challenge["steps"], reference, qalqon_conf()["face_threshold"])
    except face.FaceUnavailable as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=503)
    except Exception as exc:  # noqa: BLE001 — kutilmagan xato: 500 o'rniga aniq xabar, to'liq matn jurnalga
        logger.exception("Yuz tekshiruvida xato (navbat %s, %s)", dm.pk, action)
        return JsonResponse({"ok": False, "message": f"Serverda yuz tekshiruvida xato: {type(exc).__name__}: "
                                                     f"{str(exc)[:200]}. Sardorga xabar bering."}, status=500)

    check = FaceCheck(duty_member=dm, action=action, passed=verdict.passed, liveness=verdict.liveness,
                      similarity=verdict.similarity, message=verdict.message[:255],
                      user_agent=request.META.get("HTTP_USER_AGENT", "")[:300])
    center = frames[challenge["steps"].index("center")]
    try:
        check.selfie.save("selfie.jpg", ContentFile(center), save=False)
        check.save()
    except Exception as exc:  # noqa: BLE001 — masalan, media papkasiga yozish huquqi yo'q
        logger.exception("Yuz tekshiruvi natijasini saqlab bo'lmadi (navbat %s)", dm.pk)
        return JsonResponse({"ok": False, "message": f"Natijani saqlab bo'lmadi: {type(exc).__name__}: "
                                                     f"{str(exc)[:200]}. Sardorga xabar bering."}, status=500)
    if verdict.passed:
        request.session[_key("ok", dm, action)] = {"id": check.pk, "t": time.time()}
    return JsonResponse({"ok": verdict.passed, "message": verdict.message})


def check_passed(request, dm, action):
    """Naryadni boshlash/yakunlashdan oldin: yuz tekshiruvi o'tganmi? Xato matni yoki None qaytaradi."""
    if not face_required():
        return None
    token = request.session.get(_key("ok", dm, action))
    if not token or time.time() - token["t"] > PASS_TTL:
        return ("Avval jonli yuz tekshiruvidan o'ting. Tugmani bosganda kamera oynasi ochilmagan bo'lsa, sahifani "
                "yangilang; yordam bermasa, sardorga xabar bering (serverda collectstatic kerak).")
    return None


def consume(request, dm, action):
    token = request.session.pop(_key("ok", dm, action), None)
    if token:
        FaceCheck.objects.filter(pk=token["id"]).update(used=True)


@qalqon_required
def face_selfie(request, pk):
    import mimetypes

    from django.http import FileResponse, Http404

    check = get_object_or_404(FaceCheck.objects.select_related("duty_member"), pk=pk)
    if not (request.user.is_qalqon_staff or check.duty_member.member_id == request.user.pk):
        raise PermissionDenied
    if not check.selfie:
        raise Http404
    try:
        handle = check.selfie.open("rb")
    except FileNotFoundError:
        raise Http404
    return FileResponse(handle, content_type=mimetypes.guess_type(check.selfie.name)[0] or "image/jpeg")
