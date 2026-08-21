#!/usr/bin/env python3
"""가림이 씌워진 자리를 전수로 찾아 눈으로 판별하고, 사람이 아닌 곳만 되돌린다.

YuNet은 리콜 우선이라 조각상·명화·모자이크·지폐 인물·자동차 바퀴처럼 "얼굴처럼 생긴 것"에도
원을 씌운다. 여행 사진이나 미술관 사진에서 특히 많이 나온다. 사람 얼굴만 남기고 나머지를
되돌리려면 어디에 무엇을 씌웠는지 먼저 봐야 한다.

원본과 가림본을 픽셀로 비교해 실제로 바뀐 회색 원만 골라내고, 그 자리를 원본에서 잘라
인덱스 시트로 만든다. 사람이 아닌 번호를 골라 restore로 넘기면 그 자리만 원본 픽셀로
되돌린다. 사진 전체를 되돌리지 않으므로 같은 사진 안의 진짜 얼굴 가림은 그대로 남는다.

  scan    원본 vs 가림본 diff -> masks.json
  sheet   masks.json -> sheets/mask_NN.jpg + mask_index.json (판별용)
  restore 번호를 받아 그 자리만 원본 픽셀로 되돌림

사용:
  review_masks.py scan    <원본폴더> <가림폴더> [--out masks.json]
  review_masks.py sheet   <원본폴더> [--masks masks.json] [--out-dir sheets]
  review_masks.py restore <원본폴더> <가림폴더> --nums 2,36,52,76

되돌리기 전에 가림 폴더를 복사해 두면 안전하다.
"""
import argparse, collections, json, pathlib, math, sys
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageOps

GRAY = 150          # anonymize.py의 기본 회색
TOL = 8
MIN_AREA = 80
PAD = 2             # 되돌릴 때 경계 여유


def load_bgr(p):
    """EXIF 회전을 픽셀로 반영해 읽는다. 가림본은 이미 회전 반영본이라 맞춰야 좌표가 맞는다."""
    return np.asarray(ImageOps.exif_transpose(Image.open(p)).convert("RGB"))[:, :, ::-1]


def cmd_scan(a):
    orig, anon = pathlib.Path(a.orig), pathlib.Path(a.anon)
    out, total, skipped = {}, 0, []
    for ap in sorted(anon.rglob("*.jpg")):
        key = f"{ap.parent.name}/{ap.name}"
        op = orig / key
        if not op.exists():
            continue
        A, O = load_bgr(ap), load_bgr(op)
        if A.shape != O.shape:
            skipped.append(key)
            continue
        # 회색이면서 원본과 실제로 달라진 픽셀만. 사진에 원래 있던 회색 벽·하늘을 거른다.
        m = ((np.abs(A.astype(int) - GRAY).max(axis=2) <= TOL) &
             (np.abs(A.astype(int) - O.astype(int)).max(axis=2) > 40)).astype(np.uint8)
        if m.sum() < MIN_AREA:
            continue
        n, _, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        found = []
        for i in range(1, n):
            x, y, w, h, ar = stats[i]
            if ar < MIN_AREA:
                continue
            # 원이라 채움률 pi/4 언저리, 가로세로비 1 언저리
            if ar / max(1, w * h) < 0.55 or not (0.7 <= w / max(1, h) <= 1.4):
                continue
            found.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
        if found:
            out[key] = found
            total += len(found)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"가림 있는 사진 {len(out)}장 / 가림 {total}곳 -> {a.out}")
    if skipped:
        print(f"크기 불일치로 건너뜀 {len(skipped)}장 (EXIF 회전이 다른 경우)")
    print("폴더별:", dict(sorted(collections.Counter(k.split('/')[0] for k in out).items())))


