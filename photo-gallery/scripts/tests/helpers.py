#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""테스트용 가짜 트리 생성. 실제 T7을 절대 건드리지 않습니다."""
import io
import pathlib

from PIL import Image


def make_tree(root, files):
    """files는 {상대경로: bytes}. 부모 폴더를 만들며 씁니다."""
    root = pathlib.Path(root)
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def jpeg_bytes(w=64, h=48, color=(120, 60, 30), exif_dt=None):
    """단색 JPEG. exif_dt는 'YYYY:MM:DD HH:MM:SS' 형식입니다."""
    im = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    if exif_dt:
        ex = Image.Exif()
        ex[36867] = exif_dt          # DateTimeOriginal
        ex[271] = "TestMake"         # Make
        ex[272] = "TestModel"        # Model
        im.save(buf, "JPEG", exif=ex.tobytes())
    else:
        im.save(buf, "JPEG")
    return buf.getvalue()


def png_bytes(w=64, h=48, color=(10, 200, 90)):
    """EXIF 없는 PNG. 스크린샷 판정 테스트에 씁니다."""
    im = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def gradient_jpeg(w=64, h=48, seed=0, quality=95):
    """dHash가 서로 다르게 나오는 이미지. seed를 바꾸면 다른 그림이 됩니다."""
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 3 + seed * 37) % 256,
                        (y * 5 + seed * 11) % 256,
                        (x + y + seed) % 256)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return buf.getvalue()
