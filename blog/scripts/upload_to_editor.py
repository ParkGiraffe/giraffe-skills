#!/usr/bin/env python3
"""드래프트 폴더 하나를 네이버 글쓰기 창에 통째로 올린다.

blog/scripts/paste_to_naver.py는 "본문 붙여넣기"만 한다. 그 앞뒤로 매번 필요한
탭 확보, 포커스 검증, 제목 입력, 여행 날짜 줄 볼드, 스타일 패스, 결과 검증을
한 프로세스로 묶은 오케스트레이터다. tistory-to-naver/scripts/migrate.py의
검증된 함수(ensure_postwrite_tab, CGEvent 클릭, style_pass)를 그대로 재사용한다.

무인 실행 금지 규칙에 따라 각 단계에서 검증하고 실패하면 즉시 중단한다.
사진이 하나도 안 들어갔거나 제목이 안 박히면 계속 쏘지 않는다.

새 글은 **항상 새 탭을 열어서** 쓴다. 기존 글쓰기 탭을 재사용하거나 비우지 않는다.
사용자가 에디터에서 직접 쓰던 원고가 날아가는 사고가 있었다(2026-08-21).
기존 탭은 손대지 않으므로 사용자가 하던 작업은 그대로 남는다.

글쓰기 탭이 여러 개 열려 있어도 헷갈리지 않도록, 새로 연 탭의 **id를 잡아 두고**
그 id로만 JS를 실행한다(migrate.chrome_js는 URL로 첫 탭을 찾기 때문에 그대로 두면
남의 탭을 집는다). 탭을 다른 창으로 옮겨도 id는 유지되므로 창 순서에 영향받지 않는다.

사용:
  upload_to_editor.py <draft_dir> [--save]   (--save: 마지막에 상단 "저장"으로 임시저장)

draft_dir 요구사항:
  script.md   본문 (blog 스킬 형식)
  meta.json   title_candidates[0]을 제목으로 쓰고, images.source_folder에서 사진을 읽는다

대본에 `[영상 자리 : 파일명.mp4]` 줄이 있고 meta.json에 videos_folder가 있으면
본문을 다 올린 뒤 그 자리를 실제 동영상으로 바꾼다. 동영상은 캐럿 위치에 삽입되므로
자리 문단을 통째로 선택해 지워 빈 문단에 캐럿을 남긴 뒤 업로더를 부른다.
"""
import base64, json, os, re, subprocess, sys, time
import pathlib

REPO = str(pathlib.Path(__file__).resolve().parents[2])
sys.path.insert(0, f"{REPO}/tistory-to-naver/scripts")
sys.path.insert(0, f"{REPO}/_lib")

import migrate as M
import se_doc
import chrome_window

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


# 상단 "저장" 버튼 = 임시저장. 클래스 뒤 해시는 빌드마다 바뀌므로 접두어로 찾는다 (2026-09-23)
JS_SAVE_CLICK = """
(() => { const b = document.querySelector('button[class^="save_btn"], button[class*=" save_btn"]');
  if (!b) return 'none'; b.click(); return 'clicked'; })()"""
JS_SAVE_COUNT = """
(() => { const b = document.querySelector('button[class^="save_count_btn"], button[class*=" save_count_btn"]');
  return b ? b.getAttribute('aria-label') : 'none'; })()"""
JS_SAVE_BTN_TEXT = """
(() => { const b = document.querySelector('button[class^="save_btn"], button[class*=" save_btn"]');
  return b ? b.innerText.replace(/\\s+/g, ' ').trim() : 'none'; })()"""


# 문서 빌더(se_doc.skeleton_from_ops)가 옮기지 못하는 인라인 서식. 하나라도 있으면 붙여넣기 경로로 간다
RICH_INLINE_RE = re.compile(r"`[^`\n]+`|\[[^\]\n]+\]\([^)\s]+\)|<u>|<mark>|<span style=|(?<![*])\*[^*\n]+\*(?![*])")


CURRENT_TAB_ID = None   # open_fresh_tab이 연 탭. upload_video.py에 환경변수로 넘긴다


