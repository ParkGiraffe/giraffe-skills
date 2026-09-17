# -*- coding: utf-8 -*-
"""텍스트 레이어가 있는 PDF를 EPUB 3으로 바꿉니다.
본문 글자 크기를 기준으로 각주를 갈라내고, 줄 앞 공백으로 문단을 되살립니다.
사용법: python3 pdf2epub.py <입력.pdf> <출력.epub> [제목]
"""
import fitz, os, re, sys, zipfile, html, json
from collections import Counter

CHAP = re.compile(r"^\s*([a-zA-Z]?\d+(?:\.\d+)?)\.\s*(\S.{0,70})$")
NAMED = re.compile(r"^\s*(interlude|prologue|epilogue|prologue|에필로그|프롤로그|종장|서장)\b.*", re.I)


def body_size(doc, limit=60):
    c = Counter()
    for i in range(min(limit, doc.page_count)):
        for b in doc[i].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    if s["text"].strip():
                        c[round(s["size"], 1)] += len(s["text"].strip())
    return c.most_common(1)[0][0] if c else 16.0


def page_lines(page, bsize):
    """(본문줄들, 각주줄들)을 돌려줍니다. 각 줄은 (원시텍스트, HTML)입니다."""
    body, notes = [], []
    small = bsize * 0.72
    for b in page.get_text("dict")["blocks"]:
        if not b.get("lines"):
            continue
        for l in b["lines"]:
            spans = [s for s in l["spans"] if s["text"].strip() or s["text"] == " "]
            if not spans:
                continue
            has_body = any(s["size"] > small for s in spans)
            raw = "".join(s["text"] for s in spans)
            if not raw.strip():
                continue
            if has_body:
                parts = []
                for s in spans:
                    t = html.escape(s["text"])
                    parts.append(f"<sup>{t.strip()}</sup>" if s["size"] <= small and t.strip() else t)
                body.append((raw, "".join(parts)))
            else:
                notes.append((raw, html.escape(raw.strip())))
    return body, notes


def build_paragraphs(lines):
    """줄 앞 공백을 새 문단 신호로 삼아 문단을 되살립니다."""
    paras = []
    cur_raw, cur_html = "", ""
    for raw, h in lines:
        newpara = (not cur_raw) or raw[:1].isspace()
        if newpara:
            if cur_raw.strip():
                paras.append((cur_raw.strip(), cur_html.strip()))
            cur_raw, cur_html = raw, h
        else:
            cur_raw += raw
            cur_html += h
    if cur_raw.strip():
        paras.append((cur_raw.strip(), cur_html.strip()))
    return paras


CSS = """@charset "utf-8";
html, body { margin:0; padding:0; }
body { font-family: serif; line-height:1.75; padding: 0 1em; }
h1 { font-size:1.35em; margin: 2.5em 0 1.6em; line-height:1.5; text-align:left;
     page-break-before: always; break-before: page; }
p { margin:0; text-indent:1em; text-align:justify; }
p.noindent { text-indent:0; }
sup { font-size:0.6em; vertical-align:super; }
div.illus { margin:1.5em 0; text-align:center; page-break-before: always; break-before: page; }
div.illus img { max-width:100%; height:auto; }
hr.sep { border:0; border-top:1px solid #bbb; width:30%; margin:2em auto; }
aside.notes { margin-top:2.5em; padding-top:.8em; border-top:1px solid #ccc;
              font-size:.82em; color:#444; }
aside.notes p { text-indent:0; margin:.3em 0; }
"""


