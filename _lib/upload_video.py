#!/usr/bin/env python3
"""네이버 동영상 업로더를 스크립트로 구동해 본문에 동영상을 넣는다.

사진과 달리 동영상은 클립보드 붙여넣기가 통하지 않는다. 네이버 자체 업로더
레이어를 열고 네이티브 파일 선택 창을 거쳐야 한다. 2026-08-21 실측으로 확인한
경로를 그대로 자동화한 것이다.

흐름과 각 단계에서 막혔던 지점:
  1. 툴바 button[data-name=video]를 JS로 클릭 -> 업로더 레이어(.se-popup-video-upload)
     여기까지는 합성 클릭으로 열린다.
  2. 레이어 안 "동영상 추가"(.nvu_btn_append.nvu_local)는 파일 선택 창을 여는 버튼이라
     브라우저가 사용자 제스처를 요구한다. JS 클릭은 무시되므로 CGEvent 실제 클릭이 필요하다.
  3. 뜬 파일 창은 Chrome 창에 붙은 시트인데 접근성으로 내부 요소가 안 보인다(버튼·필드 0개).
     그래도 키는 전달된다. 단 `tell process "Google Chrome"`을 명시해야 한다.
     그냥 keystroke를 쏘면 전면 앱(터미널)이 받아 버린다.
  4. 경로 입력은 슬래시(/) 키로 경로 창을 연 뒤 text field 1에 값을 직접 넣는다.
     파일명에 한글이 있으면 타이핑은 IME 때문에 깨지므로 값 설정이 안전하다.
     Return 두 번(경로 이동, 열기)으로 업로드가 시작된다.
  5. 업로드가 끝나면 제목이 필수다. input.nvu_inp에 native setter로 넣고 input 이벤트를 쏜 뒤
     "완료"(.nvu_btn_submit)를 누르면 본문에 se-video 컴포넌트가 생긴다.

동영상은 현재 캐럿 자리에 들어간다. 특정 위치에 넣으려면 이 스크립트를 부르기 전에
그 문단을 클릭해 캐럿을 옮겨 두면 된다.

사용:
  upload_video.py <영상파일> [제목]
"""
import json, os, sys, time

REPO = "/Users/bag-yoseb/Desktop/Project/personal/giraffe-skills"
sys.path.insert(0, f"{REPO}/tistory-to-naver/scripts")

import migrate as M

POPUP = ".se-popup-video-upload"


def frontmost():
    return M.osa('tell application "System Events" to get name of '
                 'first application process whose frontmost is true')


def ensure_chrome():
    for _ in range(4):
        if frontmost() == "Google Chrome":
            return True
        M.osa('tell application "Google Chrome" to activate')
        time.sleep(1.0)
    return False


def sheet_count():
    return M.osa('tell application "System Events" to tell process "Google Chrome" to '
                 'return (count of sheets of windows) as string')


def popup_text(limit=200):
    return M.chrome_js(
        f"(()=>{{const p=document.querySelector('{POPUP}');"
        "return p ? p.innerText.replace(/\\n+/g,' | ') : 'closed';})()")[:limit]


def open_uploader():
    r = M.chrome_js("(()=>{const b=document.querySelector('button[data-name=video]');"
                    "if(!b) return 'no-button'; b.click(); return 'clicked';})()")
    if r != "clicked":
        sys.exit(f"[ABORT] 동영상 툴바 버튼을 못 찾음: {r}")
    time.sleep(2.5)
    if "closed" in popup_text(40):
        sys.exit("[ABORT] 업로더 레이어가 안 열림")


def click_add_button():
    """파일 선택 창을 여는 버튼. 합성 클릭이 막히므로 실제 클릭으로 쏜다."""
    js = f"""
    (() => {{
      const b = document.querySelector('{POPUP} .nvu_btn_append.nvu_local');
      if (!b) return 'none';
      b.scrollIntoView({{block:'center'}});
      const r = b.getBoundingClientRect();
      return JSON.stringify({{
        x: Math.round(window.screenX + r.left + r.width/2),
        y: Math.round(window.screenY + (window.outerHeight - window.innerHeight) + r.top + r.height/2)
      }});
    }})()"""
    r = M.chrome_js(js)
    if r == "none":
        sys.exit("[ABORT] '동영상 추가' 버튼 없음")
    c = json.loads(r)
    if not ensure_chrome():
        sys.exit(f"[ABORT] 전면 앱이 Chrome이 아님({frontmost()})")
    M.click(c["x"], c["y"])
    time.sleep(2.0)
    if sheet_count() == "0":
        sys.exit("[ABORT] 파일 선택 창이 안 뜸")


