#!/usr/bin/env python3
"""네이버 글쓰기 새 탭을 '방송이 안 틀어진 크롬 창'에 여는 공용 모듈.

사용자는 치지직 같은 방송을 한 크롬 창에 틀어 두고 작업한다. 그 창에 새 탭을 열면
활성 탭이 바뀌어 시청이 끊긴다. 2026-09-26 사진 업로드 때 `window 1`에 그대로
열어서 사용자가 탭을 직접 다른 창으로 옮겨야 했다. 예전에는 창 고르기가
tistory-to-naver/migrate_fresh_tab.py에만 있고 blog/upload_to_editor.py는
window 1 고정이어서 경로마다 행동이 달랐다. 새 탭을 여는 모든 스크립트가 이 모듈을 쓴다.

기존 글쓰기 탭은 닫지도, 비우지도, 재사용하지도 않는다(사용자 하드룰). 새 탭이
비어 있지 않으면(임시저장 복원 등) 비우지 않고 예외를 던진다.

    from chrome_window import open_postwrite_tab
    tab_id, js = open_postwrite_tab()     # js(src, timeout=10) -> str, 그 탭에서만 실행
"""
import base64
import subprocess
import time

# 이 패턴이 URL에 있는 탭이 하나라도 있는 창은 사용자가 보고 있는 창으로 보고 피한다.
MEDIA_PATTERNS = (
    "chzzk.naver.com", "youtube.com/watch", "youtu.be/", "twitch.tv",
    "tv.naver.com", "netflix.com", "tving.com", "wavve.com", "laftel.net",
    "disneyplus.com", "coupangplay.com",
)

POSTWRITE_URL = "https://blog.naver.com/{blog_id}/postwrite"


def osa(script, timeout=15):
    out = subprocess.run(["osascript", "-e", script], capture_output=True,
                         text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"osascript: {out.stderr.strip()}")
    return out.stdout.strip()


def windows():
    """[(window id, [탭 URL...])]. 크롬 창 순서(앞에서부터)대로."""
    out = osa('tell application "Google Chrome"\nset s to ""\n'
              "repeat with w in windows\n"
              'set s to s & "|W|" & (id of w) & "|U|"\n'
              "repeat with t in tabs of w\n"
              'set s to s & (URL of t) & "|T|"\n'
              "end repeat\nend repeat\nreturn s\nend tell")
    wins = []
    for chunk in (out or "").split("|W|")[1:]:
        wid, _, rest = chunk.partition("|U|")
        wins.append((int(wid.strip()), [u for u in rest.split("|T|") if u]))
    return wins


def has_media(urls):
    return any(p in u for u in urls for p in MEDIA_PATTERNS)


def pick_target_window(explicit=None, log=print):
    """새 탭을 열 창 id. 방송 탭이 없는 첫 창, 없으면 새 창을 만든다.

    explicit은 사용자가 말하는 창 번호(1부터).
    """
    wins = windows()
    if explicit:
        if not 1 <= explicit <= len(wins):
            raise SystemExit(f"ABORT: {explicit}번 창은 없음 (현재 {len(wins)}개)")
        log(f"[창] {explicit}번 창 지정 (id {wins[explicit - 1][0]})")
        return wins[explicit - 1][0]
    for idx, (wid, urls) in enumerate(wins, start=1):
        if not has_media(urls):
            log(f"[창] {idx}번 창 선택 (id {wid}, 방송 탭 없음, 탭 {len(urls)}개)")
            return wid
    osa('tell application "Google Chrome" to make new window')
    time.sleep(1)
    wid = windows()[-1][0]
    log(f"[창] 모든 창에 방송 탭이 있어 새 창 생성 (id {wid})")
    return wid


def tab_js(tab_id):
    """그 탭 id에서만 JS를 실행하는 함수. 창을 옮겨도 탭 id는 유지된다."""
    def f(js_source, timeout=10):
        b64 = base64.b64encode(js_source.encode("utf-8")).decode("ascii")
        wrapped = f"eval(decodeURIComponent(escape(atob('{b64}'))))"
        out = osa('tell application "Google Chrome"\n'
                  "repeat with w in windows\nrepeat with t in tabs of w\n"
                  # `id of t is N`은 매칭이 안 된다. 정수로 캐스팅해 비교해야 잡힌다.
                  f"if (id of t as integer) = {tab_id} then\n"
                  f'return execute t javascript "{wrapped}"\n'
                  "end if\nend repeat\nend repeat\n"
                  'return "NO_TAB"\nend tell', timeout=timeout)
        if out == "NO_TAB":
            raise RuntimeError(f"탭 {tab_id}이 없음 (사용자가 닫았을 수 있음)")
        return out
    return f


JS_DISMISS = ('(function(){var b=Array.from(document.querySelectorAll("button"))'
              '.find(function(x){return x.offsetParent&&x.textContent.trim()==="취소";});'
              'if(b){b.click();return "dismissed";}return "no-dialog";})()')


def open_tab_front(url, explicit_window=None, log=print):
    """방송 없는 창에 새 탭을 열고 그 창을 맨 앞으로 올린다. (window id, tab id).

    'window 1의 활성 탭'에 JS를 쏘거나 화면 좌표를 클릭하는 스크립트(naver-to-naver,
    upload_draft)용이다. 방송 창은 뒤로 가도 자기 활성 탭이 그대로라 재생이 끊기지 않는다.
    """
    wid = pick_target_window(explicit_window, log)
    tab_id = int(osa('tell application "Google Chrome"\nactivate\n'
                     f"set tgt to (first window whose id is {wid})\n"
                     f'tell tgt to make new tab at end of tabs with properties {{URL:"{url}"}}\n'
                     "set active tab index of tgt to (count of tabs of tgt)\n"
                     "set index of tgt to 1\n"
                     "return id of last tab of tgt\nend tell"))
    return wid, tab_id


def open_postwrite_tab(blog_id="op5321", explicit_window=None, log=print):
    """방송 없는 창에 새 글쓰기 탭을 열고 (tab_id, js)를 돌려준다. 빈 에디터가 아니면 예외."""
    wid = pick_target_window(explicit_window, log)
    url = POSTWRITE_URL.format(blog_id=blog_id)
    tab_id = int(osa('tell application "Google Chrome"\n'
                     f"set tgt to (first window whose id is {wid})\n"
                     f'tell tgt to make new tab at end of tabs with properties {{URL:"{url}"}}\n'
                     "set active tab index of tgt to (count of tabs of tgt)\n"
                     "return id of last tab of tgt\nend tell"))
    js = tab_js(tab_id)
    for _ in range(90):   # 에디터 로딩이 30초를 넘기는 경우가 있다 (2026-09-03)
        time.sleep(1.0)
        try:
            if js("document.querySelector('.se-canvas') ? 'ready' : 'loading'") == "ready":
                break
        except RuntimeError:
            pass
    else:
        raise RuntimeError("글쓰기 탭이 안 뜸")
    # 임시저장 복원 물음은 늦게 뜰 수 있어 세 번 본다
    for _ in range(3):
        time.sleep(2)
        if js(JS_DISMISS) == "dismissed":
            log("[탭] 임시저장 복원 물음 취소")
            break
    n = js("String(document.querySelectorAll('.se-component').length)")
    if not n.isdigit() or int(n) > 2:
        raise RuntimeError(f"새 탭이 비어 있지 않음(컴포넌트 {n}). 비우지 않고 멈춤")
    log(f"[탭] 새 글쓰기 탭 id={tab_id} (창 {wid})")
    return tab_id, js
