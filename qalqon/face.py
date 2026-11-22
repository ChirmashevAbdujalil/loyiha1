"""Jonli yuz tekshiruvi: OpenCV YuNet (yuzni topish) + SFace (yuzni solishtirish).

Oqim:
  1. Server tasodifiy topshiriq beradi: "to'g'ri qarang", "chapga buring", "o'ngga buring" (tartibi aralash).
  2. Telefon old kamerasidan har bir qadamda bitta kadr olinadi va serverga yuboriladi.
  3. Server har bir kadrda yuzni topadi, boshning burilishini (burun ko'zlarga nisbatan qayerdaligi)
     tekshiradi — qog'ozdagi yoki ekrandagi qotib turgan rasm boshini bura olmaydi (jonlilik).
  4. To'g'ri qaragan kadrdagi yuz a'zoning bazadagi rasmi bilan solishtiriladi (kosinus o'xshashlik).

Cheklov: bu oddiy jonlilik tekshiruvi; oldindan yozib olingan video bilan aldashga urinishni
to'liq istisno qilmaydi — shuning uchun har bir tekshiruvning selfisi sardor ko'rishi uchun saqlanadi.
"""
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent / "face_models"
DETECTOR_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"

STEPS = {
    "center": "Telefonga to'g'ri qarang",
    "left": "Boshingizni sekin CHAPGA buring",
    "right": "Boshingizni sekin O'NGGA buring",
}
CENTER_MAX_DEV = 0.16   # to'g'ri qaraganda burun ko'zlar o'rtasidan shuncha (nisbat) uzoqlashmasligi kerak
TURN_MIN_DEV = 0.12     # boshini burganda burun (to'g'ri kadrga nisbatan) kamida shuncha siljishi kerak
SAME_PERSON_MIN = 0.30  # kadrlar orasida bir odam ekanini tekshirish chegarasi
MIN_FACE_PX = 70        # yuz kadrda juda kichik bo'lmasin
MAX_SIDE = 640

_lock = threading.Lock()
_models = {}


class FaceUnavailable(Exception):
    """Modellar yoki OpenCV o'rnatilmagan."""


def _load():
    if "det" in _models:
        return _models["det"], _models["rec"]
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover — requirements.txt da bor
        raise FaceUnavailable("OpenCV o'rnatilmagan: pip install opencv-python-headless") from exc
    if not DETECTOR_MODEL.exists() or not RECOGNIZER_MODEL.exists():
        raise FaceUnavailable("Yuz tekshiruvi modellari topilmadi (qalqon/face_models).")
    _models["det"] = cv2.FaceDetectorYN.create(str(DETECTOR_MODEL), "", (320, 320), 0.8, 0.3, 50)
    _models["rec"] = cv2.FaceRecognizerSF.create(str(RECOGNIZER_MODEL), "")
    return _models["det"], _models["rec"]


def available():
    try:
        _load()
        return True
    except FaceUnavailable:
        return False


def decode_image(data):
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    return img


@dataclass
class FrameResult:
    found: bool
    faces: int = 0
    yaw: float = 0.0          # -0.5..0.5; 0 — to'g'ri qaragan
    width: int = 0
    feature: object = None


def analyze(img):
    """Kadrdagi eng katta yuzni topadi, burilishini va "yuz izi"ni hisoblaydi."""
    det, rec = _load()
    h, w = img.shape[:2]
    with _lock:
        det.setInputSize((w, h))
        _, faces = det.detect(img)
        if faces is None or len(faces) == 0:
            return FrameResult(found=False)
        face = max(faces, key=lambda f: f[2] * f[3])
        aligned = rec.alignCrop(img, face)
        feature = rec.feature(aligned).copy()
    # YuNet landmarklari: [4,5] o'ng ko'z, [6,7] chap ko'z, [8,9] burun
    ex1, ex2, nx = float(face[4]), float(face[6]), float(face[8])
    span = abs(ex2 - ex1) or 1.0
    yaw = (nx - min(ex1, ex2)) / span - 0.5
    return FrameResult(found=True, faces=len(faces), yaw=yaw, width=int(face[2]), feature=feature)


