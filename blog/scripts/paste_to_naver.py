#!/usr/bin/env python3
"""Paste a blog draft's script.md into the focused Naver blog editor.

Directly adapted from the proven-working auto mode in the tistory migration
engine, now vendored into this repo at tistory-to-naver/scripts/
(run_migration.py + migrate_from_url.py). Core differences:
  - Parses a local script.md instead of fetching a Tistory URL.
  - Images are already local files; no download step.

Execution flow (auto mode):
  1. Parse script.md into ordered chunks alternating between HTML text
     (wrapped in simple <p> tags, no inline styles) and image file paths.
  2. Countdown 3 seconds.
  3. For each chunk:
       - HTML: copy_html_to_clipboard  → paste_cmd → sleep 0.5
       - Image: copy_image_file_to_clipboard → paste_cmd → sleep 1.0

Usage:
  paste_to_naver.py <draft_dir> [--images DIR] [--start 3] [--dry-run]
                    [--manual]

Before running:
  - Accessibility permission for Terminal (System Settings → Privacy &
    Security → Accessibility → add Terminal/iTerm)
  - Open Naver blog editor and click into the post body so the cursor
    is positioned where content should start.
"""

import sys, os, re, time, json, subprocess, pathlib, argparse
import AppKit


def resolve_images_dir(draft: pathlib.Path, flag_value: str | None) -> pathlib.Path | None:
    """Resolve the images directory. Priority:
      1. Explicit --images flag
      2. meta.json → images.source_folder
      3. None
    """
    if flag_value:
        return pathlib.Path(flag_value).resolve()
    meta_path = draft / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            src = (meta.get("images") or {}).get("source_folder")
            if src:
                p = pathlib.Path(src).resolve()
                if p.exists():
                    return p
        except Exception as e:
            print(f"[meta.json] parse error: {e}", file=sys.stderr)
    return None

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".tiff"}

IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
PLACEHOLDER_RE = re.compile(
    r"^\s*\[\s*(?:스크린샷|스샷|screenshot|img)\s*:\s*([^\]]+)\]\s*$", re.I,
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
HR_RE = re.compile(r"^\s*---\s*$")


def list_images(d: pathlib.Path | None) -> list[pathlib.Path]:
    if not d or not d.exists():
        return []
    return sorted(
        p for p in d.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and p.suffix.lower() in IMAGE_EXTS
    )


def strip_frontmatter(src: str) -> str:
    # <!-- ... --> 마크다운 주석은 검사기용 표식이라 본문에 붙여 넣지 않는다 (2026-09-03)
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    if not src.startswith("---\n"):
        return src
    end = src.find("\n---\n", 4)
    return src[end + 5:] if end > 0 else src


# ---------- parse script.md → chunks ----------

def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Observed styles from op5321 blog (박기린의 기린파크):
#   헤딩: <span style="background-color:#fff593;" class="se-fs-fs24"><b>…</b></span>
#   본문: <p class="se-text-paragraph">…</p>
#
# Naver SmartEditor's paste sanitizer tends to bleed the previous paragraph's
# inline style onto subsequent paragraphs. We defend against this in two ways:
#   1. Every body span sets font-weight:normal + background:transparent
#      explicitly so the heading's style can't inherit through.
#   2. After every heading we emit an empty <p><br></p> as a style barrier
#      paragraph (common WYSIWYG trick).
HEADING_SPAN_STYLE = "font-size:24px;background-color:#fff593;"
# 소제목(### , level>=3): 배경 없이 본문보다 큰 볼드. 노랑 제목보다 살짝 작게.
SUBHEADING_SPAN_STYLE = (
    "font-size:19px;background-color:transparent;color:#212529;"
)
BODY_SPAN_STYLE = (
    "font-size:15px;font-weight:normal;background-color:transparent;"
    "color:#212529;"
)
BARRIER_HTML = '<p><br></p>'

# 사용자 평소 블로그 여백 규칙 (2026-06-16 지시):
#   제목(세션, ##) 위 5줄 / 소제목(###) 위 3줄 /
#   [사진 + 바로 아래 설명글] 묶음 아래 4줄.
# 핵심: 사진과 그 캡션(본문 단락)은 딱 붙인다(여백 0). 여백은 캡션(본문 단락)
#   '아래'에만 둔다 = 다음 사진/요소 앞에 옴. 사진 바로 뒤에는 여백을 넣지 않음.
# 빈 줄은 <p><br></p> 빈 단락으로 표현. 인접한 여백은 합산하지 않고 max로 둠.
BLANK_P = '<p><br></p>'
SPACE_BEFORE_SESSION = 7
SPACE_BEFORE_SUB = 3
SPACE_AFTER_TEXT = 8   # 본문 단락(=사진 캡션) 아래 8줄. 사진 바로 뒤엔 안 넣음. (2026-09-03 발행 글 실측: 중앙값 8줄)


def heading_html(text: str, level: int = 2) -> str:
    # 제목 뒤 trailing 빈 줄(barrier) 없음 — 소제목 바로 밑에 사진/글을 딱 붙이기
    # 위함. 스타일 번짐은 body_html의 명시적 reset span으로 이미 차단됨.
    t = _html_escape(text)
    style = SUBHEADING_SPAN_STYLE if level >= 3 else HEADING_SPAN_STYLE
    return f'<p><span style="{style}"><b>{t}</b></span></p>'


BOLD_LINE_RE = re.compile(r"^\*\*([^*].*?)\*\*$")
# 리스트 항목(- / * / 1.): 각각 별도 문단으로 렌더 (md_to_smarteditor와 동일).
# 없으면 연속 항목이 flush_para에서 한 줄로 합쳐진다 (2026-07-16 리스트 뭉침 버그).
LIST_RE = re.compile(r"^\s*([-*]|\d+\.)\s+(.+)$")

# 인라인 코드(`...`): 노션풍 회색 배경 + 붉은 글자 span으로 렌더 (2026-07-07)
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
INLINE_CODE_STYLE = (
    "font-size:14px;background-color:#f2f3f5;color:#d6336c;"
    "border-radius:3px;padding:1px 4px;"
)

# 인라인 서식 전체 (giraffe-editor의 마크 집합과 1:1, 2026-07-21):
#   `code`, ***bold italic***, **bold**, *italic*, <u>, <mark>,
#   <span style="color:#xxx;">, [text](href)
_INLINE_TOKEN_RE = re.compile(
    r"(`[^`]+`)"
    r"|(\*\*\*[^*]+\*\*\*)"
    r"|(\*\*[^*]+\*\*)"
    r"|(\*[^*]+\*)"
    r"|(<u>.+?</u>)"
    r"|(<mark>.+?</mark>)"
    r"|(<span style=\"color:[^\"]+\">.+?</span>)"
    r"|(\[[^\]]+\]\([^)\s]+\))"
)


def _render_inline(text: str) -> str:
    """HTML 이스케이프 + 인라인 서식을 네이버가 보존하는 스타일로 변환."""
    out = []
    last = 0
    for m in _INLINE_TOKEN_RE.finditer(text):
        if m.start() > last:
            out.append(_html_escape(text[last:m.start()]))
        token = m.group(0)
        if m.group(1):
            out.append(f'<span style="{INLINE_CODE_STYLE}">{_html_escape(token[1:-1])}</span>')
        elif m.group(2):
            out.append(f"<b><i>{_render_inline(token[3:-3])}</i></b>")
        elif m.group(3):
            out.append(f"<b>{_render_inline(token[2:-2])}</b>")
        elif m.group(4):
            out.append(f"<i>{_render_inline(token[1:-1])}</i>")
        elif m.group(5):
            out.append(f"<u>{_render_inline(token[3:-4])}</u>")
        elif m.group(6):
            out.append(
                '<span style="background-color:#fff593;">'
                f"{_render_inline(token[6:-7])}</span>"
            )
        elif m.group(7):
            open_end = token.index('">') + 2
            out.append(f"{token[:open_end]}{_render_inline(token[open_end:-7])}</span>")
        elif m.group(8):
            close = token.index("](")
            label = _render_inline(token[1:close])
            href = _html_escape(token[close + 2:-1])
            out.append(f'<a href="{href}" target="_blank">{label}</a>')
        last = m.end()
    if last < len(text):
        out.append(_html_escape(text[last:]))
    return "".join(out)


def body_html(text: str) -> str:
    # 단락 전체가 **...** 인 경우 절 제목(소제목, 19px 볼드)으로 렌더.
    # md_to_smarteditor.py의 subheading(fs19)과 일치시킨다 — 예전엔 15px 본문
    # 볼드였는데, preview(md_to_smarteditor)와 실제 업로드가 달라 소제목이
    # 본문 크기로 나오는 사고가 났다 (2026-07-16 사용자 지적).
    b = BOLD_LINE_RE.match(text)
    if b:
        t = _render_inline(b.group(1).strip())
        return f'<p><span style="{SUBHEADING_SPAN_STYLE}"><b>{t}</b></span></p>'
    t = _render_inline(text)
    return f'<p><span style="{BODY_SPAN_STYLE}">{t}</span></p>'


def parse_to_chunks(md_text: str, images_dir: pathlib.Path | None) -> list[dict]:
    """Walk markdown body and emit ordered chunks.

    Chunk shapes:
      {"type": "html",  "content": "<p>...</p><p>...</p>..."}
      {"type": "image", "path": "/abs/path/to/file.jpg"}
    """
    body = strip_frontmatter(md_text)
    lines = body.splitlines()
    files = list_images(images_dir)

    # ---- 1) 토큰화 ----
    tokens: list[tuple] = []   # ('hr',) | ('h',level,text) | ('img',path) | ('p',text)
    para: list[str] = []

    def flush_para():
        # 줄 끝 백슬래시(\) = 단순 줄바꿈(markdown hard break).
        # 노션의 인접 블록(Enter)처럼 빈 줄 없이 <p>만 나눠 연속 렌더한다.
        if para:
            segs: list[str] = []
            cur: list[str] = []
            for l in para:
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
            if len(segs) == 1:
                tokens.append(("p", segs[0]))
            elif segs:
                tokens.append(("pgroup", segs))
        para.clear()

    auto_idx = 0
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_para()
            continue
        if HR_RE.match(line):
            flush_para()
            tokens.append(("hr",))
            continue
        h = HEADING_RE.match(line)
        if h:
            flush_para()
            level = len(h.group(1))
            text = h.group(2).strip()
            if level == 1:
                # 글 제목은 본문에 안 넣음 (네이버 제목칸으로 따로)
                continue
            tokens.append(("h", level, text))
            continue
        img = IMAGE_RE.match(line)
        if img:
            flush_para()
            ref = img.group(2)
            if ref.startswith(("http://", "https://", "file://")):
                tokens.append(("p", f"[원격 이미지: {ref}]"))
                continue
            matched = None
            for p in files:
                if p.name == ref or p.stem == pathlib.Path(ref).stem:
                    matched = p
                    break
            if matched:
                tokens.append(("img", str(matched.resolve())))
            else:
                tokens.append(("p", f"[이미지 누락: {ref}]"))
            continue
        ph = PLACEHOLDER_RE.match(line)
        if ph:
            flush_para()
            if auto_idx < len(files):
                tokens.append(("img", str(files[auto_idx].resolve())))
                auto_idx += 1
            else:
                tokens.append(("p", f"[스크린샷: {ph.group(1).strip()}]"))
            continue
        lst = LIST_RE.match(line)
        if lst:
            # 리스트 항목은 각각 별도 문단 토큰으로 (한 줄로 뭉치지 않게)
            flush_para()
            marker = lst.group(1)
            bullet = "• " if marker in ("-", "*") else f"{marker} "
            tokens.append(("li", bullet + lst.group(2).strip()))
            continue
        para.append(line)
    flush_para()

    # ---- 2) 여백 규칙 적용해 element 나열 ----
    elements: list[tuple] = []   # ('html', s) | ('img', path)

    def blanks(n):
        if n > 0:
            elements.append(("html", BLANK_P * n))

    prev_type = None        # 직전 토큰 종류
    prev_is_caption = False  # 직전 토큰이 캡션(사진 바로 뒤 문단)인지
    for i, tok in enumerate(tokens):
        typ = tok[0]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        is_caption = (typ == "p" and prev_type == "img")

        if typ == "hr":
            # 구분선 위 여백. 다음이 세션제목이면 그 5줄을 '구분선 위'에 둔다.
            n = SPACE_BEFORE_SESSION if (nxt and nxt[0] == "h" and nxt[1] == 2) else SPACE_AFTER_TEXT
            blanks(n)
            elements.append(("html", "<hr>"))
        elif typ == "h":
            level = tok[1]
            if level == 2 and prev_type != "hr":
                # 세션 제목(##) 위에는 항상 구분선 — 기린님 블로그 작성법 (2026-07-07)
                blanks(SPACE_BEFORE_SESSION)
                elements.append(("html", "<hr>"))
                prev_type = "hr"
            if prev_type == "hr":
                n = 0  # 구분선↔제목 딱 붙임 (여백은 이미 구분선 위에)
            elif prev_type == "h":
                n = 1  # 세션(노랑) 제목 바로 밑 첫 소제목은 한 칸만
            else:
                n = SPACE_BEFORE_SESSION if level == 2 else SPACE_BEFORE_SUB
                if prev_type in ("p", "img"):   # 직전 블록(설명글/사진) 끝 -> 경계 여백
                    n = max(n, SPACE_AFTER_TEXT)
            blanks(n)
            elements.append(("html", heading_html(tok[2], level)))
        elif typ == "img":
            # caption-after(사진 먼저, 밑에 설명글). 직전이 설명글이면 [사진+설명] 블록이
            # 끝난 것이므로 4줄 띄우고 새 사진. 구분선/앞 사진 뒤엔 딱 붙임.
            # 단 소제목 바로 뒤 사진은 barrier 한 칸을 둔다 — 안 두면 사진 다음 본문이
            # 소제목의 노란 배경 서식을 상속해 노랑 번짐이 생긴다(빈 단락이 상속을 끊음).
            if prev_type == "p":
                n = SPACE_AFTER_TEXT
            elif prev_type == "h":
                n = 1
            else:
                n = 0
            blanks(n)
            elements.append(("img", tok[1]))
        elif typ == "pgroup":  # 백슬래시 줄바꿈 그룹: 문단 여백 규칙은 그룹 단위로만
            if prev_type in ("img", "h"):
                n = 0
            elif prev_type == "p":
                n = 1
            else:
                n = 0
            blanks(n)
            for seg in tok[1]:
                elements.append(("html", body_html(seg)))
            typ = "p"  # 이후 여백 판단에는 일반 문단으로 취급
        elif typ == "li":  # 리스트 항목: 각각 별도 문단, 항목끼리는 딱 붙임
            if prev_type == "li":
                n = 0                  # 리스트 항목 사이 여백 0
            elif prev_type == "p":
                n = 1                  # 도입 문단 ↔ 리스트 첫 항목 1줄
            else:                      # img, h, hr, None
                n = 0
            blanks(n)
            elements.append(("html", body_html(tok[1])))
        else:  # 'p' (사진 아래 설명글)
            if prev_type in ("img", "h"):
                n = 0                  # 설명글은 사진/소제목 바로 밑에 딱 붙임
            elif prev_type in ("p", "li"):
                n = 1                  # 연속 문단 사이, 리스트 끝난 뒤 새 문단 1줄
            else:
                n = 0
            blanks(n)
            elements.append(("html", body_html(tok[1])))

        prev_type = typ
        prev_is_caption = is_caption

    # ---- 3) 연속 html을 한 chunk로 합치기 ----
    chunks: list[dict] = []
    buf: list[str] = []
    for kind, val in elements:
        if kind == "html":
            buf.append(val)
        else:
            if buf:
                chunks.append({"type": "html", "content": "".join(buf)})
                buf = []
            chunks.append({"type": "image", "path": val})
    if buf:
        chunks.append({"type": "html", "content": "".join(buf)})
    return chunks


# ---------- clipboard (adapted verbatim from migrate_from_url.py) ----------

def get_pasteboard():
    return AppKit.NSPasteboard.generalPasteboard()


def copy_html_to_clipboard(html_content: str) -> bool:
    """Wrap in minimal <html><body> and write as `public.html` + plain text."""
    safe_html = f"""
    <html>
    <head><meta charset='utf-8'></head>
    <body style='font-family: -apple-system, sans-serif;'>
        {html_content}
        <br>
    </body>
    </html>
    """
    pb = get_pasteboard()
    pb.clearContents()
    ns_html = safe_html.encode('utf-8')
    ns_data = AppKit.NSData.dataWithBytes_length_(ns_html, len(ns_html))
    types = ["public.html", AppKit.NSPasteboardTypeString]
    pb.declareTypes_owner_(types, None)
    pb.setData_forType_(ns_data, "public.html")
    pb.setString_forType_(html_content, AppKit.NSPasteboardTypeString)
    return True


def copy_image_file_to_clipboard(filepath: str) -> bool:
    """Copy the file itself to the clipboard (NSURL fileURL)."""
    if not os.path.exists(filepath):
        print(f"    [ERROR] Image file not found: {filepath}", file=sys.stderr)
        return False
    pb = get_pasteboard()
    pb.clearContents()
    ns_url = AppKit.NSURL.fileURLWithPath_(filepath)
    pb.writeObjects_([ns_url])
    return True


def paste_cmd() -> None:
    """Cmd+V via raw key code (IME-independent)."""
    time.sleep(0.2)
    cmd = (
        "osascript "
        "-e 'try' "
        "-e 'tell application \"System Events\" to key code 9 using command down' "
        "-e 'end try'"
    )
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"    [ERROR] Auto-paste failed: {result.stderr.strip()}", file=sys.stderr)
    except Exception as e:
        print(f"    [ERROR] Paste command exception: {e}", file=sys.stderr)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft_dir")
    ap.add_argument("--images", default=None)
    ap.add_argument("--start", type=float, default=3.0,
                    help="Countdown seconds before auto paste (default 3)")
    ap.add_argument("--html-sleep", type=float, default=0.5,
                    help="Sleep after each html chunk (default 0.5)")
    ap.add_argument("--image-sleep", type=float, default=1.0,
                    help="Sleep after each image chunk (default 1.0)")
    ap.add_argument("--manual", action="store_true",
                    help="Step through chunks waiting for Enter in terminal "
                         "(manual paste mode; doesn't auto-press Cmd+V)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the chunk plan without touching the clipboard")
    args = ap.parse_args()

    draft = pathlib.Path(args.draft_dir).resolve()
    md = draft / "script.md"
    if not md.exists():
        print(f"ERR: {md} not found", file=sys.stderr)
        sys.exit(2)

    images_dir = resolve_images_dir(draft, args.images)
    if images_dir:
        print(f"[images] resolved: {images_dir}")
    else:
        print("[images] WARNING: no images dir resolved. "
              "Placeholders will paste as literal text.", file=sys.stderr)

    md_text = md.read_text(encoding="utf-8")

    # Extract post title from frontmatter or first # line so we can show
    # it to the user (the title goes into Naver's dedicated title input
    # field, not the body).
    title = ""
    fm_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', md_text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            m = re.match(r'^title:\s*(.+)$', line)
            if m:
                title = m.group(1).strip().strip('"').strip("'")
                break
    if not title:
        tm = re.search(r"^# (.+)$", md_text, re.MULTILINE)
        if tm:
            title = tm.group(1).strip()

    # Sanity check: count placeholders in script.md
    placeholder_count = len(PLACEHOLDER_RE.findall(md_text) or [])
    inline_count = sum(1 for line in md_text.splitlines() if PLACEHOLDER_RE.match(line))
    img_ref_count = sum(1 for line in md_text.splitlines() if IMAGE_RE.match(line))
    expected_imgs = inline_count + img_ref_count
    available_imgs = len(list_images(images_dir))

    chunks = parse_to_chunks(md_text, images_dir)
    n_html = sum(1 for c in chunks if c["type"] == "html")
    n_img = sum(1 for c in chunks if c["type"] == "image")
    print(f"Parsed {len(chunks)} chunks ({n_html} html + {n_img} images)")
    print(f"[check] script.md image refs: {expected_imgs}, "
          f"folder images: {available_imgs}, chunked images: {n_img}")
    if expected_imgs > 0 and n_img == 0:
        print("\n❌ ERROR: script.md has image placeholders but none were resolved.",
              file=sys.stderr)
        print("   Did you pass --images or set meta.json images.source_folder?",
              file=sys.stderr)
        sys.exit(5)
    if expected_imgs != n_img:
        print(f"\n⚠️  WARNING: expected {expected_imgs} images but chunked {n_img}. "
              f"Some placeholders may paste as literal text.", file=sys.stderr)

    if args.dry_run:
        for i, c in enumerate(chunks, 1):
            if c["type"] == "image":
                print(f"  {i:2d}. [image] {pathlib.Path(c['path']).name}")
            else:
                preview = re.sub(r"<[^>]+>", " | ", c["content"])[:80]
                print(f"  {i:2d}. [html ] {preview}")
        return

    if args.manual:
        print()
        print("▶ 수동 모드. 매 chunk마다 클립보드에 복사 후 Enter 입력 대기.")
        print("▶ 네이버 에디터로 가서 Cmd+V 직접 누르고, 돌아와서 Enter.")
        for i, c in enumerate(chunks, 1):
            if c["type"] == "html":
                preview = re.sub(r"<[^>]+>", " ", c["content"])[:60]
                print(f"\n[{i:2d}/{len(chunks)}] html: {preview}")
                copy_html_to_clipboard(c["content"])
                print("  → 클립보드 준비됨. 네이버에서 Cmd+V.")
            else:
                name = pathlib.Path(c["path"]).name
                print(f"\n[{i:2d}/{len(chunks)}] image: {name}")
                if copy_image_file_to_clipboard(c["path"]):
                    print("  → 클립보드 준비됨. 네이버에서 Cmd+V.")
                else:
                    print("  → [실패, skip]")
                    continue
            input("  Enter for next chunk (Ctrl+C to abort) ")
        print("\n▶ 완료.")
        return

    # Auto mode
    if title:
        print()
        print("=" * 60)
        print("📝 제목 (네이버 에디터 상단의 '제목' 입력칸에 직접 붙여넣으세요):")
        print(f"   {title}")
        print("=" * 60)

    print()
    print("▶ 네이버 블로그 에디터 **본문** 영역을 클릭 (제목칸 아님).")
    print(f"▶ {args.start:.0f}초 후 본문 자동 paste 시작. 네이버 창 포커스 유지.")
    for i in range(int(args.start), 0, -1):
        print(f"   {i}...", flush=True)
        time.sleep(1)
    print("▶ 시작\n")

    for i, c in enumerate(chunks, 1):
        label = "Text " if c["type"] == "html" else "Image"
        if c["type"] == "html":
            preview = re.sub(r"<[^>]+>", " ", c["content"])[:50]
            print(f"[{i:2d}/{len(chunks)}] {label}: {preview}")
            copy_html_to_clipboard(c["content"])
            paste_cmd()
            time.sleep(args.html_sleep)
        else:
            name = pathlib.Path(c["path"]).name
            print(f"[{i:2d}/{len(chunks)}] {label}: {name}")
            if copy_image_file_to_clipboard(c["path"]):
                paste_cmd()
                time.sleep(args.image_sleep)
            else:
                print("    [skip]")

    print("\n▶ 완료. 네이버 에디터에서 결과 확인.")


if __name__ == "__main__":
    main()