def make_chrome_js(tab_id):
    """지정한 탭에서만 JS를 실행하는 함수를 만든다.

    migrate.chrome_js는 "URL에 /postwrite가 든 첫 탭"을 쓴다. 글쓰기 탭이 여러 개면
    남의 탭에 글을 쏟아붓게 되므로, 우리가 연 탭의 id로 못박는다.
    """
    def f(js_source, timeout=10):
        b64 = base64.b64encode(js_source.encode("utf-8")).decode("ascii")
        wrapped = f"eval(decodeURIComponent(escape(atob('{b64}'))))"
        script = ('tell application "Google Chrome"\n'
                  "repeat with w in windows\n"
                  "repeat with t in tabs of w\n"
                  # `id of t is N`은 매칭에 실패한다. 정수로 캐스팅해 비교해야 잡힌다.
                  f"if (id of t as integer) = {tab_id} then\n"
                  f'return execute t javascript "{wrapped}"\n'
                  "end if\nend repeat\nend repeat\n"
                  'return "NO_TAB"\n'
                  "end tell")
        out = subprocess.run(["osascript", "-e", script], capture_output=True,
                             text=True, timeout=timeout)
        if out.returncode != 0:
            raise RuntimeError(f"chrome_js: {out.stderr.strip()}")
        return out.stdout.strip()
    return f


def open_fresh_tab():
    """새 탭에 글쓰기 페이지를 연다. 기존 탭은 건드리지 않는다.

    그 탭에는 사용자가 직접 쓰던 원고가 들어 있을 수 있고, 한 번 비우면 되돌릴 방법이 없다.
    임시저장도 슬롯이 몇 개뿐이라 안전망이 못 된다. 새로 여는 편이 언제나 싸다.

    창은 _lib/chrome_window가 고른다. 치지직 등 방송이 틀어진 창은 피한다. 예전에는
    window 1에 고정으로 열어 방송 창의 활성 탭을 빼앗았다(2026-09-26).
    """
    try:
        tab_id, js = chrome_window.open_postwrite_tab(M.BLOG_ID)
    except RuntimeError as e:
        print(f"[ABORT] {e}"); sys.exit(2)
    # 이후 M의 모든 JS 호출(style_pass 등)이 이 탭만 보게 못박는다
    M.chrome_js = js
    global CURRENT_TAB_ID
    CURRENT_TAB_ID = tab_id
    time.sleep(0.5)


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


def resolve_videos_folder(draft, value):
    """meta.json의 videos_folder를 초안 폴더 기준으로 해석한다. 절대 경로는 그대로 쓴다."""
    if not value:
        return None
    p = pathlib.Path(value).expanduser()
    if not p.is_absolute():
        p = pathlib.Path(draft) / p
    return p.resolve()


