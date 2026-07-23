#!/usr/bin/env python3
"""Convert blog draft markdown → Naver SmartEditor-compatible HTML.

The output is designed to be opened in a browser, selected (Ctrl+A), and
pasted into the Naver blog editor. Naver's editor recognizes its own
se-component class structure and rebuilds the post; pasted <img> tags are
re-uploaded server-side.

Usage: md_to_smarteditor.py <in.md> <out.html> [--images <dir>] [--title <str>]
"""
import sys, re, html, pathlib, uuid, json, argparse, base64, mimetypes, base64, mimetypes


def uid() -> str:
    return f"SE-{uuid.uuid4()}"


def esc(s: str) -> str:
    return html.escape(s, quote=False)


# ---------- component builders ----------

INLINE_CODE_RE = re.compile(r"`([^`]+)`")
INLINE_CODE_STYLE = (
    "font-size:14px;background-color:#f2f3f5;color:#d6336c;"
    "border-radius:3px;padding:1px 4px;"
)


def render_inline(text: str) -> str:
    out, pos = [], 0
    for m in INLINE_CODE_RE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        out.append(f'<span style="{INLINE_CODE_STYLE}">{esc(m.group(1))}</span>')
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


def text_component(text: str, *, heading: bool = False, subheading: bool = False,
                   bold: bool = False, align: str = "") -> str:
    cid = uid()
    pid = uid()
    sid = uid()
    # 장 제목(##)=fs24, 절 제목(전체 라인 볼드)=fs19, 평문=크기 없음
    fs = "fs24" if heading else ("fs19" if subheading else "")
    inner = f"<b>{render_inline(text)}</b>" if (heading or subheading or bold) else render_inline(text)
    return f'''<div class="se-component se-text se-l-default" id="{cid}">
<div class="se-component-content">
<div class="se-section se-section-text se-l-default">
<div class="se-module se-module-text">
<p class="se-text-paragraph se-text-paragraph-align-{align} " id="{pid}"><span class="se-fs-{fs} se-ff-" id="{sid}">{inner}</span></p>
</div></div></div></div>'''


def horizontal_line() -> str:
    cid = uid()
    return f'''<div class="se-component se-horizontalLine se-l-line3" id="{cid}">
<div class="se-component-content">
<div class="se-section se-section-horizontalLine se-l-line3 se-section-align-center">
<div class="se-module se-module-horizontalLine"><hr class="se-hr" /></div>
</div></div></div>'''


def image_component(src: str, alt: str = "") -> str:
    cid = uid()
    return f'''<div class="se-component se-image se-l-default" id="{cid}">
<div class="se-component-content se-component-content-fit">
<div class="se-section se-section-image se-l-default se-section-align-center">
<div class="se-module se-module-image">
<img src="{esc(src)}" alt="{esc(alt)}" class="se-image-resource" />
</div></div></div></div>'''


def placeholder_component(label: str) -> str:
    return text_component(f"[스크린샷: {label}]", heading=False, align="center")


def quote_component(text: str) -> str:
    cid = uid()
    return f'''<div class="se-component se-quotation se-l-default" id="{cid}">
<div class="se-component-content">
<div class="se-section se-section-quotation se-l-default">
<div class="se-module se-module-text">
<blockquote><p>{esc(text)}</p></blockquote>
</div></div></div></div>'''


def document_title(title: str, category: str = "") -> str:
    cid = uid()
    pid = uid()
    cat_block = (f'<div class="blog_category"><a href="#">{esc(category)}</a></div>'
                 if category else "")
    return f'''<div class="se-component se-documentTitle se-l-default" id="{cid}">
<div class="se-component-content">
<div class="se-section se-section-documentTitle se-l-default se-section-align-left">
{cat_block}
<div class="se-module se-module-text se-title-text">
<p class="se-text-paragraph se-text-paragraph-align-" id="{pid}"><span class="se-fs- se-ff-">{esc(title)}</span></p>
</div></div></div></div>'''


# ---------- markdown → components ----------

