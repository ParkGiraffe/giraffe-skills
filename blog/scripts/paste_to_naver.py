#!/usr/bin/env python3
"""Paste a blog draft's script.md into the focused Naver blog editor.

Directly adapted from the proven-working auto mode in
https://github.com/ParkGiraffe/tistory-to-naver-blog (run_migration.py +
migrate_from_url.py). Core differences:
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
BODY_SPAN_STYLE = (
    "font-size:15px;font-weight:normal;background-color:transparent;"
    "color:#212529;"
)
BARRIER_HTML = '<p><br></p>'


def heading_html(text: str) -> str:
    t = _html_escape(text)
    return (
        f'<p><span style="{HEADING_SPAN_STYLE}"><b>{t}</b></span></p>'
        + BARRIER_HTML
    )


def body_html(text: str) -> str:
    t = _html_escape(text)
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
    chunks: list[dict] = []
    html_buf: list[str] = []
    para: list[str] = []
    auto_idx = 0

    def flush_para():
        nonlocal para
        if para:
            text = " ".join(l.strip() for l in para if l.strip())
            if text:
                html_buf.append(body_html(text))
        para = []

    def flush_html():
        nonlocal html_buf
        if html_buf:
            chunks.append({"type": "html", "content": "".join(html_buf)})
            html_buf = []

    def push_image(p: pathlib.Path):
        flush_para()
        flush_html()
        chunks.append({"type": "image", "path": str(p.resolve())})

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_para()
            continue
        if HR_RE.match(line):
            flush_para()
            html_buf.append("<hr>")
            continue
        h = HEADING_RE.match(line)
        if h:
            flush_para()
            level = len(h.group(1))
            text = h.group(2).strip()
            if level == 1:
                # Skip post title entirely — it goes in Naver's dedicated
                # title input field above the body, not in the body itself.
                # The caller prints the title separately so the user can
                # paste it manually into that field.
                continue
            html_buf.append(heading_html(text))
            continue
        img = IMAGE_RE.match(line)
        if img:
            flush_para()
            ref = img.group(2)
            if ref.startswith(("http://", "https://", "file://")):
                html_buf.append(body_html(f"[원격 이미지: {ref}]"))
                continue
            matched = None
            for p in files:
                if p.name == ref or p.stem == pathlib.Path(ref).stem:
                    matched = p
                    break
            if matched:
                push_image(matched)
            else:
                html_buf.append(body_html(f"[이미지 누락: {ref}]"))
            continue
        ph = PLACEHOLDER_RE.match(line)
        if ph:
            flush_para()
            if auto_idx < len(files):
                push_image(files[auto_idx])
                auto_idx += 1
            else:
                html_buf.append(body_html(f"[스크린샷: {ph.group(1).strip()}]"))
            continue
        para.append(line)
    flush_para()
    flush_html()
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
