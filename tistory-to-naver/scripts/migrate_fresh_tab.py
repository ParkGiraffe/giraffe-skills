#!/usr/bin/env python3
"""tistory→naver 마이그레이션의 기본 실행 경로 (2026-08-20 확정).

기존 postwrite 탭은 절대 건드리지 않는다 — 닫지도, 비우지도(--clear), 재사용하지도
않는다. 항상 새 탭을 열어 그 탭에서만 작업한다. 사용자가 같은 지시를 반복하며
강하게 확정한 규칙이다.

migrate.py의 chrome_js는 '첫 번째' postwrite 탭을 조준하므로 기존 탭이 남아 있으면
새 탭이 무시된다. 여기서 chrome_js를 '마지막' postwrite 탭 조준으로 바꿔치기한다.
새 탭은 창 끝에 열리므로 마지막 매치 = 새 탭이고, ensure_postwrite_tab의 raise
루프도 마지막 매치를 활성으로 남기므로 JS 조준과 CGEvent 클릭이 같은 탭을 본다.

usage: migrate_fresh_tab.py <TISTORY_URL> [--tags "..."] [기타 migrate.py 플래그]
(--clear는 여기서 금지: 전달돼도 제거한다)
"""
import sys, os, time, base64, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import migrate as M


def chrome_js_last(js, timeout=15):
    """마지막 postwrite 탭에서 JS 실행 (원본 migrate.chrome_js는 첫 탭 조준)."""
    b64 = base64.b64encode(js.encode()).decode()
    wrapped = f"eval(decodeURIComponent(escape(atob('{b64}'))))"
    script = (
        'tell application "Google Chrome"\n'
        "set tw to 0\nset tt to 0\n"
        "set wIdx to 0\n"
        "repeat with w in windows\n"
        "set wIdx to wIdx + 1\n"
        "set tIdx to 0\n"
        "repeat with t in tabs of w\n"
        "set tIdx to tIdx + 1\n"
        'if URL of t contains "/postwrite" then\n'
        "set tw to wIdx\nset tt to tIdx\n"
        "end if\nend repeat\nend repeat\n"
        'if tw is 0 then return "NO_TAB"\n'
        f'return execute tab tt of window tw javascript "{wrapped}"\n'
        "end tell"
    )
    out = subprocess.run(["osascript", "-e", script], capture_output=True,
                         text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"chrome_js: {out.stderr.strip()}")
    return out.stdout.strip()


def main():
    args = [a for a in sys.argv[1:] if a != "--clear"]
    if not args or args[0].startswith("--"):
        sys.exit("usage: migrate_fresh_tab.py <TISTORY_URL> [--tags ...]")

    M.chrome_js = chrome_js_last

    # 1. 새 탭 열기 (기존 탭은 손대지 않음)
    M.osa('tell application "Google Chrome"\nactivate\n'
          'tell window 1 to make new tab at end of tabs with properties '
          '{URL:"https://blog.naver.com/op5321/postwrite"}\n'
          "set active tab index of window 1 to (count of tabs of window 1)\nend tell")
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