PLACEHOLDER_RE = re.compile(r"^\s*\[\s*(?:스크린샷|스샷|screenshot|img)\s*:\s*([^\]]+)\]\s*$", re.IGNORECASE)
IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
HR_RE = re.compile(r"^\s*---\s*$")
QUOTE_RE = re.compile(r"^>\s*(.*)$")
BOLD_LINE_RE = re.compile(r"^\*\*([^*].*?)\*\*\s*$")
LIST_RE = re.compile(r"^\s*([-*]|\d+\.)\s+(.+)$")


def parse_frontmatter(src: str) -> tuple[dict, str]:
    if not src.startswith("---\n"):
        return {}, src
    end = src.find("\n---\n", 4)
    if end < 0:
        return {}, src
    fm_raw = src[4:end]
    body = src[end + 5:]
    fm = {}
    for line in fm_raw.splitlines():
        m = re.match(r"^(\w+):\s*(.*)$", line)
        if m:
            k, v = m.group(1), m.group(2).strip()
            if v.startswith('"') and v.endswith('"'):
                try:
                    v = json.loads(v)
                except Exception:
                    v = v.strip('"')
            fm[k] = v
    return fm, body


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic"}


def _list_images(images_dir: pathlib.Path) -> list[pathlib.Path]:
    """List image files in a directory, skipping hidden/dotfiles
    (macOS AppleDouble `._*`, `.DS_Store`, etc.) and non-image extensions.
    """
    out = []
    for p in images_dir.iterdir():
        if p.name.startswith("."):
            continue
        if not p.is_file():
            continue
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        out.append(p)
    return sorted(out)


def resolve_image(ref: str, images_dir: pathlib.Path | None) -> str:
    """Resolve an image reference. If it's an absolute URL, return as-is.
    If images_dir is set and a file matches (prefix-match or name-match),
    return file:// URL. Otherwise return as-is.
    """
    if ref.startswith(("http://", "https://", "file://", "data:")):
        return ref
    if images_dir and images_dir.exists():
        files = _list_images(images_dir)
        for p in files:
            if p.name == ref:
                return "file://" + str(p.resolve())
        stem = pathlib.Path(ref).stem
        for p in files:
            if p.stem.startswith(stem) or stem.startswith(p.stem):
                return "file://" + str(p.resolve())
    return ref


