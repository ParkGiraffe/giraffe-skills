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

유형 추정은 고정 영역의 단순 통계다. 결과 화면은 전적 세 줄이 모두 어둡고 흰 글자가 있고,
전투 대사 박스는 좌하단 상자가 어두우면서 흰 글자가 있고, 컷신 자막은 하단 띠에 검은
테두리의 흰 글자가 있다. 틀릴 수 있으므로 콘택트 시트 확인을 건너뛰지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
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
RESULT_ROWS = [(330, 340, 1050, 390), (330, 435, 1050, 485), (330, 530, 1050, 580)]
PRESETS = {"popup": (398, 57, 1521, 1023), "scroll": (0, 830, 1920, 1030)}
BANDS = {"subtitle": SUBTITLE_BAND, "dialog": DIALOG_BOX}
SEP = 4
TEXT_RATIO = 0.0015
RESULT_TEXT_RATIO = 0.008
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
    if all(dark_ratio(img, box) > 0.7 and outline_ratio(img, box) > RESULT_TEXT_RATIO
           for box in RESULT_ROWS):
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


SHEET_LABEL_W = 300
SHEET_ROW_PAD = 8


def item_sources(it: dict) -> list[str]:
    if it["type"] == "strip":
        return [it["lead"]] + list(it["src"])
    if it["type"] in ("video", "heading"):
        return []
    return [it["src"]]


def render_sheets(plan: dict, out_dir: pathlib.Path, per_sheet: int = 12,
                  thumb=(320, 180)) -> list[pathlib.Path]:
    font = load_font(22)
    rows = []
    idx = 0
    for sec in plan["sections"]:
        for it in sec["items"]:
            idx += 1
            label = f"{idx:03d} {it['type']} {it.get('guess', '')}".rstrip()
            if it.get("hand_crop"):
                label += " 손크롭"
            if it["type"] == "video":
                label += " " + it.get("file", "")
            if it["type"] == "heading":
                label += " " + it.get("title", "")
            rows.append((label, item_sources(it)[:6]))
    sheets = []
    tw, th = thumb
    for n in range(0, len(rows), per_sheet):
        chunk = rows[n:n + per_sheet]
        sheet = Image.new("RGB", (SHEET_LABEL_W + 6 * tw, len(chunk) * (th + SHEET_ROW_PAD)), (20, 20, 20))
        draw = ImageDraw.Draw(sheet)
        for r, (label, paths) in enumerate(chunk):
            y = r * (th + SHEET_ROW_PAD)
            draw.text((4, y + 4), label, fill=(255, 255, 255), font=font)
            for k, p in enumerate(paths):
                with Image.open(p) as src:
                    im = ImageOps.fit(src.convert("RGB"), thumb)
                    sheet.paste(im, (SHEET_LABEL_W + k * tw, y))
        out = out_dir / f"sheet_{n // per_sheet + 1:02d}.jpg"
        sheet.save(out, quality=80)
        sheets.append(out)
    return sheets


def cmd_sheet(args) -> None:
    work = pathlib.Path(args.work_dir).expanduser().resolve()
    plan = read_json(work / "plan.json")
    for p in render_sheets(plan, work):
        print(p)


def make_strip(paths: list[str], band: str) -> Image.Image:
    """여러 장의 같은 영역을 잘라 세로로 잇고 사이에 SEP px 검은 선을 둔다."""
    box = BANDS[band]
    w, h = box[2] - box[0], box[3] - box[1]
    out = Image.new("RGB", (w, h * len(paths) + SEP * (len(paths) - 1)), (0, 0, 0))
    for i, p in enumerate(paths):
        with Image.open(p) as src:
            out.paste(src.convert("RGB").crop(box), (0, i * (h + SEP)))
    return out


def crop_preset(path: str, preset: str) -> Image.Image:
    with Image.open(path) as src:
        return src.convert("RGB").crop(PRESETS[preset]).copy()


