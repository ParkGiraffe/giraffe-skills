# -*- coding: utf-8 -*-
"""이미지가 든 zip(스캔 아카이브)을 PDF 한 권으로 묶습니다.
원본 JPEG을 다시 압축하지 않고 그대로 넣습니다.
사용법: python3 zip2pdf.py <입력.zip> <출력.pdf> [--height 800]
"""
import fitz, io, os, re, sys, zipfile

IMG = re.compile(r"\.(jpe?g|png)$", re.I)


def natural(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def convert(src, dst, page_h=800.0):
    z = zipfile.ZipFile(src)
    names = sorted((n for n in z.namelist()
                    if IMG.search(n) and not os.path.basename(n).startswith((".", "._"))),
                   key=natural)
    if not names:
        raise SystemExit("zip 안에 이미지가 없습니다: " + src)
    doc = fitz.open()
    skipped = 0
    for n in names:
        data = z.read(n)
        try:
            img = fitz.open(stream=data, filetype=os.path.splitext(n)[1][1:])
            w, h = img[0].rect.width, img[0].rect.height
            img.close()
        except Exception:
            skipped += 1
            continue
        if not w or not h:
            skipped += 1
            continue
        pw = page_h * w / h
        page = doc.new_page(width=pw, height=page_h)
        page.insert_image(page.rect, stream=data)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    doc.save(dst, deflate=True)
    n_pages = doc.page_count
    doc.close()
    return {"zip": os.path.basename(src), "쪽": n_pages, "건너뜀": skipped,
            "MB": round(os.path.getsize(dst) / 1e6, 1)}


if __name__ == "__main__":
    h = 800.0
    if "--height" in sys.argv:
        h = float(sys.argv[sys.argv.index("--height") + 1])
    import json
    print(json.dumps(convert(sys.argv[1], sys.argv[2], h), ensure_ascii=False))