def file_to_data_uri(path: pathlib.Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        mime = "application/octet-stream"
    data = path.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def maybe_embed(src_url: str, embed: bool) -> str:
    """If embed is on and src_url is a file:// URL pointing to an existing
    image file, return a data URI instead."""
    if not embed or not src_url.startswith("file://"):
        return src_url
    p = pathlib.Path(src_url[len("file://"):])
    if not p.is_file():
        return src_url
    return file_to_data_uri(p)


def convert(src: str, images_dir: pathlib.Path | None = None,
            title_override: str | None = None,
            embed: bool = False) -> str:
    fm, body = parse_frontmatter(src)
    title = title_override or fm.get("title") or ""
    category = fm.get("category") or ""

    components: list[str] = []
    if title:
        components.append(document_title(title, category))

    lines = body.splitlines()
    i = 0
    para_buf: list[str] = []

    def flush_para():
        # 줄 끝 백슬래시(\) = 단순 줄바꿈: 빈 줄 없이 문단만 나눠 연속 렌더
        nonlocal para_buf
        if para_buf:
            segs, cur = [], []
            for l in para_buf:
                s = l.strip()
                if not s:
                    continue
                if s.endswith("\\"):
                    cur.append(s[:-1].rstrip())
                    seg = " ".join(x for x in cur if x)
                    if seg:
                        segs.append(seg)
                    cur = []
                else:
                    cur.append(s)
            tail = " ".join(x for x in cur if x)
            if tail:
                segs.append(tail)
            for seg in segs:
                components.append(text_component(seg))
            para_buf = []

    auto_img_idx = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            flush_para()
            i += 1
            continue
        if HR_RE.match(line):
            flush_para()
            components.append(horizontal_line())
            i += 1
            continue
        h = HEADING_RE.match(line)
        if h:
            flush_para()
            # treat # as the post title (skip if already set) and ## as section heading
            level = len(h.group(1))
            text = h.group(2).strip()
            if level == 1 and title and text == title:
                pass
            else:
                # 세션 제목(##) 위에는 항상 구분선 (기린님 블로그 작성법)
                if level == 2 and components and "se-horizontalLine" not in components[-1]:
                    components.append(horizontal_line())
                components.append(text_component(text, heading=True))
            i += 1
            continue
        img = IMAGE_RE.match(line)
        if img:
            flush_para()
            alt, ref = img.group(1), img.group(2)
            src_url = maybe_embed(resolve_image(ref, images_dir), embed)
            components.append(image_component(src_url, alt))
            i += 1
            continue
        ph = PLACEHOLDER_RE.match(line)
        if ph:
            flush_para()
            label = ph.group(1).strip()
            # try to auto-match a file in images_dir by index
            matched = None
            if images_dir and images_dir.exists():
                files = _list_images(images_dir)
                if auto_img_idx < len(files):
                    matched = "file://" + str(files[auto_img_idx].resolve())
                    auto_img_idx += 1
            if matched:
                components.append(image_component(maybe_embed(matched, embed), label))
            else:
                components.append(placeholder_component(label))
            i += 1
            continue
        lst = LIST_RE.match(line)
        if lst:
            # 리스트 항목은 각각 별도 문단으로 (한 줄로 뭉치지 않게)
            flush_para()
            marker = lst.group(1)
            bullet = "• " if marker in ("-", "*") else f"{marker} "
            components.append(text_component(bullet + lst.group(2).strip()))
            i += 1
            continue
        b = BOLD_LINE_RE.match(line)
        if b:
            # 전체 라인 볼드(**...**)는 절 제목으로 (평문보다 큰 글씨)
            flush_para()
            components.append(text_component(b.group(1).strip(), subheading=True))
            i += 1
            continue
        q = QUOTE_RE.match(line)
        if q:
            flush_para()
            quote_lines = [q.group(1)]
            i += 1
            while i < len(lines):
                qq = QUOTE_RE.match(lines[i])
                if not qq:
                    break
                quote_lines.append(qq.group(1))
                i += 1
            components.append(quote_component(" ".join(quote_lines)))
            continue
        para_buf.append(line)
        i += 1
    flush_para()

    body_html = "\n".join(components)
    page = f'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>{esc(title) if title else "blog draft"}</title>
<style>
body {{ max-width: 720px; margin: 2rem auto; font-family: -apple-system, sans-serif; padding: 0 1rem; line-height: 1.7; }}
.se-main-container {{ }}
.se-documentTitle p span {{ font-size: 28px; font-weight: 700; }}
.se-section-text p {{ margin: 0.8em 0; }}
.se-fs-fs24 b {{ font-size: 22px; background: #fff593; padding: 2px 4px; }}
.se-fs-fs19 b {{ font-size: 18px; font-weight: 700; }}
.se-image-resource {{ max-width: 100%; display: block; margin: 1em auto; }}
.se-hr {{ border: none; border-top: 1px solid #ccc; margin: 2em 0; }}
.blog_category a {{ color: #1ec800; text-decoration: none; font-size: 14px; }}
blockquote {{ border-left: 3px solid #ccc; padding-left: 1em; color: #555; }}
</style>
</head><body>
<div class="se-viewer se-theme-default">
<div class="se-main-container">
{body_html}
</div></div>
</body></html>'''
    return page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("in_md")
    ap.add_argument("out_html")
    ap.add_argument("--images", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--embed", action="store_true",
                    help="Embed images as base64 data URIs (for clipboard paste into Naver editor)")
    args = ap.parse_args()
    src = pathlib.Path(args.in_md).read_text(encoding="utf-8")
    images_dir = pathlib.Path(args.images).resolve() if args.images else None
    out = convert(src, images_dir=images_dir, title_override=args.title, embed=args.embed)

    # emoji scan
    emoji_re = re.compile(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")
    if emoji_re.search(out):
        print("[warn] emoji detected in output!", file=sys.stderr)
        sys.exit(3)

    pathlib.Path(args.out_html).write_text(out, encoding="utf-8")
    print(f"[ok] wrote {args.out_html} ({len(out)} bytes)")


if __name__ == "__main__":
    main()
