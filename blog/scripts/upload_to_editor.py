#!/usr/bin/env python3
"""드래프트 폴더 하나를 네이버 글쓰기 창에 통째로 올린다.

blog/scripts/paste_to_naver.py는 "본문 붙여넣기"만 한다. 그 앞뒤로 매번 필요한
탭 확보, 포커스 검증, 제목 입력, 여행 날짜 줄 볼드, 스타일 패스, 결과 검증을
한 프로세스로 묶은 오케스트레이터다. tistory-to-naver/scripts/migrate.py의
검증된 함수(ensure_postwrite_tab, CGEvent 클릭, style_pass)를 그대로 재사용한다.

무인 실행 금지 규칙에 따라 각 단계에서 검증하고 실패하면 즉시 중단한다.
사진이 하나도 안 들어갔거나 제목이 안 박히면 계속 쏘지 않는다.

새 글은 **항상 새 창에 새 글쓰기 창을 열어서** 쓴다. 기존 글쓰기 탭을 재사용하거나
비우지 않는다. 사용자가 에디터에서 직접 쓰던 원고가 날아가는 사고가 있었다(2026-08-21).
기존 탭은 손대지 않으므로 사용자가 하던 작업은 그대로 남는다.

사용:
  upload_to_editor.py <draft_dir>

draft_dir 요구사항:
  script.md   본문 (blog 스킬 형식)
  meta.json   title_candidates[0]을 제목으로 쓰고, images.source_folder에서 사진을 읽는다

대본에 `[영상 자리 : 파일명.mp4]` 줄이 있고 meta.json에 videos_folder가 있으면
본문을 다 올린 뒤 그 자리를 실제 동영상으로 바꾼다. 동영상은 캐럿 위치에 삽입되므로
자리 문단을 통째로 선택해 지워 빈 문단에 캐럿을 남긴 뒤 업로더를 부른다.
"""
import json, re, subprocess, sys, time

REPO = "/Users/bag-yoseb/Desktop/Project/personal/giraffe-skills"
sys.path.insert(0, f"{REPO}/tistory-to-naver/scripts")

import migrate as M

KEY_B = 11

# 여행기 시리즈는 첫 줄에 "여행 날짜 : 2019.8.4"를 본문 크기 볼드로 둔다.
# 대본에 **...** 로 쓰면 19px 소제목으로 렌더되므로, 평문으로 붙인 뒤
# 그 줄만 실제 선택 + Cmd+B로 굵게 만든다.
JS_DATE_LINE = """
(() => {
  const p = Array.from(document.querySelectorAll('.se-text p'))
    .find(e => e.innerText.includes('여행 날짜'));
  if (!p) return 'none';
  p.scrollIntoView({block: 'center'});
  const r = p.getBoundingClientRect();
  return JSON.stringify({
    x: Math.round(window.screenX + r.left + Math.min(r.width/2, 80)),
    y: Math.round(window.screenY + (window.outerHeight - window.innerHeight) + r.top + r.height/2)
  });
})()"""

JS_DATE_BOLD = """
(() => {
  const p = Array.from(document.querySelectorAll('.se-text p'))
    .find(e => e.innerText.includes('여행 날짜'));
  return p ? String(p.innerHTML.includes('<b>')) : 'none';
})()"""


JS_VIDEO_SLOT = """
(() => {
  const p = Array.from(document.querySelectorAll('.se-text p'))
    .find(e => e.innerText.includes('[영상 자리'));
  if (!p) return 'none';
  p.scrollIntoView({block:'center'});
  const r = p.getBoundingClientRect();
  return JSON.stringify({
    text: p.innerText.trim(),
    x: Math.round(window.screenX + r.left + Math.min(r.width/2, 80)),
    y: Math.round(window.screenY + (window.outerHeight - window.innerHeight) + r.top + r.height/2)
  });
})()"""

JS_VIDEO_COUNT = ("String(document.querySelectorAll('.se-component.se-video, "
                  ".se-component.se-videoDetail').length)")


