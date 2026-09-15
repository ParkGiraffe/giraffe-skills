#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파일 하나를 조사해 해시, 종류, 지각해시, EXIF를 뽑습니다. 파일을 고치지 않습니다."""
import hashlib
import io
import os
import pathlib
import re

from PIL import Image

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".bmp", ".tif", ".tiff"}

# 삼성 스크린샷: Screenshot_20260501_155542_Pokmon GO.jpg
SS_SAMSUNG = re.compile(r"^Screenshot_\d{8}[-_]\d{6}")
# 아이폰 스크린샷: IMG_2713.PNG (아이폰은 카메라 사진을 PNG로 저장하지 않습니다)
SS_IPHONE = re.compile(r"^IMG_\d+\.png$", re.IGNORECASE)
SS_WORDS = re.compile(r"스크린샷|Screen ?Shot|Screen[ _]Recording|Shipping Screenshot",
                      re.IGNORECASE)

EXIF_DT_ORIGINAL = 36867
EXIF_DT = 306
EXIF_MAKE = 271
EXIF_MODEL = 272
EXIF_GPS = 34853


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def hamming(a, b):
    return (a ^ b).bit_count()


def phash_to_db(value):
    """지각해시를 인덱스에 넣을 형태로 바꿉니다.

    dHash 는 부호 없는 64비트라 최상위 비트가 1이면 2^63을 넘어
    SQLite INTEGER 에 안 들어갑니다. 16자리 16진수 문자열로 저장합니다.
    """
    return None if value is None else format(value, "016x")


def phash_from_db(value):
    """인덱스에서 읽은 지각해시를 정수로 되돌립니다."""
    if value is None:
        return None
    try:
        return int(value, 16)
    except (TypeError, ValueError):
        return None


def _dhash_image(im):
    """9x8 흑백으로 줄여 가로 이웃 밝기를 비교한 64비트 지문입니다.

    화질과 포맷이 달라도 같은 장면이면 같은 지문이 나옵니다.
    """
    try:
        im.draft("L", (64, 64))   # JPEG 디코딩 가속
    except Exception:
        pass
    im = im.convert("L").resize((9, 8), Image.BILINEAR)
    px = list(im.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            left = px[row * 9 + col]
            right = px[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def dhash(path):
    """파일에서 지각해시를 구합니다. 이미지가 아니면 None입니다."""
    try:
        with Image.open(path) as im:
            return _dhash_image(im)
    except Exception:
        return None


def dhash_bytes(data):
    """내려받은 바이트에서 지각해시를 구합니다. Task 6의 dHash 폴백용입니다."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            return _dhash_image(im)
    except Exception:
        return None


def _gps(exif):
    try:
        g = exif.get_ifd(EXIF_GPS)
    except Exception:
        return None, None
    if not g:
        return None, None

    def dms(v, ref, neg):
        d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
        return -d if ref in neg else d

    try:
        lat = dms(g[2], g[1], ("S",))
        lon = dms(g[4], g[3], ("W",))
        return lat, lon
    except Exception:
        return None, None


def read_exif(path):
    """EXIF와 치수를 읽습니다. 못 읽는 값은 None입니다."""
    out = {"dt": None, "make": None, "model": None,
           "width": None, "height": None, "gps_lat": None, "gps_lon": None}
    ext = pathlib.Path(path).suffix.lower()
    if ext not in IMAGE_EXT:
        return out
    try:
        with Image.open(path) as im:
            out["width"], out["height"] = im.size
            ex = im.getexif()
    except Exception:
        return out
    if not ex:
        return out
    dt = ex.get(EXIF_DT_ORIGINAL) or ex.get(EXIF_DT)
    if dt:
        dt = str(dt).strip()
        if dt and not dt.startswith("0000"):
            out["dt"] = dt
    for key, tag in (("make", EXIF_MAKE), ("model", EXIF_MODEL)):
        v = ex.get(tag)
        if v:
            out[key] = str(v).strip() or None
    out["gps_lat"], out["gps_lon"] = _gps(ex)
    return out


def classify(basename, exif):
    """사진, 스크린샷, 동영상 중 하나를 돌려줍니다.

    두 번째 조건(EXIF 없는 PNG)은 오탐이 납니다. 웹에서 저장한 그림이나 스캔본도
    EXIF 없는 PNG입니다. 배치 계획 단계에서 사용자가 검토합니다.
    """
    ext = os.path.splitext(basename)[1].lower()
    if ext in VIDEO_EXT:
        return "동영상"
    if SS_SAMSUNG.match(basename) or SS_WORDS.search(basename):
        return "스크린샷"
    if SS_IPHONE.match(basename) and not exif.get("make"):
        return "스크린샷"
    if ext == ".png" and not exif.get("make"):
        return "스크린샷"
    return "사진"
