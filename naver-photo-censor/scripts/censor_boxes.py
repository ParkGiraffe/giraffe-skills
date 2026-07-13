#!/usr/bin/env python3
"""마이그레이션 이미지의 살 노출 부위를 회색 박스로 가린다(네이버 노출 가이드라인 대응).

사용:
  1. migrate.py --dry-run 으로 이미지 순서 확인(순서 번호 = 아래 spec 키)
  2. spec JSON 작성: {"이미지번호": [[x1,y1,x2,y2], ...]}  (0~1 비율 좌표)
  3. python3 censor_boxes.py --order <img_order.txt> --spec <boxes.json>
  4. migrate.py 재실행(캐시가 가려진 파일을 그대로 사용)

- 원본은 캐시/orig/에 백업, 재실행 시 항상 원본에서 다시 그림(박스 조정 안전)
- GIF는 전 프레임 적용. 얼굴은 가리지 말 것 — 가슴골/하의 부위만(사용자 지시).
- 부위 좌표는 격자 오버레이 이미지를 만들어 눈으로 확인하고 잡는 것이 정확하다.
"""
import sys, json, argparse, pathlib, shutil
from PIL import Image, ImageDraw, ImageSequence

GRAY = (150, 150, 150)
CACHE = pathlib.Path.home() / ".cache" / "naver-to-naver"
ORIG = CACHE / "orig"
ORIG.mkdir(exist_ok=True)

ap = argparse.ArgumentParser()
ap.add_argument("--order", required=True, help="이미지 경로 목록 파일(마이그레이션 순서)")
ap.add_argument("--spec", required=True, help="번호->박스목록 JSON")
args = ap.parse_args()
BOXES = {int(k): [tuple(b) for b in v] for k, v in json.load(open(args.spec)).items()}
files = [pathlib.Path(l.strip()) for l in open(args.order) if l.strip()]


def rects(size, boxes):
    w, h = size
    return [(int(x1*w), int(y1*h), int(x2*w), int(y2*h)) for x1, y1, x2, y2 in boxes]


def censor_still(src, dst, boxes):
    im = Image.open(src)
    mode = "RGBA" if im.mode in ("RGBA", "P", "LA") else "RGB"
    im = im.convert(mode)
    d = ImageDraw.Draw(im)
    for r in rects(im.size, boxes):
        d.rectangle(r, fill=GRAY)
    if dst.suffix.lower() in (".jpg", ".jpeg"):
        im.convert("RGB").save(dst, quality=92)
    else:
        im.save(dst)


def censor_gif(src, dst, boxes):
    im = Image.open(src)
    frames, durs = [], []
    for fr in ImageSequence.Iterator(im):
        f = fr.convert("RGB")
        d = ImageDraw.Draw(f)
        for r in rects(f.size, boxes):
            d.rectangle(r, fill=GRAY)
        frames.append(f)
        durs.append(fr.info.get("duration", im.info.get("duration", 80)))
    frames[0].save(dst, save_all=True, append_images=frames[1:],
                   duration=durs, loop=im.info.get("loop", 0), optimize=False)


done = 0
for idx, f in enumerate(files, 1):
    if idx not in BOXES:
        continue
    bak = ORIG / f.name
    if not bak.exists():
        shutil.copy2(f, bak)
    src = bak                                   # 항상 원본에서 다시 그림(박스 조정 재실행 안전)
    if f.suffix.lower() == ".gif":
        censor_gif(src, f, BOXES[idx])
    else:
        censor_still(src, f, BOXES[idx])
    done += 1
    print(f"{idx:2} {f.name} 박스 {len(BOXES[idx])}개")
print(f"가림 완료: {done}/{len(BOXES)}")