def open_fresh_window():
    """새 Chrome 창을 만들어 글쓰기 페이지를 연다.

    기존 글쓰기 탭을 재사용하지 않는 이유는 단순하다. 그 탭에는 사용자가 직접 쓰던
    원고가 들어 있을 수 있고, 한 번 비우면 되돌릴 방법이 없다.
    새 창을 만들면 그 창이 window 1이 되므로, URL로 탭을 찾는 migrate.chrome_js가
    항상 이 창의 글쓰기 탭을 먼저 집는다. 사용자의 기존 탭은 건드리지 않는다.
    """
    url = M.POSTWRITE_URL.format(blog_id=M.BLOG_ID)
    M.osa('tell application "Google Chrome" to make new window')
    time.sleep(1.0)
    M.osa(f'tell application "Google Chrome" to set URL of active tab of window 1 to "{url}"')
    for _ in range(25):
        time.sleep(1.0)
        try:
            if M.chrome_js("document.querySelector('.se-canvas') ? 'ready' : 'loading'") == "ready":
                break
        except Exception:
            pass
    else:
        print("[ABORT] 글쓰기 창이 안 뜸"); sys.exit(2)
    M.osa('tell application "Google Chrome" to set index of window 1 to 1')
    M.osa('tell application "Google Chrome" to activate')
    time.sleep(0.8)


def frontmost():
    return M.osa('tell application "System Events" to get name of '
                 'first application process whose frontmost is true')


def guard():
    """Chrome이 실제로 전면인지 확인한다.

    document.hasFocus()만 믿으면 다른 앱이 전면일 때도 true가 나와서
    CGEvent 클릭과 Cmd+V가 엉뚱한 앱으로 들어간다 (2026-07-07 카카오톡 사고).
    """
    for _ in range(4):
        if frontmost() == "Google Chrome":
            return True
        M.osa('tell application "Google Chrome" to activate')
        time.sleep(1.0)
    return False


def counts():
    return json.loads(M.chrome_js(M.JS_PASTE_COUNTS, timeout=8))


def place_videos(draft, meta):
    """대본의 `[영상 자리 : ...]`를 실제 동영상으로 바꾼다.

    자리 문단을 triple_click으로 통째로 선택해 지우면 빈 문단에 캐럿이 남는다.
    그 상태에서 업로더를 부르면 동영상이 정확히 그 자리에 들어간다.
    자리가 없어질 때까지 한 개씩 처리한다.
    """
    folder = meta.get("videos_folder")
    if not folder:
        print("      videos_folder 없음 -> 영상 자리는 그대로 둔다")
        return
    titles = {v.get("file"): v.get("title") for v in meta.get("videos", [])}

    done = 0
    for _ in range(20):
        r = M.chrome_js(JS_VIDEO_SLOT)
        if r == "none":
            break
        slot = json.loads(r)
        m = re.search(r"\[영상 자리\s*:\s*([^\]]+)\]", slot["text"])
        if not m:
            print(f"      [WARN] 자리 형식을 못 읽음: {slot['text'][:40]}"); break
        fname = m.group(1).strip()
        path = f"{folder.rstrip('/')}/{fname}"
        # 제목은 meta에 있으면 그걸 쓰고, 없으면 파일명에서 슬롯 접두어를 뗀다
        title = titles.get(fname) or fname.split("_", 2)[-1].rsplit(".", 1)[0]

        if not guard():
            print(f"[ERROR] 전면 앱이 Chrome이 아님({frontmost()}). 중단."); sys.exit(1)
        M.triple_click(slot["x"], slot["y"]); time.sleep(0.5)
        M.key(M.KEY_BACKSPACE); time.sleep(1.0)

        before = int(M.chrome_js(JS_VIDEO_COUNT))
        rc = subprocess.run([sys.executable, f"{REPO}/_lib/upload_video.py", path, title]).returncode
        after = int(M.chrome_js(JS_VIDEO_COUNT))
        if rc != 0 or after <= before:
            print(f"[ABORT] 영상 삽입 실패: {fname}"); sys.exit(6)
        done += 1
        print(f"      {fname} -> 삽입 완료 (동영상 {after}개)")
    print(f"      영상 {done}개 배치")


