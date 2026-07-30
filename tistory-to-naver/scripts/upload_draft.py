#!/usr/bin/env python3
"""Upload a local blog draft (script.md + images) into a FRESH Naver
postwrite editor, reusing the proven migrate.py orchestration.

Unlike migrate.py (which fetches a Tistory URL), this parses a local
draft folder via paste_to_naver.parse_to_chunks (so ## = yellow heading,
### = no-bg subheading) and pastes it.

Flow: close any existing /postwrite tabs -> open a fresh one (empty editor,
cancel the draft-restore dialog) -> paste title -> paste body chunks with
per-chunk verification -> style pass (hr center + every image center).

Usage: python3 upload_draft.py <draft_dir> [--title "..."]
"""
import sys, os, json, time, pathlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))   # <repo>/tistory-to-naver/scripts -> <repo>
sys.path.insert(0, HERE)
import migrate as M          # chrome plumbing, CGEvent input, paste_chunks, style_pass
import migrate_from_url as m  # clipboard helpers (used by M.paste_chunks)
sys.path.insert(0, os.path.join(REPO, "blog", "scripts"))
import paste_to_naver as P    # parse_to_chunks with ## / ### heading styles

BLOG_ID = "op5321"


def close_existing_postwrite():
    M.osa(
        'tell application "Google Chrome"',
        "repeat with w in windows",
        "set k to count of tabs of w",
        "repeat with i from k to 1 by -1",
        'if (URL of tab i of w) contains "/postwrite" then close tab i of w',
        "end repeat",
        "end repeat",
        "end tell",
    )


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    draft = pathlib.Path(args[0]).resolve()
    title = "[우아콘 2025] 방문 후기"
    if "--title" in sys.argv:
        title = sys.argv[sys.argv.index("--title") + 1]

    md = (draft / "script.md").read_text(encoding="utf-8")
    images_dir = draft / "images"
    chunks = P.parse_to_chunks(md, images_dir)
    n_img = sum(1 for c in chunks if c["type"] == "image")
    print(f"[parse] {len(chunks)} chunks ({n_img} images) | title: {title}", flush=True)

    # 단일 postwrite 탭 재사용 (좌표 읽는 탭 == 맨 앞 탭 보장 → 허공 붙여넣기 방지).
    # 새 탭을 또 열면 chrome_js는 '첫' postwrite 탭을 보고 CGEvent는 '맨 앞' 탭을
    # 때리므로 둘이 어긋난다(직전 사고 원인). 기존 탭 하나를 재사용하고 비운다.
    print("[tab] ensuring single postwrite tab (reuse + clear)...", flush=True)
    M.ensure_postwrite_tab(BLOG_ID)
    M.chrome_js(M.JS_DISMISS_DIALOG)
    time.sleep(0.6)
    if not M.wait_for_window_focus():
        print("[ERROR] Chrome never got OS focus", flush=True)
        sys.exit(1)

    n = int(M.chrome_js(M.JS_COMPONENT_COUNT))
    if n > 2:
        print(f"[clear] editor has {n} components -> wiping", flush=True)
        c = json.loads(M.chrome_js(M.JS_BODY_COORDS))
        M.click(c["x"], c["y"]); time.sleep(0.4)
        M.key(M.KEY_A, cmd=True); time.sleep(0.5)
        M.key(M.KEY_BACKSPACE); time.sleep(0.9)
        n = int(M.chrome_js(M.JS_COMPONENT_COUNT))
        print(f"[clear] now {n} components", flush=True)

    # ---- title ----
    print("[title] pasting...", flush=True)
    M.copy_text(title)
    norm = lambda s: s.replace("\xa0", " ").strip()
    ok = False
    for _ in range(3):
        c = json.loads(M.chrome_js(M.JS_TITLE_COORDS))
        M.triple_click(c["x"], c["y"])
        time.sleep(0.4)
        M.key(M.KEY_V, cmd=True)
        for _ in range(10):
            time.sleep(0.4)
            if norm(M.chrome_js(M.JS_TITLE_TEXT)) == norm(title):
                ok = True
                break
        if ok:
            break
        M.osa('tell application "Google Chrome" to activate')
        time.sleep(1.0)
    if not ok:
        print("[ABORT] title did not register -> focus likely broken. "
              "Not pasting body into the void. Re-run after checking the tab.",
              flush=True)
        sys.exit(4)
    print("[title] ok", flush=True)

    # ---- body ----
    print("[body] focusing + pasting chunks...", flush=True)
    c = json.loads(M.chrome_js(M.JS_BODY_COORDS))
    M.click(c["x"], c["y"])
    time.sleep(0.5)
    failures = M.paste_chunks(chunks)

    # ---- style pass ----
    print("[style] hr line3+center, images center...", flush=True)
    styled = M.style_pass()
    print(f"      hr styled: {styled['hr']}, images centered: {styled['img']}", flush=True)

    audit = json.loads(M.chrome_js(M.JS_FINAL_AUDIT))
    print("\n=== DONE ===", flush=True)
    print(f"title:  {audit['title']}", flush=True)
    print(f"counts: {audit['counts']}", flush=True)
    if failures:
        print(f"FAILED chunks: {failures}", flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
