# -*- coding: utf-8 -*-
"""폴더 안 PDF들이 OCR이 되어 있는지, 스캔 해상도는 어떤지 조사합니다.
사용법: python3 scan_pdfs.py <폴더 또는 파일> [...]
"""
import fitz, os, sys, unicodedata as ud


def is_pdf(name):
    b = os.path.basename(name)
    # 맥에서 복제하면 "책.pdf의 사본"처럼 확장자 뒤에 말이 붙습니다
    return not b.startswith("._") and ".pdf" in ud.normalize("NFC", b).lower() \
        and not b.endswith(".part")


def collect(paths):
    out = []
    for p in paths:
        if os.path.isfile(p):
            if is_pdf(p):
                out.append(p)
            continue
        for dp, dn, fn in os.walk(p):
            dn[:] = [d for d in dn if not d.startswith(".")]
            for f in sorted(fn):
                if is_pdf(f):
                    out.append(os.path.join(dp, f))
    return out


def probe(path, samples=12):
    d = fitz.open(path)
    n = d.page_count
    idx = sorted(set(int(i * (n - 1) / (samples - 1)) for i in range(samples))) if n > 1 else [0]
    text_pages = chars = img_pages = 0
    widths = []
    for i in idx:
        pg = d[i]
        t = pg.get_text("text").strip()
        chars += len(t)
        if len(t) > 40:
            text_pages += 1
        imgs = pg.get_images(full=True)
        if imgs:
            img_pages += 1
            try:
                info = d.extract_image(imgs[0][0])
                widths.append(info["width"])
            except Exception:
                pass
    meta = d.metadata or {}
    gen = ((meta.get("producer") or "") + " " + (meta.get("creator") or "")).strip()
    d.close()
    ratio = text_pages / len(idx)
    kind = "텍스트 PDF" if ratio >= 0.7 else ("일부만 텍스트" if ratio > 0.2 else "OCR 없음")
    return {"path": path, "쪽": n, "표본": len(idx), "텍스트쪽": text_pages,
            "글자": chars, "그림쪽": img_pages,
            "폭중앙값": sorted(widths)[len(widths) // 2] if widths else 0,
            "판정": kind, "생성기": gen[:46]}


def main():
    paths = sys.argv[1:] or ["."]
    files = collect(paths)
    if not files:
        print("PDF를 찾지 못했습니다.")
        return
    rows = []
    for f in files:
        try:
            rows.append(probe(f))
        except Exception as e:
            print(f"[열기 실패] {os.path.basename(f)}: {type(e).__name__}")
    rows.sort(key=lambda r: (r["판정"] != "OCR 없음", r["path"]))
    print(f"{'파일':<52}{'쪽':>5}{'글자':>8}{'그림폭':>7}  {'판정':<12}생성기")
    print("-" * 118)
    for r in rows:
        name = ud.normalize("NFC", os.path.basename(r["path"]))
        print(f"{name[:50]:<52}{r['쪽']:>5}{r['글자']:>8}{r['폭중앙값']:>7}  {r['판정']:<12}{r['생성기']}")
    need = [r for r in rows if r["판정"] != "텍스트 PDF"]
    print(f"\n전체 {len(rows)}개 중 OCR이 필요한 것 {len(need)}개, "
          f"총 {sum(r['쪽'] for r in need):,}쪽")
    low = [r for r in need if 0 < r["폭중앙값"] < 900]
    if low:
        print(f"해상도가 낮아 인식률이 떨어질 것 {len(low)}개:")
        for r in low:
            print(f"  - {ud.normalize('NFC', os.path.basename(r['path']))[:60]} (그림 폭 {r['폭중앙값']}px)")


if __name__ == "__main__":
    main()
