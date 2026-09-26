#!/usr/bin/env python3
"""tistory→naver 마이그레이션의 기본 실행 경로 (2026-08-20 확정).

기존 postwrite 탭은 절대 건드리지 않는다 — 닫지도, 비우지도(--clear), 재사용하지도
않는다. 항상 새 탭을 열어 그 탭에서만 작업한다. 사용자가 같은 지시를 반복하며
강하게 확정한 규칙이다.

migrate.py의 chrome_js는 '첫 번째' postwrite 탭을 조준하므로 기존 탭이 남아 있으면
새 탭이 무시된다. 여기서 chrome_js를 '마지막' postwrite 탭 조준으로 바꿔치기한다.
새 탭은 창 끝에 열리므로 마지막 매치 = 새 탭이고, ensure_postwrite_tab의 raise
루프도 마지막 매치를 활성으로 남기므로 JS 조준과 CGEvent 클릭이 같은 탭을 본다.

새 탭을 여는 창도 고른다 (2026-09-18 추가). 예전에는 `window 1`을 하드코딩해서
사용자가 보고 있던 창(치지직 방송 등)의 활성 탭을 빼앗았다. 이제 재생 중일 법한
탭이 있는 창은 피하고, 전부 그렇다면 새 창을 연다. `--chrome-window N`으로 직접
지정할 수도 있다.

usage: migrate_fresh_tab.py <TISTORY_URL> [--tags "..."] [기타 migrate.py 플래그]
       [--chrome-window N]
(--clear는 여기서 금지: 전달돼도 제거한다)
"""
import sys, os, time, base64, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import migrate as M

# 창 고르기(방송 탭 있는 창 피하기)는 리포 공용 _lib/chrome_window.py가 정본이다.
# blog/upload_to_editor.py 등 새 탭을 여는 다른 스크립트도 같은 규칙을 쓴다.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "_lib"))
from chrome_window import MEDIA_PATTERNS, pick_target_window  # noqa: E402,F401

# 창은 최전면으로 올리면 index가 바뀐다. 그래서 index가 아니라 안정적인
# window id로 대상 창을 붙든다.
TARGET_WIN = None  # pick_target_window()가 채운다 (Chrome window id)


def chrome_js_last(js, timeout=15):
    """대상 창의 마지막 postwrite 탭에서 JS 실행.

    원본 migrate.chrome_js는 전체 창을 훑어 '첫' 탭을 조준한다. 여기서는 창을
    TARGET_WIN으로 좁혀, 다른 창에 남아 있는 기존 postwrite 탭을 건드리지 않는다.
    """
    b64 = base64.b64encode(js.encode()).decode()
    wrapped = f"eval(decodeURIComponent(escape(atob('{b64}'))))"
    script = (
        'tell application "Google Chrome"\n'
        "set tw to 0\nset tt to 0\n"
        "set tIdx to 0\n"
        f"repeat with t in tabs of (first window whose id is {TARGET_WIN})\n"
        "set tIdx to tIdx + 1\n"
        'if URL of t contains "/postwrite" then\n'
        "set tt to tIdx\n"
        "end if\nend repeat\n"
        'if tt is 0 then return "NO_TAB"\n'
        f'return execute tab tt of (first window whose id is {TARGET_WIN}) '
        f'javascript "{wrapped}"\n'
        "end tell"
    )
    out = subprocess.run(["osascript", "-e", script], capture_output=True,
                         text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"chrome_js: {out.stderr.strip()}")
    return out.stdout.strip()


def main():
    global TARGET_WIN

    args = [a for a in sys.argv[1:] if a != "--clear"]
    explicit = None
    if "--chrome-window" in args:
        i = args.index("--chrome-window")
        explicit = int(args[i + 1])
        del args[i:i + 2]
    if not args or args[0].startswith("--"):
        sys.exit("usage: migrate_fresh_tab.py <TISTORY_URL> [--tags ...] "
                 "[--chrome-window N]")

    # 0. 새 탭을 열 창 결정 (보고 있는 창은 피한다)
    TARGET_WIN = pick_target_window(explicit)
    M.chrome_js = chrome_js_last

    # 1. 새 탭 열기 (기존 탭은 손대지 않음)
    M.osa('tell application "Google Chrome"\nactivate\n'
          f"set tgt to (first window whose id is {TARGET_WIN})\n"
          'tell tgt to make new tab at end of tabs with properties '
          '{URL:"https://blog.naver.com/op5321/postwrite"}\n'
          "set active tab index of tgt to (count of tabs of tgt)\n"
          "set index of tgt to 1\nend tell")
    for _ in range(25):
        time.sleep(1)
        if M.chrome_js("document.querySelector('.se-canvas') ? 'ready' : 'loading'") == "ready":
            break
    print("[프렙] 새 에디터 로딩 완료")

    # 2. 임시저장 복원 다이얼로그 취소 (늦게 뜰 수 있어 3회)
    for _ in range(3):
        time.sleep(2)
        r = M.chrome_js(
            '(function(){var b=Array.from(document.querySelectorAll("button"))'
            '.find(function(x){return x.offsetParent&&x.textContent.trim()==="취소";});'
            'if(b){b.click();return "dismissed";}return "no-dialog";})()')
        if r == "dismissed":
            print("[프렙] 임시저장 다이얼로그 취소")
            break

    # 3. 빈 에디터 검증 (아니면 즉시 중단 — 절대 비우지 않는다)
    time.sleep(1)
    n = M.chrome_js("String(document.querySelectorAll('.se-component').length)")
    print("[프렙] 새 탭 컴포넌트:", n)
    if not n.isdigit() or int(n) > 2:
        sys.exit("ABORT: 새 탭이 비어있지 않음 (비우기 금지 — 원인 확인 필요)")

    # 4. 본 마이그레이션 (패치된 조준으로 실행)
    sys.argv = ["migrate.py"] + args
    return M.main()


if __name__ == "__main__":
    sys.exit(main())
