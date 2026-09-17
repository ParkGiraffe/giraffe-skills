# -*- coding: utf-8 -*-
"""원본 PDF의 그림은 그대로 두고 보이지 않는 텍스트 층만 얹습니다.
인식은 macOS Vision(ko-KR)을 씁니다.
사용법: python3 ocr_pdf.py <입력.pdf> <출력.pdf> [--dpi 300] [--batch 24]
"""
import fitz, os, sys, json, subprocess, tempfile, shutil, time

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
VISION = os.path.join(SCRIPTS, "visionocr")


def ensure_vision():
    """Vision 도우미가 없거나 소스보다 오래됐으면 다시 빌드합니다."""
    src = os.path.join(SCRIPTS, "visionocr.swift")
    if os.path.exists(VISION) and os.path.getmtime(VISION) >= os.path.getmtime(src):
        return
    r = subprocess.run(["swiftc", "-O", src, "-o", VISION], capture_output=True)
    if r.returncode != 0:
        raise SystemExit("visionocr 빌드 실패. Xcode 명령행 도구가 필요합니다.\n"
                         + r.stderr.decode("utf-8", "replace")[:800])
MAX_PX = 4000          # 너무 큰 그림은 이 폭/높이로 줄여 인식합니다
RENDER_DPI = 300


def page_image(doc, page, tmpdir, idx):
    """페이지의 배경 그림을 파일로 꺼내고 (경로, 그림이 놓인 사각형)을 돌려줍니다."""
    imgs = page.get_images(full=True)
    prect = page.rect
    if len(imgs) == 1:
        xref = imgs[0][0]
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            rects = []
        if rects:
            r = rects[0]
            # 그림이 페이지의 대부분을 덮을 때만 원본 그대로 씁니다
            if r.width * r.height >= prect.width * prect.height * 0.6:
                info = doc.extract_image(xref)
                if max(info["width"], info["height"]) <= MAX_PX:
                    p = os.path.join(tmpdir, f"p{idx:05d}.{info['ext']}")
                    with open(p, "wb") as fh:
                        fh.write(info["image"])
                    return p, r
    # 그 밖에는 페이지를 직접 그립니다
    zoom = RENDER_DPI / 72.0
    scale = min(1.0, MAX_PX / max(prect.width * zoom, prect.height * zoom))
    pm = page.get_pixmap(matrix=fitz.Matrix(zoom * scale, zoom * scale), alpha=False)
    p = os.path.join(tmpdir, f"p{idx:05d}.png")
    pm.save(p)
    return p, prect


def run_vision(paths, batch=24):
    out = {}
    for i in range(0, len(paths), batch):
        chunk = paths[i:i + batch]
        try:
            r = subprocess.run([VISION] + chunk, capture_output=True, timeout=600)
        except subprocess.TimeoutExpired:
            continue
        for line in r.stdout.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            out[d["path"]] = d
    return out


def inject(page, rect, vis):
    """Vision 결과를 페이지에 보이지 않는 텍스트로 심습니다."""
    iw, ih = vis["w"], vis["h"]
    if not iw or not ih:
        return 0
    sx = rect.width / iw
    sy = rect.height / ih
    n = 0
    for ln in vis["lines"]:
        t = ln["t"].strip()
        if not t:
            continue
        x = rect.x0 + ln["x"] * sx
        y = rect.y0 + ln["y"] * sy
        w = ln["w"] * sx
        h = ln["h"] * sy
        if h <= 0.5 or w <= 0.5:
            continue
        # 글상자 너비에 맞춰 크기를 정합니다. 넘치면 추출 때 잘립니다.
        ref = fitz.get_text_length(t, fontname="korea", fontsize=10.0)
        size = (10.0 * w / ref) if ref > 0 else h * 0.82
        size = max(0.6, min(size, h * 1.6))
        baseline = y + h * 0.82
        try:
            page.insert_text(
                fitz.Point(x, baseline), t,
                fontname="korea", fontsize=size,
                render_mode=3,          # 보이지 않음
                overlay=True,
            )
            n += 1
        except Exception:
            continue
    return n


def main():
    src, dst = sys.argv[1], sys.argv[2]
    ensure_vision()
    t0 = time.time()
    doc = fitz.open(src)
    tmpdir = tempfile.mkdtemp(prefix="ocrpage_")
    try:
        metas = []
        for i, page in enumerate(doc):
            if len(page.get_text("text").strip()) > 40:
                metas.append(None)          # 이미 텍스트가 있는 쪽은 건너뜁니다
                continue
            metas.append(page_image(doc, page, tmpdir, i))
        paths = [m[0] for m in metas if m]
        vis = run_vision(paths)
        total_lines = 0
        ocr_pages = 0
        for i, m in enumerate(metas):
            if not m:
                continue
            p, rect = m
            v = vis.get(p)
            if not v or not v["lines"]:
                continue
            c = inject(doc[i], rect, v)
            if c:
                ocr_pages += 1
                total_lines += c
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        doc.save(dst, garbage=3, deflate=True)
        doc.close()
        # 검증: 결과에서 텍스트가 실제로 뽑히는지 확인합니다
        chk = fitz.open(dst)
        got = sum(1 for pg in chk if len(pg.get_text("text").strip()) > 40)
        chars = sum(len(pg.get_text("text")) for pg in chk)
        chk.close()
        print(json.dumps({
            "src": os.path.basename(src), "쪽": len(metas), "OCR한쪽": ocr_pages,
            "심은줄": total_lines, "텍스트있는쪽": got, "총글자": chars,
            "초": round(time.time() - t0, 1),
            "MB": round(os.path.getsize(dst) / 1e6, 1),
        }, ensure_ascii=False))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
