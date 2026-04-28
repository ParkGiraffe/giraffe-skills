#!/usr/bin/env python3
"""Parse a Naver m.blog SmartEditor post HTML → markdown with frontmatter.

Usage: parse_smarteditor.py <in.html> <log_no> <out.md>
"""
import sys, re, html, json, pathlib
from html.parser import HTMLParser

# ---------- helpers ----------

TAG_RE = re.compile(r"<[^>]+>")
ZWSP_RE = re.compile(r"[\u200b\ufeff\u00a0]")

def strip_tags(s: str) -> str:
    return TAG_RE.sub("", s)

def clean_text(s: str) -> str:
    s = html.unescape(s)
    s = ZWSP_RE.sub(" ", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


class Slicer(HTMLParser):
    """Collect (tag, attrs, inner_html_start) events so we can slice the input
    string by byte offsets. We only need coarse structure: top-level se-component
    blocks inside se-main-container.
    """
    def __init__(self, src: str):
        super().__init__(convert_charrefs=False)
        self.src = src
        self.stack: list[tuple[str, dict, int]] = []  # (tag, attrs, start_offset)
        self.components: list[tuple[str, int, int]] = []  # (kind, start, end)
        self.in_main = 0  # depth inside main-container
        self.main_depth_trigger = None

    def handle_starttag(self, tag, attrs):
        if tag != "div":
            return
        a = dict(attrs)
        cls = a.get("class", "")
        offset = self.getpos_offset()
        # entering main container
        if "se-main-container" in cls and self.in_main == 0:
            self.in_main = 1
            self.main_depth_trigger = len(self.stack)
            self.stack.append(("__main__", a, offset))
            return
        if self.in_main:
            self.stack.append((tag, a, offset))
            # direct se-component children (any depth inside main)
            if "se-component" in cls:
                kind = self._kind_from_class(cls)
                # defer end until matching close
                self.stack[-1] = (f"__comp__:{kind}", a, offset)

    def handle_endtag(self, tag):
        if tag != "div":
            return
        if not self.stack:
            return
        top_tag, top_attrs, top_start = self.stack.pop()
        end = self.getpos_offset_after()
        if top_tag.startswith("__comp__:"):
            kind = top_tag.split(":", 1)[1]
            self.components.append((kind, top_start, end))
        elif top_tag == "__main__":
            self.in_main = 0

    @staticmethod
    def _kind_from_class(cls: str) -> str:
        for k in ("documentTitle", "horizontalLine", "imageStrip", "image",
                  "text", "quotation", "code", "video", "oembed", "material",
                  "table", "map", "placesMap", "sticker", "file"):
            if f"se-{k}" in cls:
                return k
        return "unknown"

    # --- offset tracking (HTMLParser gives line/col; convert to byte offset) ---
    def getpos_offset(self) -> int:
        return self._offset_at(self.getpos())

    def getpos_offset_after(self) -> int:
        line, col = self.getpos()
        # compute end of current tag (index of '>' + 1)
        start = self._offset_at((line, col))
        end = self.src.find(">", start)
        return end + 1 if end >= 0 else start

    def _offset_at(self, pos) -> int:
        line, col = pos
        # build line starts once
        if not hasattr(self, "_line_starts"):
            self._line_starts = [0]
            for i, c in enumerate(self.src):
                if c == "\n":
                    self._line_starts.append(i + 1)
        return self._line_starts[line - 1] + col


def extract_main_components(html_src: str) -> list[tuple[str, str]]:
    """Return list of (kind, raw_html_slice) for each top-level SE component
    inside se-main-container. Uses regex rather than HTMLParser for robustness
    on Naver's messy markup.
    """
    # locate main container
    m = re.search(r'<div[^>]*class="[^"]*se-main-container[^"]*"[^>]*>', html_src)
    if not m:
        return []
    start = m.end()
    # naive but effective: find all se-component top-level divs by scanning
    # We rely on Naver's indentation: each top-level component opens with
    # `<div class="se-component ...` at the same indent level and closes with
    # </div> before the next one. We'll do depth-aware extraction.
    depth = 0
    i = start
    comps: list[tuple[str, str]] = []
    comp_start = -1
    comp_kind = ""
    comp_open_depth = -1
    tag_re = re.compile(r"<(/?)(div)\b([^>]*)>", re.IGNORECASE)
    while i < len(html_src):
        tm = tag_re.search(html_src, i)
        if not tm:
            break
        closing, _, attrs = tm.groups()
        if closing:
            depth -= 1
            if comp_open_depth == depth and comp_start >= 0:
                comps.append((comp_kind, html_src[comp_start:tm.end()]))
                comp_start = -1
                comp_kind = ""
                comp_open_depth = -1
            # exiting main-container when depth goes below 0 relative to start
            if depth < 0:
                break
        else:
            # opening
            cls_m = re.search(r'class="([^"]*)"', attrs)
            cls = cls_m.group(1) if cls_m else ""
            if depth == 0 and "se-component" in cls and comp_start < 0:
                comp_start = tm.start()
                comp_kind = Slicer._kind_from_class(cls)
                comp_open_depth = depth
            depth += 1
        i = tm.end()
    return comps


# ---------- component renderers ----------

def render_text(block: str) -> str:
    """Convert a se-text component to markdown. Large bold spans become ##."""
    # find each <p class="se-text-paragraph ..."> ... </p>
    paragraphs = re.findall(
        r'<p[^>]*class="se-text-paragraph[^"]*"[^>]*>(.*?)</p>',
        block, re.DOTALL,
    )
    lines = []
    for p in paragraphs:
        # detect heading: any span with se-fs-fs{N>=20} wrapping <b>...</b>
        is_heading = False
        m = re.search(r'class="[^"]*se-fs-fs(\d+)[^"]*"[^>]*>(.*?)</span>',
                      p, re.DOTALL)
        if m:
            size = int(m.group(1))
            inner = m.group(2)
            if size >= 20 and re.search(r"<b>", inner):
                is_heading = True
        text = clean_text(strip_tags(p))
        if not text:
            lines.append("")
            continue
        if is_heading:
            lines.append(f"## {text}")
        else:
            lines.append(text)
    return "\n\n".join(x for x in lines if x is not None).strip("\n")


def render_image(block: str) -> str:
    # prefer data-lazy-src (actual URL without blur), fallback to src
    m = re.search(r'data-lazy-src="([^"]+)"', block) or \
        re.search(r'class="se-image-resource"[^>]*src="([^"]+)"', block) or \
        re.search(r'<img[^>]*src="([^"]+)"[^>]*class="se-image-resource"', block)
    url = m.group(1) if m else ""
    # strip "?type=w800" query param suffix naver adds
    url = re.sub(r"\?type=[^&\"]*", "", url)
    alt = ""
    am = re.search(r'<img[^>]*alt="([^"]*)"', block)
    if am:
        alt = am.group(1)
    return f"![{alt}]({url})"


def render_image_strip(block: str) -> str:
    imgs = re.findall(r'data-lazy-src="([^"]+)"', block)
    if not imgs:
        imgs = re.findall(r'class="se-image-resource"[^>]*src="([^"]+)"', block)
    out = []
    for u in imgs:
        u = re.sub(r"\?type=[^&\"]*", "", u)
        out.append(f"![]({u})")
    return "\n\n".join(out)


def render_hr(_: str) -> str:
    return "---"


def render_quotation(block: str) -> str:
    text = clean_text(strip_tags(block))
    return "\n".join("> " + l for l in text.splitlines() if l)


def render_code(block: str) -> str:
    # naive: strip tags, wrap in fenced block
    text = strip_tags(block)
    text = html.unescape(text).strip("\n")
    return "```\n" + text + "\n```"


def render_unknown(kind: str, block: str) -> str:
    text = clean_text(strip_tags(block))
    return f"<!-- unhandled {kind} --> {text}" if text else ""


RENDERERS = {
    "text": render_text,
    "image": render_image,
    "imageStrip": render_image_strip,
    "horizontalLine": render_hr,
    "quotation": render_quotation,
    "code": render_code,
}


# ---------- title / category / date ----------

def extract_title(html_src: str) -> str:
    m = re.search(
        r'<div class="se-module se-module-text se-title-text">.*?<span[^>]*>(.*?)</span>',
        html_src, re.DOTALL,
    )
    if m:
        return clean_text(strip_tags(m.group(1)))
    m = re.search(r"<title>([^<]+)</title>", html_src)
    return clean_text(strip_tags(m.group(1))) if m else ""


def extract_category(html_src: str) -> str:
    m = re.search(r'<div class="blog_category">.*?<a[^>]*>(.*?)</a>', html_src, re.DOTALL)
    return clean_text(strip_tags(m.group(1))) if m else ""


def extract_date(html_src: str) -> str:
    # look for "작성시간" or se_publishDate
    m = re.search(r'class="se_publishDate[^"]*"[^>]*>([^<]+)</', html_src)
    if m:
        return clean_text(m.group(1))
    m = re.search(r'"publishDate"\s*:\s*"([^"]+)"', html_src)
    return m.group(1) if m else ""


# ---------- main ----------

def parse(html_src: str, log_no: str) -> dict:
    title = extract_title(html_src)
    category = extract_category(html_src)
    date = extract_date(html_src)
    comps = extract_main_components(html_src)
    body_parts = []
    for kind, block in comps:
        if kind == "documentTitle":
            continue  # title already captured
        r = RENDERERS.get(kind)
        if r:
            out = r(block)
        else:
            out = render_unknown(kind, block)
        if out:
            body_parts.append(out)
    body = "\n\n".join(body_parts).strip()
    return {
        "log_no": log_no,
        "title": title,
        "category": category,
        "date": date,
        "url": f"https://blog.naver.com/op5321/{log_no}",
        "body": body,
    }


def to_markdown(rec: dict) -> str:
    fm = [
        "---",
        f'log_no: "{rec["log_no"]}"',
        f'title: {json.dumps(rec["title"], ensure_ascii=False)}',
        f'category: {json.dumps(rec["category"], ensure_ascii=False)}',
        f'date: "{rec["date"]}"',
        f'url: {rec["url"]}',
        "---",
        "",
        f"# {rec['title']}",
        "",
        rec["body"],
        "",
    ]
    return "\n".join(fm)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("usage: parse_smarteditor.py <in.html> <log_no> <out.md>", file=sys.stderr)
        sys.exit(2)
    in_path, log_no, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    src = pathlib.Path(in_path).read_text(encoding="utf-8", errors="replace")
    rec = parse(src, log_no)
    pathlib.Path(out_path).write_text(to_markdown(rec), encoding="utf-8")
    print(json.dumps({
        "log_no": log_no,
        "title": rec["title"],
        "category": rec["category"],
        "body_len": len(rec["body"]),
        "out": out_path,
    }, ensure_ascii=False))
