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

    # 항상 '새 탭을 연다'. 2026-08-07 실측으로 확인된 두 가지 금지 사항:
    #   1) 기존 탭을 닫지 말 것 — 작성 중인 글이 있으면 beforeunload alert가 뜨고,
    #      네이티브 alert는 CGEvent 입력과 osascript JS를 전부 삼켜 매크로가 죽는다.
    #   2) Cmd+A + Backspace로 비워서 재사용하지 말 것 — SE가 캐럿에 남은 인라인
    #      서식(노란 배경·취소선)을 유지해 다음 붙여넣기 본문 전체에 번진다.
    # 임시저장 복원 다이얼로그는 '떠야 닫을 수 있으므로' 로딩 후 넉넉히 기다렸다가
    # 취소를 누른다. .se-popup 안만 보면 아직 안 뜬 다이얼로그를 놓친다.
    print("[tab] opening a fresh postwrite tab (never close, never wipe)...", flush=True)
    M.osa('tell application "Google Chrome"',
          "activate",
          "make new tab at end of tabs of window 1 with properties "
          f'{{URL:"https://blog.naver.com/{BLOG_ID}/postwrite"}}',
          "set active tab index of window 1 to (count of tabs of window 1)",
          "end tell")
    time.sleep(6)
    M.chrome_js('(function(){var b=Array.from(document.querySelectorAll("button"))'
                '.find(function(x){return x.textContent.trim()==="취소"&&x.offsetParent;});'
                'if(b){b.click();return "dismissed";}return "no-dialog";})()')
    time.sleep(1.5)
    if not M.wait_for_window_focus():
        print("[ERROR] Chrome never got OS focus", flush=True)
        sys.exit(1)

    n = int(M.chrome_js(M.JS_COMPONENT_COUNT))
    if n > 2:
        print(f"[ABORT] 새 탭인데 컴포넌트가 {n}개 — 임시저장이 복원됐다. "
              "지우고 쓰지 않는다(서식 번짐). 다이얼로그를 직접 취소한 뒤 재실행할 것.",
              flush=True)
        sys.exit(3)

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
