#!/usr/bin/env python3
"""사진 폴더를 촬영 시각순으로 줄 세워 번호를 붙이고 워터마크를 넣는다. 영상은 movies/로 옮긴다.

카톡으로 받은 사진, 스크린샷, 직접 찍은 사진이 한 폴더에 섞여 있을 때 쓴다.
파일명 순서로는 섞이지 않는다(카톡 사진은 받은 시각이 이름이라 전부 뒤로 몰린다).
그래서 사진마다 '찍은 시각'을 아래 순서로 찾는다.

  1. EXIF DateTimeOriginal. 카톡으로 받은 사진도 원본 EXIF가 남아 있는 경우가 많다
     (2026-09-21 포켓몬 고풍상점 38장 전부 남아 있었다).
  2. 파일명 속 시각: 20260921_112814, Screenshot_20260921_113111_..., IMG_2026-09-21-121534xx,
     KakaoTalk_20260921_121534123 등.
  3. 여기까지 없으면 '추정'으로 표시한다. 카톡 13자리 숫자 이름(1789984814621)은 받은 시각이라
     찍은 시각이 아니다. 수정 시각도 복사할 때 바뀐다. 둘 다 추정으로만 쓰고 보고서에 따로 적는다.

사용:
  organize.py <폴더> --dry-run       순서만 보고 (파일은 안 건드림)
  organize.py <폴더>                  movies/로 영상 이동 + watermark/에 NNN_ 번호 붙인 워터마크본
옵션:
  --out watermark   출력 폴더 이름
  --movies movies   영상 폴더 이름
  --no-watermark    번호만 붙여 복사

폴더 바로 아래 파일만 본다. '얼굴가리기' 같은 하위 작업 폴더에는 가리기 전 원본이 있을 수 있어
섞으면 안 된다. 얼굴을 가려야 하면 이 스크립트 전에 face-anonymizer로 가린 사진을 폴더 바로
아래에 둔다.
"""
import argparse
import datetime as dt
import os
import pathlib
import re
import shutil
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_lib"))

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".3gp", ".mkv"}

# (정규식, 설명). 앞에서부터 먼저 맞는 것을 쓴다.
_NAME_PATTERNS = [
    # 20260921_112814 / Screenshot_20260921_113111_앱 / KakaoTalk_20260921_121534123 / PXL_20260921_121534
    (re.compile(r"(20\d{2})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})"), "파일명"),
    # IMG_2026-09-21-12153467 / 2026-09-21 12.15.34 / 2026-09-21-121534
    (re.compile(r"(20\d{2})-(\d{2})-(\d{2})[ _-](\d{2})[.:]?(\d{2})[.:]?(\d{2})"), "파일명"),
]
_KAKAO_MS = re.compile(r"^(1\d{12})(?:\D|$)")


def kind_of(name):
    n = name.lower()
    if n.startswith("screenshot") or "스크린샷" in name:
        return "스크린샷"
    if _KAKAO_MS.match(name) or n.startswith("kakaotalk"):
        return "카톡"
    if re.match(r"^(20\d{6}_\d{6}|img_\d{8}_|pxl_|dsc|img_\d{4})", n):
        return "카메라"
    return "기타"


