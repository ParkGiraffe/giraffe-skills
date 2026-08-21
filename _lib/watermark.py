#!/usr/bin/env python3
"""사진 우하단에 블로그 주소 워터마크를 굽는다.

op5321 기존 글에서 실측한 값을 그대로 재현한다. 네이버가 본문 이미지를 폭 966px로
줄여 보여주므로, 그 표시 크기를 기준으로 값을 잡아 두고 사진마다 폭 비율로 환산한다.
그래야 720px 사진이든 4032px 사진이든 발행 후 워터마크가 같은 크기로 보인다.

실측 기준 (표시 폭 966px):
  도현체 29px / 박스 높이 38px / 글자 둘레 여백 3px / 검정 알파 0.44
  우측 여백 1px, 하단 여백 0px (모서리에 붙임)

--scale로 전체 크기를 줄이거나 키운다. 2026-08-13 사용자 확정값은 0.85.

사용:
  watermark.py <입력폴더|파일> <출력폴더> [--text ...] [--scale 0.85]
"""
import argparse, pathlib, sys
from PIL import Image, ImageDraw, ImageFont, ImageOps

FONT = "/Users/bag-yoseb/Library/Fonts/BMDOHYEON_otf.otf"
TEXT = "blog.naver.com/op5321"

REF_W = 966.0
FONT_PX = 29.0
PAD_PX = 3.0
MARGIN_R = 1.0
MARGIN_B = 0.0
ALPHA = 0.44
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".heic"}


def stamp(im: Image.Image, text: str = TEXT, scale: float = 0.85) -> Image.Image:
    """한 장에 워터마크를 얹어 돌려준다. EXIF 회전은 픽셀로 반영한다."""
    im = ImageOps.exif_transpose(im).convert("RGB")
    w, h = im.size
    k = w / REF_W * scale
    size = max(9, round(FONT_PX * k))
    pad = max(1, round(PAD_PX * k))
    mr, mb = round(MARGIN_R * k), round(MARGIN_B * k)

    font = ImageFont.truetype(FONT, size)
    # 도현체는 메트릭 여백이 넓어 폰트 높이로 박스를 잡으면 위아래가 떠 보인다.
    # 실제 잉크 범위(getbbox)로 재야 실측값과 맞는다.
    probe = Image.new("L", (size * len(text) + 80, size * 3), 0)
    ImageDraw.Draw(probe).text((20, 20), text, 255, font=font)
    bb = probe.getbbox()
    tw, th = bb[2] - bb[0], bb[3] - bb[1]

    bw, bh = tw + pad * 2, th + pad * 2
    x0, y0 = w - mr - bw, h - mb - bh

    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([x0, y0, x0 + bw - 1, y0 + bh - 1], fill=(0, 0, 0, round(255 * ALPHA)))
    d.text((x0 + pad - (bb[0] - 20), y0 + pad - (bb[1] - 20)), text,
           (255, 255, 255, 255), font=font)
    return Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--text", default=TEXT)
    ap.add_argument("--scale", type=float, default=0.85)
    a = ap.parse_args()

    src, dst = pathlib.Path(a.src), pathlib.Path(a.dst)
    if src.resolve() == dst.resolve():
        sys.exit("출력 폴더가 입력과 같습니다. 원본을 덮어쓰지 않도록 다른 폴더를 지정하세요.")
    files = [src] if src.is_file() else sorted(
        p for p in src.rglob("*") if p.suffix.lower() in EXTS and not p.name.startswith("."))
    if not files:
        sys.exit("대상 파일 없음")

    n = 0
    for p in files:
        rel = p.name if src.is_file() else p.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        stamp(Image.open(p), a.text, a.scale).save(out, quality=95, subsampling=0)
        n += 1
    print(f"워터마크 {n}장 -> {dst}")


if __name__ == "__main__":
    main()