def place_videos(draft, meta):
    """대본의 `[영상 자리 : ...]`를 실제 동영상으로 바꾼다.

    자리 문단을 triple_click으로 통째로 선택해 지우면 빈 문단에 캐럿이 남는다.
    그 상태에서 업로더를 부르면 동영상이 정확히 그 자리에 들어간다.
    자리가 없어질 때까지 한 개씩 처리한다.
    """
    folder = resolve_videos_folder(draft, meta.get("videos_folder"))
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
        path = str(folder / fname)
        # 제목은 meta에 있으면 그걸 쓰고, 없으면 파일명에서 슬롯 접두어를 뗀다
        title = titles.get(fname) or fname.split("_", 2)[-1].rsplit(".", 1)[0]

        if not guard():
            print(f"[ERROR] 전면 앱이 Chrome이 아님({frontmost()}). 중단."); sys.exit(1)
        M.triple_click(slot["x"], slot["y"]); time.sleep(0.5)
        M.key(M.KEY_BACKSPACE); time.sleep(1.0)

        before = int(M.chrome_js(JS_VIDEO_COUNT))
        rc = subprocess.run([sys.executable, f"{REPO}/_lib/upload_video.py", path, title],
                            env={**os.environ, "NAVER_TAB_ID": str(CURRENT_TAB_ID)}).returncode
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

    # 기본은 에디터 API로 문서를 통째로 쓴다(se_doc.write_document). 포커스·클립보드를 안 쓰므로
    # 업로드 중 다른 창을 만져도 글이 빠지지 않는다. --paste는 예전 클립보드 붙여넣기 경로다.
    use_paste = "--paste" in sys.argv
    body = open(f"{draft}/script.md", encoding="utf-8").read()
    if not use_paste and RICH_INLINE_RE.search(re.sub(r"<!--.*?-->", "", body, flags=re.S)):
        # 문서 빌더는 굵게(**)만 옮긴다. 코드·링크·밑줄·색 같은 서식은 붙여넣기 경로가 살린다.
        print("      본문에 인라인 서식(코드·링크·밑줄·색·기울임)이 있어 붙여넣기 방식으로 올린다")
        use_paste = True

    print("[1/8] 새 글쓰기 탭 열기")
    open_fresh_tab()
    M.chrome_js(M.JS_DISMISS_DIALOG)   # "작성 중인 글" 복구 물음은 취소
    time.sleep(0.6)
    if use_paste and not guard():
        print(f"[ERROR] 전면 앱이 Chrome이 아님({frontmost()}). 중단."); sys.exit(1)
    if use_paste and not M.wait_for_window_focus(retries=2):
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
        # 새 탭인데 내용이 있다는 건 복구 물음을 못 닫았다는 뜻이다.
        # 남의 원고일 수 있으니 절대 지우지 않고 멈춘다.
        print("[ABORT] 새 탭인데 본문이 비어 있지 않음. 사람이 확인할 것."); sys.exit(3)

    if not use_paste:
        write_via_api(draft, meta, title)
    else:
        paste_title_and_body(draft, meta, title)
    finish(draft, meta, use_paste)


def place_videos_api(draft, meta):
    """파일 선택 창 없이 영상을 올리고, 각 영상을 자기 [영상 자리] 문단으로 옮긴다."""
    slots = re.findall(r"^\s*\[영상 자리\s*:\s*([^\]]+)\]\s*$",
                       open(f"{draft}/script.md", encoding="utf-8").read(), re.M)
    if not slots:
        print("      영상 자리 없음"); return
    titles = {v.get("file"): v.get("title") for v in meta.get("videos", [])}
    folder = resolve_videos_folder(draft, meta.get("videos_folder")) or pathlib.Path(draft)
    items = []
    for f in (x.strip() for x in slots):
        if not (folder / f).exists():
            print(f"[ABORT] 영상 파일 없음: {folder / f}"); sys.exit(6)
        items.append({"file": f, "title": titles.get(f) or f.split("_", 2)[-1].rsplit(".", 1)[0]})
    if len({i["title"] for i in items}) != len(items):
        print("[ABORT] 영상 제목이 겹침. 제목으로 영상을 찾아 옮기므로 모두 달라야 한다"); sys.exit(6)
    srv, port = se_doc.serve_dir(folder)
    try:
        for it in items:
            se_doc.upload_video(M.chrome_js, port, it["file"], it["title"])
    except Exception as e:
        print(f"[ABORT] 영상 업로드 실패: {e}"); sys.exit(6)
    finally:
        srv.shutdown()
    r = se_doc.place_videos_at_slots(M.chrome_js, items)
    if not r.get("ok"):
        print(f"[ABORT] 영상 배치 실패: {r.get('err')}"); sys.exit(6)
    print(f"      영상 {len(r['placed'])}개를 자리에 배치")


