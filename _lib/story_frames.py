#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""story_frames.py: 게임 스토리 연재용 사진 파이프라인.

    story_frames.py scan   <편 폴더> --out <작업 폴더> [--originals <원본 폴더>] [--threshold 0.10]
    story_frames.py sheet  <작업 폴더>
    story_frames.py render <작업 폴더> --out <초안 폴더> --title <제목>
                           [--category <이름>] [--category-no N] [--date YYYY-MM-DD] [--no-watermark]
    story_frames.py check  <script.md>

편 폴더의 스위치 캡처(1920x1080 JPG)를 유형별로 추정해 plan.json을 만들고(scan), 사람이
콘택트 시트로 확인해 plan.json을 고친 뒤(sheet), 합성·크롭·제외를 적용해 초안 폴더의
images/와 script.md 뼈대, meta.json을 만든다(render). check는 캡션이 마침표로 끝나는지 본다.

유형 추정은 고정 영역의 단순 통계다. 결과 화면은 상단 띠와 전적 상자가 어둡고, 전투 대사
박스는 좌하단 상자가 어두우면서 흰 글자가 있고, 컷신 자막은 하단 띠에 검은 테두리의 흰
글자가 있다. 틀릴 수 있으므로 콘택트 시트 확인을 건너뛰지 않는다.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from watermark import add_watermark  # noqa: E402

FRAME = (1920, 1080)
TOP_REGION = (0, 0, 1920, 820)
SUBTITLE_BAND = (0, 830, 1920, 1030)
DIALOG_BOX = (340, 760, 1580, 990)
DIALOG_TEXT = (620, 790, 1540, 960)
RESULT_BAND = (0, 105, 1920, 215)
RESULT_ROW = (330, 340, 1050, 390)
PRESETS = {"popup": (398, 57, 1521, 1023), "scroll": (0, 830, 1920, 1030)}
BANDS = {"subtitle": SUBTITLE_BAND, "dialog": DIALOG_BOX}
SEP = 4
TEXT_RATIO = 0.003
STAMP16_RE = re.compile(r"(\d{16})")
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
CAPTION_MARK = "<!-- 캡션 -->"
INTRO_MARK = "<!-- 도입 -->"
FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
]


def load_font(size: int):
    for cand in FONT_CANDIDATES:
        if pathlib.Path(cand).exists():
            return ImageFont.truetype(cand, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def list_images(folder: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in folder.iterdir()
                  if p.suffix.lower() in IMAGE_EXTS and not p.name.startswith("."))


def _gray(img: Image.Image, box, size) -> list[int]:
    return list(img.convert("L").crop(box).resize(size).getdata())


def frame_diff(a: Image.Image, b: Image.Image, box=TOP_REGION) -> float:
    """상단 영역을 96x54 회색조로 줄여 비교한 평균 차이(0~1)."""
    pa = _gray(a, box, (96, 54))
    pb = _gray(b, box, (96, 54))
    return sum(abs(x - y) for x, y in zip(pa, pb)) / (96 * 54 * 255)


def same_framing(a: Image.Image, b: Image.Image, threshold: float = 0.10) -> bool:
    return frame_diff(a, b) < threshold


def dark_ratio(img: Image.Image, box) -> float:
    px = _gray(img, box, (192, 12))
    return sum(1 for v in px if v < 80) / len(px)


def outline_ratio(img: Image.Image, box, size=(640, 66)) -> float:
    """검은 테두리를 두른 흰 글자의 비율. 밝은 픽셀 좌우 2px 안에 어두운 픽셀이 있으면 센다."""
    w, h = size
    px = _gray(img, box, size)
    hits = 0
    for y in range(h):
        row = px[y * w:(y + 1) * w]
        for x in range(2, w - 2):
            if row[x] > 200 and (row[x - 2] < 70 or row[x - 1] < 70 or row[x + 1] < 70 or row[x + 2] < 70):
                hits += 1
    return hits / (w * h)


def classify(img: Image.Image) -> str:
    if dark_ratio(img, RESULT_BAND) > 0.85 and dark_ratio(img, RESULT_ROW) > 0.9:
        return "result"
    if dark_ratio(img, DIALOG_TEXT) > 0.55 and outline_ratio(img, DIALOG_TEXT) > TEXT_RATIO:
        return "dialog"
    if outline_ratio(img, SUBTITLE_BAND) > TEXT_RATIO:
        return "subtitle"
    return "plain"


def resolve_source(path: pathlib.Path, originals: pathlib.Path | None) -> tuple[pathlib.Path, bool]:
    """손 크롭본(1920x1080이 아님)이면 원본 폴더에서 같은 16자리 시각의 파일을 찾는다."""
    with Image.open(path) as im:
        size = im.size
    if size == FRAME or originals is None:
        return path, False
    m = STAMP16_RE.search(path.name)
    if m:
        for cand in sorted(originals.glob(f"*{m.group(1)}*")):
            if cand.suffix.lower() in IMAGE_EXTS and not cand.name.startswith("."):
                return cand, True
    return path, False


def build_plan(ep_folder: pathlib.Path, originals: pathlib.Path | None, threshold: float) -> dict:
    items: list[dict] = []
    prev_img = None
    prev_item = None
    for p in list_images(ep_folder):
        src, restored = resolve_source(p, originals)
        img = Image.open(src).convert("RGB")
        kind = classify(img) if img.size == FRAME else "plain"
        rec: dict = {"type": "photo", "src": str(src), "guess": kind}
        if restored:
            rec["hand_crop"] = p.name
        if kind == "result":
            rec = {"type": "skip", "src": str(src), "guess": kind, "reason": "결과 화면"}
        elif (kind in BANDS and prev_item is not None and prev_item.get("guess") == kind
              and prev_img is not None and same_framing(prev_img, img, threshold)):
            if prev_item["type"] == "strip":
                prev_item["src"].append(str(src))
            else:
                prev_item.update({"type": "strip", "lead": prev_item["src"],
                                  "src": [str(src)], "band": kind})
            prev_img = img
            continue
        items.append(rec)
        prev_item = rec
        prev_img = img
    section_title = re.sub(r"^\d+_", "", ep_folder.name)
    return {"source": str(ep_folder), "originals": str(originals) if originals else None,
            "threshold": threshold,
            "sections": [{"title": section_title, "items": items}]}


def read_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_scan(args) -> None:
    ep = pathlib.Path(args.ep_folder).expanduser().resolve()
    originals = pathlib.Path(args.originals).expanduser().resolve() if args.originals else None
    out = pathlib.Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = build_plan(ep, originals, args.threshold)
    write_json(out / "plan.json", plan)
    items = plan["sections"][0]["items"]
    kinds = {}
    for it in items:
        kinds[it["type"]] = kinds.get(it["type"], 0) + 1
    print(f"사진 {len(list_images(ep))}장 -> 항목 {len(items)}개 {kinds} -> {out / 'plan.json'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="편 폴더를 훑어 plan.json을 만든다")
    p.add_argument("ep_folder")
    p.add_argument("--out", required=True)
    p.add_argument("--originals")
    p.add_argument("--threshold", type=float, default=0.10)
    p.set_defaults(func=cmd_scan)

    args = ap.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