def exif_time(path):
    try:
        e = Image.open(path).getexif()
        v = e.get_ifd(0x8769).get(36867) or e.get(306)
        if v:
            return dt.datetime.strptime(str(v).strip()[:19], "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def name_time(name):
    for rx, _ in _NAME_PATTERNS:
        m = rx.search(name)
        if m:
            try:
                return dt.datetime(*map(int, m.groups()))
            except ValueError:
                continue
    return None


def capture_time(path):
    """(시각, 근거). 근거가 '추정:'으로 시작하면 찍은 시각이 아닐 수 있다."""
    t = exif_time(path)
    if t:
        return t, "EXIF"
    name = os.path.basename(path)
    t = name_time(name)
    if t:
        return t, "파일명"
    m = _KAKAO_MS.match(name)
    if m:
        return dt.datetime.fromtimestamp(int(m.group(1)) / 1000), "추정:카톡 받은 시각"
    return dt.datetime.fromtimestamp(os.path.getmtime(path)), "추정:수정 시각"


def plan(folder):
    """폴더 바로 아래 사진을 촬영 시각순으로. [{name, time, source, kind}], 영상 목록, 하위 폴더 목록."""
    photos, videos, subdirs = [], [], []
    for n in sorted(os.listdir(folder)):
        if n.startswith("."):
            continue
        p = os.path.join(folder, n)
        if os.path.isdir(p):
            subdirs.append(n)
            continue
        ext = os.path.splitext(n)[1].lower()
        if ext in VIDEO_EXTS:
            videos.append(n)
        elif ext in IMAGE_EXTS:
            t, src = capture_time(p)
            photos.append({"name": n, "time": t, "source": src, "kind": kind_of(n)})
    photos.sort(key=lambda r: (r["time"], r["name"]))
    return photos, videos, subdirs


def runs(photos):
    """같은 종류가 이어지는 구간 [(종류, 장수, 첫 시각, 끝 시각)]."""
    out = []
    for r in photos:
        if out and out[-1][0] == r["kind"]:
            out[-1][1] += 1
            out[-1][3] = r["time"]
        else:
            out.append([r["kind"], 1, r["time"], r["time"]])
    return out


def numbered(photos):
    width = max(3, len(str(len(photos))))
    return [(r["name"], f"{i:0{width}d}_{r['name']}") for i, r in enumerate(photos, 1)]


def report(photos, videos, subdirs):
    kinds = {}
    for r in photos:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"사진 {len(photos)}장 ({', '.join(f'{k} {v}' for k, v in kinds.items())}) / 영상 {len(videos)}개")
    if subdirs:
        print(f"하위 폴더는 보지 않음: {', '.join(subdirs)}")
    print("\n시간순 구간:")
    for k, n, a, b in runs(photos):
        print(f"  {a:%H:%M:%S}~{b:%H:%M:%S}  {k} {n}장")
    guessed = [r for r in photos if r["source"].startswith("추정")]
    if guessed:
        print(f"\n찍은 시각을 모르는 사진 {len(guessed)}장 (자리를 사람이 확인할 것):")
        for r in guessed:
            print(f"  {r['time']:%Y-%m-%d %H:%M:%S}  {r['name']}  ({r['source']})")


def move_with_sidecar(src_dir, name, dst_dir):
    """파일과 macOS '._' 짝 파일을 함께 옮긴다. 같은 이름이 이미 있으면 멈춘다."""
    dst = os.path.join(dst_dir, name)
    if os.path.exists(dst):
        raise SystemExit(f"ABORT: {dst}가 이미 있음")
    shutil.move(os.path.join(src_dir, name), dst)
    side = os.path.join(src_dir, "._" + name)
    if os.path.exists(side):
        shutil.move(side, os.path.join(dst_dir, "._" + name))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="watermark")
    ap.add_argument("--movies", default="movies")
    ap.add_argument("--no-watermark", action="store_true")
    a = ap.parse_args()

    folder = os.path.abspath(a.folder)
    photos, videos, subdirs = plan(folder)
    if not photos and not videos:
        sys.exit("사진·영상이 없음")
    report(photos, videos, [d for d in subdirs if d not in (a.out, a.movies)])
    if a.dry_run:
        return

    out = os.path.join(folder, a.out)
    if os.path.isdir(out) and any(not n.startswith(".") for n in os.listdir(out)):
        sys.exit(f"ABORT: {out}가 비어 있지 않음. 이전 결과와 섞이지 않도록 지우거나 --out으로 다른 이름을 줄 것")
    os.makedirs(out, exist_ok=True)

    if videos:
        mv = os.path.join(folder, a.movies)
        os.makedirs(mv, exist_ok=True)
        for n in videos:
            move_with_sidecar(folder, n, mv)
        print(f"\n영상 {len(videos)}개 -> {mv}")

    import watermark as W
    pairs = numbered(photos)
    for src, dst in pairs:
        sp, dp = os.path.join(folder, src), os.path.join(out, dst)
        if a.no_watermark or src.lower().endswith(".gif"):
            shutil.copy2(sp, dp)
            continue
        im = Image.open(sp)
        W.stamp(im).save(dp, quality=95, subsampling=0, exif=W.exif_bytes(im))
    with open(os.path.join(folder, ".photo_order.tsv"), "w", encoding="utf-8") as f:
        for (src, dst), r in zip(pairs, photos):
            f.write(f"{dst}\t{src}\t{r['time']:%Y-%m-%d %H:%M:%S}\t{r['source']}\t{r['kind']}\n")
    print(f"\n{'복사' if a.no_watermark else '워터마크'} {len(pairs)}장 -> {out}")
    print(f"순서표: {os.path.join(folder, '.photo_order.tsv')}")


if __name__ == "__main__":
    main()