def similarity(f1, f2):
    import cv2

    _, rec = _load()
    with _lock:
        return float(rec.match(f1, f2, cv2.FaceRecognizerSF_FR_COSINE))


def feature_to_bytes(feature):
    import numpy as np

    return np.asarray(feature, dtype=np.float32).tobytes()


def feature_from_bytes(data):
    import numpy as np

    return np.frombuffer(bytes(data), dtype=np.float32).reshape(1, -1)


def reference_feature(profile):
    """A'zo rasmining "yuz izi" — bazada keshlanadi, rasm almashsa qayta hisoblanadi."""
    if not profile or not profile.photo:
        return None
    if profile.face_embedding and profile.face_embedding_src == profile.photo.name:
        return feature_from_bytes(profile.face_embedding)
    try:
        with profile.photo.open("rb") as fh:
            img = decode_image(fh.read())
    except FileNotFoundError:
        return None
    if img is None:
        return None
    res = analyze(img)
    if not res.found:
        return None
    profile.face_embedding = feature_to_bytes(res.feature)
    profile.face_embedding_src = profile.photo.name
    profile.save(update_fields=["face_embedding", "face_embedding_src"])
    return res.feature


def new_challenge():
    sides = ["left", "right"]
    secrets.SystemRandom().shuffle(sides)
    return ["center"] + sides


@dataclass
class Verdict:
    passed: bool
    liveness: bool
    similarity: float | None
    message: str


def verify(frames, steps, reference, threshold):
    """frames — topshiriq qadamlari tartibidagi rasmlar (bytes)."""
    if len(frames) != len(steps):
        return Verdict(False, False, None, "Kadrlar soni topshiriqqa mos emas.")
    results = {}
    for step, data in zip(steps, frames):
        img = decode_image(data)
        if img is None:
            return Verdict(False, False, None, "Rasmni o'qib bo'lmadi.")
        res = analyze(img)
        if not res.found:
            return Verdict(False, False, None, f"«{STEPS[step]}» qadamida yuz topilmadi. Yuzingiz kadrda, "
                                               f"yorug' joyda bo'lsin.")
        if res.width < MIN_FACE_PX:
            return Verdict(False, False, None, "Yuz juda kichik — telefonni yaqinroq tuting.")
        results[step] = res

    center = results["center"]
    if abs(center.yaw) > CENTER_MAX_DEV:
        return Verdict(False, False, None, "Birinchi kadrda telefonga to'g'ri qaramadingiz.")
    # Burilish to'g'ri qaragan kadrga nisbatan o'lchanadi (yuz assimetriyasi va model xatoligi chiqib ketadi).
    # Kamera rasmi ko'zgu bo'lishi mumkin, shuning uchun qaysi tomon ekanini emas — ikki tomonga qarama-qarshi
    # burilganini tekshiramiz. Tekis rasmni (qog'oz/ekran) burganda bu nisbat deyarli o'zgarmaydi.
    left = results["left"].yaw - center.yaw
    right = results["right"].yaw - center.yaw
    liveness = (abs(left) >= TURN_MIN_DEV and abs(right) >= TURN_MIN_DEV and left * right < 0)
    if not liveness:
        return Verdict(False, False, None, "Bosh burilishi aniqlanmadi — ko'rsatmaga ko'ra boshingizni "
                                           "chapga va o'ngga aniqroq buring.")
    for side in ("left", "right"):
        if similarity(center.feature, results[side].feature) < SAME_PERSON_MIN:
            return Verdict(False, True, None, "Kadrlarda turli odamlar aniqlandi.")
    if reference is None:
        return Verdict(False, True, None, "Bazada rasmingiz yo'q yoki undan yuz aniqlanmadi — sardorga "
                                          "murojaat qiling.")
    score = similarity(center.feature, reference)
    if score < threshold:
        return Verdict(False, True, score, f"Yuz bazadagi rasmingizga mos kelmadi ({round(max(score, 0) * 100)}%). "
                                           f"Yorug' joyda, ko'zoynaksiz qayta urining.")
    return Verdict(True, True, score, f"Yuz tasdiqlandi ({round(score * 100)}%).")