def convert(src, dst, title=None):
    doc = fitz.open(src)
    bsize = body_size(doc)
    title = title or os.path.splitext(os.path.basename(dst))[0]

    chapters = []            # {"title":.., "html":[..], "notes":[..]}
    images = []              # (파일명, 바이트)

    def new_chapter(t):
        chapters.append({"title": t, "html": [], "notes": []})

    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        imgs = page.get_images(full=True)
        # 삽화 쪽
        if imgs and len(text) < 30:
            try:
                info = doc.extract_image(imgs[0][0])
            except Exception:
                continue
            fn = f"img{len(images):03d}.{info['ext']}"
            images.append((fn, info["image"]))
            if not chapters:
                new_chapter("삽화")
            chapters[-1]["html"].append(
                f'<div class="illus"><img src="{fn}" alt=""/></div>')
            continue
        if not text:
            continue
        blines, nlines = page_lines(page, bsize)
        paras = build_paragraphs(blines)
        if not paras:
            continue
        # 장 제목 판정: 쪽의 첫 문단이 "3. 제목" 또는 interlude 꼴일 때
        first = paras[0][0]
        m = CHAP.match(first) or NAMED.match(first)
        if m:
            heading = " ".join(first.split())
            new_chapter(heading)
            chapters[-1]["html"].append(f"<h1>{html.escape(heading)}</h1>")
            paras = paras[1:]
        elif not chapters:
            new_chapter("시작")
        for raw, h in paras:
            cls = ""
            if raw.startswith(("“", "\"", "「", "『", "─", "―")):
                cls = ' class="noindent"'
            h = h.strip()
            if set(h) <= set("×✕xX  ") and 1 <= len(h) <= 8:
                chapters[-1]["html"].append('<hr class="sep"/>')
            else:
                chapters[-1]["html"].append(f"<p{cls}>{h}</p>")
        for raw, h in nlines:
            chapters[-1]["notes"].append(f"<p>{h}</p>")

    doc.close()
    if not chapters:
        raise SystemExit("변환할 내용이 없습니다: " + src)

    # EPUB 조립
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    uid = "urn:uuid:" + re.sub(r"[^0-9a-f]", "", hex(abs(hash(title)))[2:].ljust(32, "0"))[:32]
    nav_items, manifest, spine = [], [], []
    with zipfile.ZipFile(dst, "w") as z:
        z.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/style.css", CSS)
        for fn, data in images:
            z.writestr("OEBPS/" + fn, data)
            ext = fn.rsplit(".", 1)[1].lower()
            mt = {"jpeg": "image/jpeg", "jpg": "image/jpeg", "png": "image/png",
                  "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")
            manifest.append(f'<item id="{fn.replace(".","_")}" href="{fn}" media-type="{mt}"/>')
        for n, ch in enumerate(chapters):
            fn = f"ch{n:03d}.xhtml"
            body = "\n".join(ch["html"])
            if ch["notes"]:
                body += '\n<aside class="notes" epub:type="footnotes">\n' + "\n".join(ch["notes"]) + "\n</aside>"
            z.writestr("OEBPS/" + fn,
                       '<?xml version="1.0" encoding="utf-8"?>\n'
                       '<!DOCTYPE html>\n'
                       '<html xmlns="http://www.w3.org/1999/xhtml" '
                       'xmlns:epub="http://www.idpf.org/2007/ops" lang="ko" xml:lang="ko">\n'
                       f'<head><meta charset="utf-8"/><title>{html.escape(ch["title"])}</title>'
                       '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
                       f'<body>\n{body}\n</body></html>')
            manifest.append(f'<item id="ch{n:03d}" href="{fn}" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="ch{n:03d}"/>')
            nav_items.append(f'<li><a href="{fn}">{html.escape(ch["title"])}</a></li>')
        z.writestr("OEBPS/nav.xhtml",
                   '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
                   '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
                   'lang="ko" xml:lang="ko"><head><meta charset="utf-8"/><title>목차</title></head>'
                   '<body><nav epub:type="toc" id="toc"><h1>목차</h1><ol>'
                   + "\n".join(nav_items) + '</ol></nav></body></html>')
        manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
        manifest.append('<item id="css" href="style.css" media-type="text/css"/>')
        z.writestr("OEBPS/content.opf",
                   '<?xml version="1.0" encoding="utf-8"?>\n'
                   '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">\n'
                   '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
                   f'<dc:identifier id="bookid">{uid}</dc:identifier>\n'
                   f'<dc:title>{html.escape(title)}</dc:title>\n'
                   '<dc:language>ko</dc:language>\n'
                   '</metadata>\n<manifest>\n' + "\n".join(manifest) +
                   '\n</manifest>\n<spine>\n' + "\n".join(spine) + '\n</spine>\n</package>')

    chars = sum(len(re.sub(r"<[^>]+>", "", h)) for ch in chapters for h in ch["html"])
    return {"epub": os.path.basename(dst), "장": len(chapters), "삽화": len(images),
            "글자": chars, "MB": round(os.path.getsize(dst) / 1e6, 2)}


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    t = sys.argv[3] if len(sys.argv) > 3 else None
    print(json.dumps(convert(src, dst, t), ensure_ascii=False))