def main():
    draft = sys.argv[1].rstrip("/")
    meta = json.loads(open(f"{draft}/meta.json", encoding="utf-8").read())
    title = meta["title_candidates"][0]

    print("[1/7] 새 글쓰기 창 열기")
    open_fresh_window()
    M.chrome_js(M.JS_DISMISS_DIALOG)   # "작성 중인 글" 복구 물음은 취소
    time.sleep(0.6)
    if not guard():
        print(f"[ERROR] 전면 앱이 Chrome이 아님({frontmost()}). 중단."); sys.exit(1)
    if not M.wait_for_window_focus(retries=2):
        # 창은 전면인데 페이지가 키보드 포커스를 못 받은 경우가 있다(다른 앱 창을
        # 닫은 직후 등). 본문을 실제로 클릭하면 잡힌다.
        print("      페이지 포커스 없음 -> 본문 클릭으로 확보 시도")
        c = json.loads(M.chrome_js(M.JS_BODY_COORDS))
        M.click(c["x"], c["y"]); time.sleep(0.8)
        if M.chrome_js("String(document.hasFocus())") != "true":
            print("[ERROR] 클릭해도 페이지 포커스 없음. 중단."); sys.exit(1)
        print("      포커스 확보")

    n = int(M.chrome_js(M.JS_COMPONENT_COUNT))
    print(f"      컴포넌트 {n}개")
    if n > 2:
        # 새 창인데 내용이 있다는 건 복구 물음을 못 닫았다는 뜻이다.
        # 남의 원고일 수 있으니 절대 지우지 않고 멈춘다.
        print("[ABORT] 새 창인데 본문이 비어 있지 않음. 사람이 확인할 것."); sys.exit(3)

    print("[2/7] 제목 입력")
    M.copy_text(title)
    ok = False
    for _ in range(3):
        c = json.loads(M.chrome_js(M.JS_TITLE_COORDS))
        # triple_click으로 기존 제목 줄을 통째로 선택해야 재시도가 덧붙지 않는다.
        M.triple_click(c["x"], c["y"]); time.sleep(0.4)
        M.key(M.KEY_V, cmd=True)
        norm = lambda s: s.replace("\xa0", " ").strip()   # SE는 공백을 NBSP로 렌더
        for _ in range(10):
            time.sleep(0.4)
            if norm(M.chrome_js(M.JS_TITLE_TEXT)) == norm(title):
                ok = True; break
        if ok: break
        M.osa('tell application "Google Chrome" to activate'); time.sleep(1.0)
    if not ok:
        print("[ABORT] 제목 입력 실패. 중단."); sys.exit(4)
    print(f"      {title}")

    print(f"[3/7] 본문 붙여넣기 (사진 {meta['images']['count']}장)")
    if not guard():
        print(f"[ERROR] 전면 앱이 Chrome이 아님({frontmost()}). 중단."); sys.exit(1)
    c = json.loads(M.chrome_js(M.JS_BODY_COORDS))
    M.click(c["x"], c["y"]); time.sleep(0.6)
    before = counts()
    subprocess.run([sys.executable, f"{REPO}/blog/scripts/paste_to_naver.py", draft])
    time.sleep(2.0)
    after = counts()
    print(f"      이미지 {before['img']} -> {after['img']} / 문단 {before['p']} -> {after['p']}")
    if after["img"] - before["img"] == 0:
        print("[ABORT] 이미지가 하나도 안 들어감."); sys.exit(5)

    print("[4/7] 여행 날짜 줄 볼드")
    r = M.chrome_js(JS_DATE_LINE)
    if r == "none":
        print("      날짜 줄 없음, 건너뜀")
    else:
        if not guard():
            print(f"[ERROR] 전면 앱이 Chrome이 아님({frontmost()}). 중단."); sys.exit(1)
        d = json.loads(r)
        M.triple_click(d["x"], d["y"]); time.sleep(0.5)
        M.key(KEY_B, cmd=True); time.sleep(0.8)
        print(f"      볼드 적용: {M.chrome_js(JS_DATE_BOLD)}")
        M.chrome_js(M.JS_DESELECT)

    print("[5/7] 영상 자리 채우기")
    place_videos(draft, meta)

    print("[6/7] 스타일 패스 (구분선 line3+가운데, 사진 가운데)")
    styled = M.style_pass()
    print(f"      구분선 {styled['hr']}개, 사진 {styled['img']}개")

    print("[7/7] 최종 확인")
    time.sleep(1.5)
    fin = counts()
    body = M.chrome_js("document.querySelector('.se-canvas').innerText")
    print(f"      이미지 {fin['img']}장 / 문단 {fin['p']}개")
    print(f"      '[영상 자리' {body.count('[영상 자리')}회 / '[이미지 누락' {body.count('[이미지 누락')}회")
    print("\n발행 버튼은 사용자가 직접 누른다.")


if __name__ == "__main__":
    main()