def render(plan: dict, out_dir: pathlib.Path, title: str, category: str,
           category_no: int | None, date: str, watermark: bool = True) -> dict:
    images = out_dir / "images"
    images.mkdir(parents=True, exist_ok=True)
    lines = ["---", f'title: "{title}"', f"category: {category}", f"date: {date}", "---", "",
             f"# {title}", "", INTRO_MARK, ""]
    n = 0
    count = 0
    videos = []
    for si, sec in enumerate(plan["sections"]):
        if si > 0:
            lines += ["---", ""]
        lines += [f"## {sec['title']}", ""]
        for it in sec["items"]:
            t = it["type"]
            if t == "skip":
                continue
            if t == "heading":
                lines += [f"### {it['title']}", ""]
                continue
            if t == "video":
                if not (images / it["file"]).exists():
                    print(f"[경고] 영상 파일이 아직 없습니다: {images / it['file']}")
                lines += [f"[영상 자리 : images/{it['file']}]", "", CAPTION_MARK, ""]
                videos.append({"file": it["file"], "title": it.get("title") or it["file"]})
                continue
            n += 1
            if t == "photo":
                dst = images / f"{n:03d}.jpg"
                shutil.copyfile(it["src"], dst)
                count += 1
                lines += [f"![](images/{dst.name})", "", CAPTION_MARK, ""]
            elif t == "crop":
                dst = images / f"{n:03d}_crop.jpg"
                crop_preset(it["src"], it["preset"]).save(dst, quality=92)
                count += 1
                lines += [f"![](images/{dst.name})", "", CAPTION_MARK, ""]
            elif t == "strip":
                lead = images / f"{n:03d}.jpg"
                shutil.copyfile(it["lead"], lead)
                count += 1
                strip = images / f"{n:03d}_strip.jpg"
                make_strip(it["src"], it["band"]).save(strip, quality=92)
                count += 1
                lines += [f"![](images/{lead.name})", "", f"![](images/{strip.name})", "", CAPTION_MARK, ""]
            else:
                raise ValueError(f"모르는 항목 유형입니다: {t}")
    if watermark:
        for p in sorted(images.glob("*.jpg")):
            add_watermark(str(p))
    (out_dir / "script.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta = {
        "title_candidates": [title],
        "category": category,
        "category_no": category_no,
        "hashtags": [],
        "images": {"count": count, "source_folder": str(images.resolve())},
        "videos_folder": str(images.resolve()),
        "videos": videos,
    }
    write_json(out_dir / "meta.json", meta)
    return meta


IMG_LINE = re.compile(r"^!\[[^\]]*\]\([^)]+\)\s*$")
VIDEO_LINE = re.compile(r"^\[영상 자리\s*:")
STRUCT_LINE = re.compile(r"^(#{1,6}\s|---\s*$|!\[|\[영상 자리)")


def check_captions(md: str) -> list[tuple[int, str]]:
    """사진이나 영상 자리 뒤에 오는 캡션이 마침표로 끝나는지, 빈 표식이 남았는지 본다."""
    lines = md.splitlines()
    problems: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if line.strip() == INTRO_MARK:
            problems.append((i + 1, "도입이 비어 있습니다"))
            continue
        if not (IMG_LINE.match(line) or VIDEO_LINE.match(line)):
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            break
        nxt = lines[j].strip()
        if nxt == CAPTION_MARK:
            problems.append((j + 1, "캡션이 비어 있습니다"))
            continue
        if STRUCT_LINE.match(nxt):
            continue
        if not nxt.endswith("."):
            problems.append((j + 1, f"마침표로 끝나지 않습니다: {nxt[-20:]}"))
    return problems


def cmd_render(args) -> None:
    work = pathlib.Path(args.work_dir).expanduser().resolve()
    plan = read_json(work / "plan.json")
    out = pathlib.Path(args.out).expanduser().resolve()
    date = args.date or dt.date.today().isoformat()
    meta = render(plan, out, title=args.title, category=args.category,
                  category_no=args.category_no, date=date, watermark=not args.no_watermark)
    print(f"사진 {meta['images']['count']}장, 영상 {len(meta['videos'])}개 -> {out}")


def cmd_check(args) -> None:
    md = pathlib.Path(args.script).read_text(encoding="utf-8")
    problems = check_captions(md)
    for line_no, msg in problems:
        print(f"{args.script}:{line_no}  {msg}")
    print(f"문제 {len(problems)}건")
    if problems:
        sys.exit(1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="편 폴더를 훑어 plan.json을 만든다")
    p.add_argument("ep_folder")
    p.add_argument("--out", required=True)
    p.add_argument("--originals")
    p.add_argument("--threshold", type=float, default=0.10)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("sheet", help="plan.json의 콘택트 시트를 만든다")
    p.add_argument("work_dir")
    p.set_defaults(func=cmd_sheet)

    p = sub.add_parser("render", help="plan.json대로 초안 폴더를 만든다")
    p.add_argument("work_dir")
    p.add_argument("--out", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--category", default="젤다무쌍 봉인전기")
    p.add_argument("--category-no", type=int, default=None)
    p.add_argument("--date", default=None)
    p.add_argument("--no-watermark", action="store_true")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("check", help="script.md의 캡션 마침표와 빈 표식을 검사한다")
    p.add_argument("script")
    p.set_defaults(func=cmd_check)

    args = ap.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