def cmd_sheet(a):
    src = pathlib.Path(a.orig)
    data = json.load(open(a.masks))
    items = [(k, j, m) for k, ms in sorted(data.items()) for j, m in enumerate(ms)]
    print("가림", len(items), "곳")
    out_dir = pathlib.Path(a.out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    CELL, COLS, ROWS, LABEL = 200, 6, 5, 18
    per, idx = COLS * ROWS, []
    for s in range(math.ceil(len(items) / per)):
        chunk = items[s * per:(s + 1) * per]
        canvas = Image.new("RGB", (COLS * CELL, ROWS * (CELL + LABEL)), (22, 22, 22))
        d = ImageDraw.Draw(canvas)
        for k, (key, j, m) in enumerate(chunk):
            n = s * per + k + 1
            idx.append({"n": n, "file": key, **m})
            r, c = divmod(k, COLS)
            x, y = c * CELL, r * (CELL + LABEL)
            try:
                im = ImageOps.exif_transpose(Image.open(src / key)).convert("RGB")
                cx, cy = m["x"] + m["w"] / 2, m["y"] + m["h"] / 2
                half = max(m["w"], m["h"]) * 1.9 / 2
                crop = im.crop((int(max(0, cx - half)), int(max(0, cy - half)),
                                int(min(im.width, cx + half)), int(min(im.height, cy + half))))
                crop.thumbnail((CELL - 6, CELL - 6), Image.LANCZOS)
                canvas.paste(crop, (x + (CELL - crop.width) // 2,
                                    y + LABEL + (CELL - LABEL - crop.height) // 2))
            except Exception as e:
                d.text((x + 6, y + LABEL + 20), f"ERR {e}"[:24], fill=(255, 90, 90))
            d.text((x + 5, y + 3), f'{n}  {key.split("/")[-1][:12]}', fill=(255, 220, 120))
        p = out_dir / f"mask_{s+1:02d}.jpg"
        canvas.save(p, quality=90)
        print("만듦:", p, len(chunk), "곳")
    json.dump(idx, open("mask_index.json", "w"), ensure_ascii=False, indent=1)
    print("번호표: mask_index.json")


def cmd_restore(a):
    orig, anon = pathlib.Path(a.orig), pathlib.Path(a.anon)
    idx = {d["n"]: d for d in json.load(open(a.index))}
    nums = [int(x) for x in a.nums.replace(" ", "").split(",") if x]
    byfile = collections.defaultdict(list)
    for n in nums:
        if n not in idx:
            sys.exit(f"번호 {n}이 {a.index}에 없음")
        byfile[idx[n]["file"]].append(idx[n])

    for key, ms in sorted(byfile.items()):
        ap, op = anon / key, orig / key
        im = Image.open(ap).convert("RGB")
        src = ImageOps.exif_transpose(Image.open(op)).convert("RGB")
        if src.size != im.size:
            print(f"  [건너뜀] 크기 불일치 {key}")
            continue
        for m in ms:
            box = (max(0, m["x"] - PAD), max(0, m["y"] - PAD),
                   min(im.width, m["x"] + m["w"] + PAD),
                   min(im.height, m["y"] + m["h"] + PAD))
            im.paste(src.crop(box), box[:2])
        im.save(ap, quality=95, subsampling=0)
        print(f"  {key}: {len(ms)}곳 되돌림")
    print(f"\n사진 {len(byfile)}장 / 가림 {len(nums)}곳 되돌림")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan"); s.add_argument("orig"); s.add_argument("anon")
    s.add_argument("--out", default="masks.json"); s.set_defaults(f=cmd_scan)

    s = sub.add_parser("sheet"); s.add_argument("orig")
    s.add_argument("--masks", default="masks.json"); s.add_argument("--out-dir", default="sheets")
    s.set_defaults(f=cmd_sheet)

    s = sub.add_parser("restore"); s.add_argument("orig"); s.add_argument("anon")
    s.add_argument("--nums", required=True); s.add_argument("--index", default="mask_index.json")
    s.set_defaults(f=cmd_restore)

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