def write_via_api(draft, meta, title):
    import importlib.util
    spec = importlib.util.spec_from_file_location("paste_to_naver", f"{REPO}/blog/scripts/paste_to_naver.py")
    PN = importlib.util.module_from_spec(spec); spec.loader.exec_module(PN)
    md = open(f"{draft}/script.md", encoding="utf-8").read()
    images_dir = PN.resolve_images_dir(pathlib.Path(draft), None)
    ops = PN.parse_to_ops(md, images_dir)
    missing = [o[1] for o in ops if o[0] == "p" and o[1].startswith("[이미지 누락")]
    if missing:
        print(f"[ABORT] 대본의 사진 파일이 없음: {missing}"); sys.exit(5)
    print(f"[2-3/8] 제목·본문을 에디터 문서 데이터로 쓰기 (사진 {meta['images']['count']}장)")
    try:
        n = se_doc.write_document(M.chrome_js, title, ops)
    except Exception as e:
        print(f"[ABORT] {e}"); sys.exit(5)
    norm = lambda s: s.replace("\xa0", " ").strip()
    got = norm(M.chrome_js(M.JS_TITLE_TEXT))
    print(f"      제목: {got}")
    if got != norm(title):
        print("[ABORT] 제목이 다르게 들어감."); sys.exit(4)
    if n != meta["images"]["count"]:
        print(f"[ABORT] 사진 {n}장 != meta {meta['images']['count']}장"); sys.exit(5)


def paste_title_and_body(draft, meta, title):
    print("[2/8] 제목 입력")
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

    print(f"[3/8] 본문 붙여넣기 (사진 {meta['images']['count']}장)")
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
    if after["img"] - before["img"] != meta["images"]["count"]:
        # 포커스가 중간에 다른 창으로 넘어가면 뒤쪽 조각이 통째로 빠진다 (2026-09-23)
        print(f"[ABORT] 사진 {after['img'] - before['img']}장만 들어감 (대본 {meta['images']['count']}장)."); sys.exit(5)


def finish(draft, meta, use_paste=True):

    print("[4/8] 여행 날짜 줄 볼드")
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

    print("[5/8] 영상 자리 채우기")
    if use_paste:
        place_videos(draft, meta)
    else:
        place_videos_api(draft, meta)

    print("[6/8] 두 장 묶음, 영상 순서 (에디터 문서 데이터)")
    script = open(f"{draft}/script.md", encoding="utf-8").read()
    titles = {v.get("file"): v.get("title") for v in meta.get("videos", [])}
    plan = se_doc.plan_from_markdown(script, titles)
    rep = se_doc.fix_media(M.chrome_js, plan["expect_images"], plan["pairs"], plan["videos"])
    if not rep.get("ok"):
        print(f"[ABORT] 문서 패스 실패: {rep.get('err')}"); sys.exit(7)
    print(f"      묶음 {rep['strips']}/{len(plan['pairs'])}개, 옮긴 영상 {rep['moved'] or '없음'}")
    if rep.get("video_check"):
        print(f"      [WARN] 영상 순서 검증 못 함: {rep['video_check']}")
    if rep["skipped"]:
        print(f"      [WARN] 묶지 못한 쌍: {rep['skipped']}")

    print("[7/8] 스타일 패스 (구분선 line3+가운데, 사진 가운데)")
    styled = M.style_pass()
    print(f"      구분선 {styled['hr']}개, 사진 {styled['img']}개")

    print("[8/8] 최종 확인")
    time.sleep(1.5)
    fin = counts()
    body = M.chrome_js("document.querySelector('.se-canvas').innerText")
    print(f"      이미지 {fin['img']}장 / 문단 {fin['p']}개")
    print(f"      '[영상 자리' {body.count('[영상 자리')}회 / '[이미지 누락' {body.count('[이미지 누락')}회")
    seq = se_doc.media_sequence(M.chrome_js)
    if seq == plan["sequence"]:
        print(f"      미디어 순서 대본과 일치 ({len(seq)}개)")
    else:
        print(f"[WARN] 미디어 순서 불일치\n      대본 {' '.join(plan['sequence'])}\n      문서 {' '.join(seq)}")
    if "--save" in sys.argv:
        print("[+] 임시저장")
        if M.chrome_js(JS_SAVE_CLICK) != "clicked":
            print("[WARN] 저장 버튼을 못 찾음. 직접 저장할 것.")
        else:
            time.sleep(3.0)
            print(f"      임시저장 목록: {M.chrome_js(JS_SAVE_COUNT)}")
    print("\n발행 버튼은 사용자가 직접 누른다.")


if __name__ == "__main__":
    main()