def pick_file(path):
    """열기 창에서 경로를 직접 지정해 파일을 연다."""
    M.osa('tell application "Google Chrome" to activate')
    time.sleep(0.6)
    # 슬래시를 누르면 "폴더로 이동" 경로 창이 열린다 (Cmd+Shift+G와 같은 창).
    M.osa('tell application "System Events" to tell process "Google Chrome" to keystroke "/"')
    time.sleep(1.3)

    script = ('tell application "System Events" to tell process "Google Chrome"\n'
              'repeat with w in windows\n'
              'if (count of sheets of w) > 0 then\n'
              'set s to sheet 1 of w\n'
              'if (count of sheets of s) > 0 then\n'
              'set g to sheet 1 of s\n'
              'if (count of text fields of g) > 0 then\n'
              'set value of text field 1 of g to "%s"\n'
              'return "set"\n'
              'end if\n'
              'end if\n'
              'end if\n'
              'end repeat\n'
              'return "no-target"\n'
              'end tell') % path
    if M.osa(script) != "set":
        sys.exit("[ABORT] 경로 입력창을 못 찾음")

    time.sleep(0.8)
    M.osa('tell application "System Events" to tell process "Google Chrome" to key code 36')
    time.sleep(1.8)
    M.osa('tell application "System Events" to tell process "Google Chrome" to key code 36')
    time.sleep(3.0)
    if sheet_count() != "0":
        sys.exit("[ABORT] 파일 창이 안 닫힘. 경로를 확인할 것")


def wait_upload(timeout=600):
    for i in range(timeout // 5):
        t = popup_text(400)
        if "업로드 진행중" not in t:
            print(f"      업로드 완료 ({i*5}초)")
            return
        time.sleep(5)
    sys.exit("[ABORT] 업로드 타임아웃")


def submit(title):
    js = """
    (() => {
      const p = document.querySelector('%s');
      const i = p && p.querySelector('input.nvu_inp');
      if (!i) return 'no-input';
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(i, %s);
      i.dispatchEvent(new Event('input', {bubbles:true}));
      i.dispatchEvent(new Event('change', {bubbles:true}));
      return i.value;
    })()""" % (POPUP, json.dumps(title, ensure_ascii=False))
    got = M.chrome_js(js)
    if got != title:
        sys.exit(f"[ABORT] 제목 입력 실패: {got}")
    time.sleep(0.8)
    r = M.chrome_js(f"(()=>{{const b=document.querySelector('{POPUP} .nvu_btn_submit');"
                    "if(!b) return 'no-btn'; b.click(); return 'clicked';})()")
    if r != "clicked":
        sys.exit(f"[ABORT] 완료 버튼 클릭 실패: {r}")
    time.sleep(4.0)


def video_count():
    return int(M.chrome_js(
        "String(document.querySelectorAll('.se-component.se-video, "
        ".se-component.se-videoDetail').length)"))


def main():
    # 글쓰기 탭이 여럿이면 migrate.chrome_js는 첫 탭을 잡는다. upload_to_editor가
    # 넘겨주는 탭 id로 못박는다 (2026-09-03: 두 번째 글에서 1편 탭에 업로더를 연 사고).
    tab_id = os.environ.get("NAVER_TAB_ID")
    if tab_id:
        sys.path.insert(0, f"{REPO}/blog/scripts")
        from upload_to_editor import make_chrome_js
        M.chrome_js = make_chrome_js(int(tab_id))
    path = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else path.rsplit("/", 1)[-1].rsplit(".", 1)[0]

    before = video_count()
    print(f"[1/5] 업로더 열기 (현재 동영상 {before}개)")
    open_uploader()
    print("[2/5] 파일 선택 창 띄우기")
    click_add_button()
    print(f"[3/5] 파일 지정: {path}")
    pick_file(path)
    print("[4/5] 업로드 대기")
    wait_upload()
    print(f"[5/5] 제목 입력 후 삽입: {title}")
    submit(title)

    after = video_count()
    print(f"\n동영상 컴포넌트 {before} -> {after}")
    if after <= before:
        sys.exit("[ABORT] 본문에 동영상이 안 들어감")


if __name__ == "__main__":
    main()
