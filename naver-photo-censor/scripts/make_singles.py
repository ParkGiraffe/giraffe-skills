#!/usr/bin/env python3
"""가리기 좌표 판독·검수용 싱글 이미지 렌더러.

두 모드:
  --grid   : 원본(백업본 우선)에 0.05 간격 격자(0.1마다 굵은선+라벨 1~9)를 입혀 920px로 저장
             → Claude가 한 장씩 Read로 정독해 부위 좌표(0~1 비율)를 판독하는 용도
  (기본)   : 가려진 현재 파일을 720px로 저장 → 가림 결과 실물 검수용

사용:
  make_singles.py --order <img_order.txt> --nums 5,13,24 [--grid] [--out <dir>]

주의: 좌표 판독·검수는 반드시 이 싱글(실물급)로만 한다. 축소 콘택트시트/2x2 격자 판독은
박스가 몸에 붙어 보여도 실물에선 빗나간다(반복 실사고).
"""
import argparse, pathlib
from PIL import Image, ImageDraw, ImageFont

CACHE_ORIG = pathlib.Path.home() / ".cache" / "naver-to-naver" / "orig"


def load_font(size):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except Exception:
        return ImageFont.load_default()


def render(path, grid, max_px):
    im = Image.open(path)
    im.seek(0)
    im = im.convert("RGB")
    im.thumbnail((max_px, max_px))
    if not grid:
        return im
    d = ImageDraw.Draw(im)
    w, h = im.size
    font = load_font(20)
    for i in range(1, 20):
        x, y = int(w * i / 20), int(h * i / 20)
        wd = 2 if i % 2 == 0 else 1
        col = (255, 0, 0) if i % 2 == 0 else (255, 120, 120)
        d.line([(x, 0), (x, h)], fill=col, width=wd)
        d.line([(0, y), (w, y)], fill=col, width=wd)
        if i % 2 == 0:
            d.text((x + 2, 2), str(i // 2), fill=(255, 255, 0), font=font)
            d.text((2, y + 2), str(i // 2), fill=(255, 255, 0), font=font)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", required=True, help="이미지 경로 목록(1줄 1경로, 순서 = 번호)")
    ap.add_argument("--nums", required=True, help="쉼표 구분 번호(1-base), 예: 5,13,24")
    ap.add_argument("--grid", action="store_true", help="원본+격자(좌표 판독용). 없으면 가림 검수용")
    ap.add_argument("--out", default=".", help="출력 폴더")
    args = ap.parse_args()

    files = [pathlib.Path(l.strip()) for l in open(args.order) if l.strip()]
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for n in [int(x) for x in args.nums.split(",")]:
        f = files[n - 1]
        src = f
        if args.grid:                      # 판독은 원본 기준(백업본이 있으면 그걸로)
            bak = CACHE_ORIG / f.name
            if bak.exists():
                src = bak
        im = render(src, args.grid, 920 if args.grid else 720)
        name = f"{'grid' if args.grid else 'verify'}_{n}.jpg"
        im.save(out / name, quality=87)
        print(out / name)


if __name__ == "__main__":
    main()
