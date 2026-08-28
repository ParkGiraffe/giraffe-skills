#!/usr/bin/env python3
"""사진 우하단에 blog.naver.com/op5321 워터마크를 굽는다. (리포 정본)

한때 tistory-to-naver와 blog 쪽에 같은 기능이 따로 있었다. 두 대의 컴퓨터에서
각자 만들어져 상수도 폰트 경로도 달랐다. 여기로 합치고 양쪽이 이 파일을 쓴다.

스타일 상수는 **사용자 확정값(2026-08-20)** 이다. 네이버 수기 발행본을 표시 폭
966px에서 실측하고 사용자 피드백으로 조정한 값이라 임의로 바꾸지 않는다:
  - 반투명 검정 바가 우측·하단 모서리에 딱 붙고 흰색 배달의민족 도현체
  - 글자 높이 = 이미지 폭의 2.57% (실물보다 살짝 작게)
  - 불투명도 150/255. "뒤에 비쳐도 되니까 검게 하지 말 것"이 사용자 지시라
    완전 불투명으로 올리지 않는다.
  - 글자가 바에 거의 꽉 차게. 여백을 크게 잡으면 사용자가 바로 지적한다.
(2026-08-13에 blog 쪽에서 쓰던 값은 도현체 29px@966에 알파 0.44였다. 크기는 거의
같고 진하기만 달랐는데, 더 나중에 확정된 위 값으로 통일했다.)

크기를 사진 폭 비율로 잡는 이유는 네이버가 본문 이미지를 폭 966px로 줄여 보여주기
때문이다. 720px 사진이든 4032px 사진이든 발행 후 워터마크가 같은 크기로 보인다.

GIF는 프레임이 깨지므로 건너뛴다.

두 가지로 쓴다:
  add_watermark(path)            파일을 제자리에서 처리 (마이그레이션 중 내려받은 사진)
  watermark.py <입력> <출력>      폴더를 통째로 새 폴더에 (원본 보존이 필요할 때)
"""
import argparse, os, pathlib, sys
from PIL import Image, ImageDraw, ImageFont, ImageOps

# 폰트 파일명이 설치 시점에 따라 다르다. 있는 것을 쓴다.
FONT_CANDIDATES = [
    "~/Library/Fonts/BMDOHYEON_otf.otf",
    "~/Library/Fonts/BM_Dohyeon.otf",
    "/Library/Fonts/BMDOHYEON_otf.otf",
    "/Library/Fonts/BM_Dohyeon.otf",
]
TEXT = "blog.naver.com/op5321"
FONT_RATIO = 0.0257     # 글자 높이 / 이미지 폭
OPACITY = 150           # 검정 바 알파 (0-255)
BAR_RGB = (20, 20, 20)
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".heic"}


def font_path():
    for c in FONT_CANDIDATES:
        p = os.path.expanduser(c)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(
        "배달의민족 도현체를 찾을 수 없습니다. 다음 중 하나에 설치하세요:\n  "
        + "\n  ".join(FONT_CANDIDATES))


def stamp(im: Image.Image, text: str = TEXT, scale: float = 1.0,
          opacity: int = OPACITY) -> Image.Image:
    """한 장에 워터마크를 얹어 돌려준다. EXIF 회전은 픽셀로 반영한다."""
    im = ImageOps.exif_transpose(im).convert("RGB")
    W, H = im.size
    font_px = max(16, int(W * FONT_RATIO * scale))
    font = ImageFont.truetype(font_path(), font_px)

    # 도현체는 메트릭 여백이 넓어 폰트 높이로 바를 잡으면 글자가 떠 보인다.
    # 실제 잉크 범위(textbbox)로 재야 "글자가 바에 꽉 찬" 확정 스타일이 나온다.
    x0, y0, x1, y1 = ImageDraw.Draw(im).textbbox((0, 0), text, font=font)
    tw, th = x1 - x0, y1 - y0
    pad_x = max(3, int(font_px * 0.14))
    pad_y = max(2, int(font_px * 0.09))
    bar_w, bar_h = tw + pad_x * 2, th + pad_y * 2

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    bx0, by0 = W - bar_w, H - bar_h
    d.rectangle([bx0, by0, W, H], fill=BAR_RGB + (opacity,))
    d.text((bx0 + pad_x - x0, by0 + pad_y - y0), text, font=font,
           fill=(255, 255, 255, 255))
    return Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")


def add_watermark(path, text=TEXT, opacity=OPACITY):
    """파일을 제자리에서 처리. GIF·미지원 포맷은 그대로 둔다.

    마이그레이션 도중 내려받은 사진에 쓴다. 성공 True, 건너뜀/실패 False.
    """
    try:
        im = Image.open(path)
        if im.format == "GIF" or getattr(im, "is_animated", False):
            return False
        stamp(im, text, opacity=opacity).save(path, quality=92)
        return True
    except Exception as e:
        print(f"[watermark] 실패({os.path.basename(path)}): {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--text", default=TEXT)
    ap.add_argument("--scale", type=float, default=1.0,
                    help="확정 상수에 곱할 배율. 보통 건드리지 않는다.")
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
