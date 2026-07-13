#!/usr/bin/env python3
"""naver-to-naver 완전 마이그레이션 — 원본 컴포넌트를 한 줄씩 서식 그대로 복붙.

구조 (markdown 중간 변환 없음):
  원본 se-component를 DOM 순서로 걸으면서
  - se-text          → 문단마다 원본 서식(폰트크기·볼드·색·배경색·정렬·빈줄 개수)을
                        그대로 보존한 HTML을 클립보드에 올려 Cmd+V
  - se-horizontalLine → <hr> 복붙 (발행 전 스타일 패스가 line3+center로)
  - se-image/Strip/sticker → 원본 이미지(postfiles ?type=w3840, GIF 애니메이션 보존,
                        스티커는 storep ?type=p100_100)를 다운로드해 파일 복붙(네이버가 재업로드)
  붙인 뒤: 이미지 가운데정렬 + 구분선 line3 스타일 패스 → 제목 입력 → 정합성 검증 리포트.

정렬은 붙여넣기 단계에서 해결한다 — 실측(2026-07-13): 네이버 paste 정규화는
<p align="center">, <center>, <div style="text-align:center">를 살려주고
class="se-text-paragraph-align-center"만 제거한다. 그래서 align 속성을 쓴다.

사용법:
  migrate.py <URL_또는_logNo> [--blog-id op5321] [--html <완전본.html>] [--dry-run]

주의:
  - CGEvent 실제 입력 사용: 실행 중 마우스·키보드 금지
  - 발행은 하지 않는다(검토 후 사용자가 직접)
  - m.blog SSR이 긴 글 텍스트를 비운 골격을 줄 수 있음 → 자동 재시도, 안 되면 --html
"""
import re, sys, json, time, argparse, base64, hashlib, pathlib, subprocess
import html as H

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "blog" / "scripts"))
import paste_to_naver as PN          # copy_html_to_clipboard / copy_image_file_to_clipboard
import Quartz

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
REFERER = "https://blog.naver.com/"
CACHE = pathlib.Path.home() / ".cache" / "naver-to-naver"
ORIG = CACHE / "orig"
USE_CENSORED = False   # --censored 명시 시에만 가려진 캐시 사용(검열은 사용자가 직접 요청할 때만)

MEDIA_RE = re.compile(r'https?://([a-z0-9-]+\.pstatic\.net)/([^"?\s\\]+\.(?:jpe?g|png|gif))', re.I)
P_RE = re.compile(r'<p([^>]*class="se-text-paragraph[^"]*"[^>]*)>(.*?)</p>', re.S)
SPAN_RE = re.compile(r'<span([^>]*)>(.*?)</span>', re.S)
ZW = "​﻿"


# ---------------------------------------------------------------- osascript
def osa(script):
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True)


def chrome_js(js, timeout=15):
    b64 = base64.b64encode(js.encode()).decode()
    r = subprocess.run(
        ["osascript", "-e",
         'tell application "Google Chrome" to execute active tab of window 1 javascript '
         f'"eval(decodeURIComponent(escape(atob(\'{b64}\'))))"'],
        capture_output=True, text=True, timeout=timeout)
    return (r.stdout or r.stderr).strip()


def click_at(x, y, clicks=1):
    for c in range(1, clicks + 1):
        for t in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            ev = Quartz.CGEventCreateMouseEvent(None, t, (x, y), Quartz.kCGMouseButtonLeft)
            Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventClickState, c)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.05)


def cmd_v():
    osa('tell application "System Events" to key code 9 using command down')


# ---------------------------------------------------------------- fetch
def curl(url, out=None):
    cmd = ["curl", "-sSL", "-A", UA, "-e", REFERER]
    if out:
        cmd += ["-o", str(out)]
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True, text=(out is None))


def content_complete(html):
    """내용 문단(볼드·큰폰트)이 비어있으면 SSR 골격."""
    ps = re.findall(
        r'<p[^>]*class="se-text-paragraph[^"]*"[^>]*>((?:(?!</p>).)*?(?:<b>|se-fs-fs(?:19|2\d|[3-9]\d))(?:(?!</p>).)*?)</p>',
        html, re.S)
    empty = sum(1 for p in ps
                if not re.sub(r"<[^>]+>", "", p).translate(str.maketrans("", "", ZW)).strip())
    return not (empty >= 4 and ps and empty > len(ps) * 0.15)


def fetch_source(blog_id, log, html_path=None, retries=8):
    if html_path:
        return pathlib.Path(html_path).read_text(encoding="utf-8", errors="replace")
    for i in range(retries):
        r = curl(f"https://m.blog.naver.com/{blog_id}/{log}")
        h = r.stdout or ""
        if len(h) > 50000 and content_complete(h):
            print(f"[fetch] 완전본 확보 (시도 {i+1})")
            return h
        print(f"[fetch] 시도 {i+1}: {'골격(텍스트 빈 문단)' if len(h) > 50000 else '실패'} — 재시도")
        time.sleep(2)
    sys.exit("완전본 fetch 실패. 브라우저에서 글을 끝까지 스크롤해 저장한 HTML을 --html 로 주세요.")


# ---------------------------------------------------------------- 이미지 원본
def head_len(url):
    r = subprocess.run(["curl", "-sI", "-A", UA, "-e", REFERER, url], capture_output=True, text=True)
    code, length = None, 0
    for ln in r.stdout.splitlines():
        if ln.upper().startswith("HTTP"):
            p = ln.split()
            code = p[1] if len(p) > 1 else None
        if ln.lower().startswith("content-length"):
            try:
                length = int(ln.split(":", 1)[1].strip())
            except ValueError:
                pass
    return code, length


def download_original(dom, path):
    """원본 화질로 다운로드. 반환: 로컬 파일 경로 또는 None."""
    CACHE.mkdir(parents=True, exist_ok=True)
    ext = pathlib.Path(path).suffix.lower() or ".jpg"
    dest = CACHE / (hashlib.sha1(path.encode()).hexdigest()[:20] + ext)
    if dest.exists() and dest.stat().st_size > 500:
        bak = ORIG / dest.name
        if not USE_CENSORED and bak.exists():
            return bak                     # 검열본이 캐시에 있어도 기본은 원본(명시 요청시에만 검열)
        return dest
    if "storep-phinf" in dom:                     # OGQ 스티커: type 필수, HEAD 미지원
        for q in ("?type=p100_100", "?type=f120_120"):
            curl(f"https://{dom}/{path}{q}", out=dest)
            if dest.exists() and dest.stat().st_size > 500:
                return dest
        return None
    cands = [f"https://postfiles.pstatic.net/{path}?type=w3840",
             f"https://blogfiles.pstatic.net/{path}",
             f"https://mblogthumb-phinf.pstatic.net/{path}?type=w966"]
    nos = re.sub(r"_s(\.[a-zA-Z]+)$", r"\1", path)
    if nos != path:
        cands = [f"https://postfiles.pstatic.net/{nos}?type=w3840",
                 f"https://blogfiles.pstatic.net/{nos}"] + cands
    best, best_len = None, 0
    for v in cands:
        c, l = head_len(v)
        if c == "200" and l > best_len:
            best, best_len = v, l
    if not best:
        return None
    curl(best, out=dest)
    return dest if dest.exists() and dest.stat().st_size > 500 else None


# ---------------------------------------------------------------- 원본 → 청크
def components(html):
    starts = [m.start() for m in re.finditer(r'<div class="se-component ', html)]
    starts.append(len(html))
    for i in range(len(starts) - 1):
        blk = html[starts[i]:starts[i + 1]]
        m = re.match(r'<div class="se-component (se-[A-Za-z]+)', blk)
        yield (m.group(1) if m else "unknown"), blk


def media_in(blk):
    seen, out = set(), []
    for m in MEDIA_RE.finditer(blk):
        dom, path = m.group(1), m.group(2)
        if path.lower() in seen:
            continue
        seen.add(path.lower())
        out.append((dom, path))
    return out


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _plain(seg):
    t = H.unescape(re.sub(r"<[^>]+>", "", seg))
    return t.translate(str.maketrans("", "", ZW)).replace("\xa0", " ")


def render_inner(seg):
    """span 내부: <b>만 보존, 나머지 태그 제거, 텍스트 이스케이프."""
    out, pos = [], 0
    for m in re.finditer(r"<b>(.*?)</b>", seg, re.S):
        out.append(esc(_plain(seg[pos:m.start()])))
        inner = esc(_plain(m.group(1)))
        if inner.strip():
            out.append(f"<b>{inner}</b>")
        pos = m.end()
    out.append(esc(_plain(seg[pos:])))
    return "".join(out)


def render_paragraph(p_attrs, p_inner):
    """원본 문단 → (충실한 HTML, plain텍스트). 빈 문단은 <p><br></p> 스페이서."""
    align = ""
    if "se-text-paragraph-align-center" in p_attrs:
        align = ' align="center"'        # class는 paste에서 제거되지만 align 속성은 생존(실측)
    elif "se-text-paragraph-align-right" in p_attrs:
        align = ' align="right"'
    spans, plain_all, is_hl = [], "", False
    pos = 0
    for sm in SPAN_RE.finditer(p_inner):
        # 스팬 사이 텍스트 노드 보존 — 해시태그는 <span>#태그</span> <span>#태그</span>처럼
        # 스팬 '사이'의 공백으로 구분된다. 버리면 #태그#태그로 붙어 네이버 태그 자동인식이 깨짐(실사고).
        gap = _plain(p_inner[pos:sm.start()])
        pos = sm.end()
        if gap:
            spans.append(esc(gap))
            plain_all += gap.strip()
        sattr, sinner = sm.group(1), sm.group(2)
        fsm = re.search(r"se-fs-fs(\d+)", sattr)
        fs = int(fsm.group(1)) if fsm else 15
        cm = re.search(r"(?<!-)color:\s*(#[0-9a-fA-F]{3,8})", sattr)
        color = cm.group(1) if cm else "#212529"
        if re.search(r"background-color:\s*#[0-9a-fA-F]{3,8}", sattr):
            is_hl = True                          # 노란배경 소제목 — 나중에 하이라이트 패스로 입힘
        inner = render_inner(sinner)
        raw = re.sub(r"<[^>]+>", "", inner)
        plain = raw.strip()
        plain_all += plain
        if not plain:
            if raw:                        # 공백만 있는 스팬도 구분 공백으로 보존
                spans.append(" ")
            continue
        whole_b = bool(re.fullmatch(r"\s*<b>.*</b>\s*", sinner, re.S))
        # background-color는 절대 넣지 않는다(transparent 포함) — SE paste 파이프라인이
        # 연속 붙여넣기 중 하이라이트를 전체에 고착시키는 사고의 원인(실측 2026-07-13).
        # 노란배경은 붙인 후 highlight_pass가 진짜 선택+팔레트로 입힌다.
        style = f"font-size:{fs}px;color:{color};"
        if not whole_b:
            style = "font-weight:normal;" + style
        spans.append(f'<span style="{style}">{inner}</span>')
    tail = _plain(p_inner[pos:]) if pos else ""
    if tail.strip():
        spans.append(esc(tail))
        plain_all += tail.strip()
    if not plain_all.strip():
        return "<p><br></p>", "", False
    return f"<p{align}>{''.join(spans)}</p>", plain_all.strip(), is_hl


def build_chunks(html):
    """([('html', str, plains) | ('img', path)], stats, hl_texts) — 원본 순서 그대로."""
    chunks, unhandled, hl_texts = [], {}, []
    stats = {"img": 0, "gif": 0, "sticker": 0, "hr": 0, "para": 0, "spacer": 0, "fail": []}
    for kind, blk in components(html):
        if kind == "se-documentTitle":
            continue
        if kind == "se-horizontalLine":
            chunks.append(("html", "<hr>", []))
            stats["hr"] += 1
            continue
        if kind in ("se-image", "se-imageStrip", "se-sticker"):
            for dom, path in media_in(blk):
                f = download_original(dom, path)
                if f:
                    chunks.append(("img", str(f), []))
                    stats["img"] += 1
                    if f.suffix == ".gif":
                        stats["gif"] += 1
                    if "storep-phinf" in dom:
                        stats["sticker"] += 1
                else:
                    stats["fail"].append(f"{dom}/{path[:60]}")
            caps, plains = [], []
            for pm in P_RE.finditer(blk):                 # 미디어 캡션("짤 출처" 등)
                ph, pl, hl = render_paragraph(pm.group(1), pm.group(2))
                if pl:
                    caps.append(ph)
                    plains.append(pl)
                    stats["para"] += 1
                    if hl:
                        hl_texts.append(pl)
            if caps:
                chunks.append(("html", "".join(caps), plains))
            continue
        if kind == "se-text":
            ps, plains = [], []
            for pm in P_RE.finditer(blk):
                ph, pl, hl = render_paragraph(pm.group(1), pm.group(2))
                ps.append(ph)
                if pl:
                    plains.append(pl)
                    stats["para"] += 1
                    if hl:
                        hl_texts.append(pl)
                else:
                    stats["spacer"] += 1
            if ps:
                chunks.append(("html", "".join(ps), plains))
            continue
        unhandled[kind] = unhandled.get(kind, 0) + 1
    if unhandled:
        print(f"[주의] 미지원 컴포넌트 스킵: {unhandled}")
    # 인접 html 청크 병합(붙여넣기 횟수 절감; 순서 불변)
    merged = []
    for c in chunks:
        if c[0] == "html" and merged and merged[-1][0] == "html":
            merged[-1] = ("html", merged[-1][1] + c[1], merged[-1][2] + c[2])
        else:
            merged.append(c)
    return merged, stats, hl_texts


def verify_chunks_vs_source(html, chunks):
    """오프라인 검증: 원본의 모든 비어있지 않은 문단이 청크에 순서대로 있는가."""
    def norm(s):
        return re.sub(r"\s+", "", s).translate(str.maketrans("", "", ZW))
    src = []
    for kind, blk in components(html):
        if kind == "se-documentTitle":
            continue
        for pm in P_RE.finditer(blk):
            t = norm(_plain(pm.group(2)))
            if t:
                src.append(t)
    flat = norm("".join(p for c in chunks if c[0] == "html" for p in c[2]))
    missing = [t for t in src if t not in flat]
    return src, missing


# ---------------------------------------------------------------- 에디터 조작
def open_fresh_editor(blog_id):
    osa(f'''tell application "Google Chrome"
      activate
      make new tab at end of tabs of window 1 with properties {{URL:"https://blog.naver.com/{blog_id}/postwrite"}}
      set active tab index of window 1 to (count of tabs of window 1)
    end tell''')
    time.sleep(6)
    chrome_js('(function(){var b=Array.from(document.querySelectorAll("button")).find(function(x){return x.textContent.trim()==="취소";});if(b)b.click();return "ok";})()')
    time.sleep(1)


def body_coords():
    # 본문 '문단 텍스트 자체'의 중앙을 클릭해야 SE가 캐럿을 본문에 둔다.
    # 섹션 top+40 같은 여백 좌표를 클릭하면 SE가 입력을 제목으로 라우팅한다(실측 사고).
    xy = chrome_js('(function(){var el=document.querySelector(".se-component.se-text .se-text-paragraph")||document.querySelector(".se-section-text,.se-content");el.scrollIntoView({block:"center"});var r=el.getBoundingClientRect();return JSON.stringify({x:Math.round(window.screenX+r.left+Math.max(10,Math.min(r.width/2,150))),y:Math.round(window.screenY+(window.outerHeight-window.innerHeight)+r.top+Math.max(6,r.height/2))});})()')
    c = json.loads(xy)
    return c["x"], c["y"]


def caret_in_title():
    return chrome_js('(function(){var a=document.activeElement;return (a&&a.closest&&a.closest(".se-documentTitle"))?"T":"B";})()') == "T"


def focus_body():
    # 새 글쓰기 창은 초기화가 끝나면 캐럿을 '제목'으로 자동 포커스한다(실측 — 첫 청크가
    # 제목칸에 붙던 사고 원인). 초기화가 끝나길 기다린 뒤 본문을 클릭하고, 제목이면 재클릭.
    time.sleep(3.0)
    x, y = body_coords()
    for _ in range(5):
        click_at(x, y)
        time.sleep(0.8)
        if not caret_in_title():
            return
        time.sleep(0.8)
    sys.exit("포커스가 계속 제목칸에 잡힘 — 중단")


def focused():
    return chrome_js("String(document.hasFocus())", timeout=8) == "true"


def img_count():
    try:
        return int(chrome_js('String(document.querySelectorAll(".se-component.se-image").length)'))
    except ValueError:
        return -1


def para_count():
    try:
        return int(chrome_js('String(document.querySelectorAll(".se-text-paragraph").length)'))
    except ValueError:
        return -1


def title_text():
    return chrome_js('(function(){var t=document.querySelector(".se-documentTitle");return t?t.innerText.trim():"";})()')


def paste_all(chunks):
    n = len(chunks)
    for i, (t, content, _) in enumerate(chunks):
        if not focused():
            regained = False
            for _ in range(8):
                osa('tell application "Google Chrome" to activate')
                time.sleep(1.0)
                if focused():
                    regained = True
                    break
            if not regained:
                sys.exit(f"[ABORT] 창 포커스 상실({i+1}/{n}) — 에디터 밖 살포 방지 중단")
        if t == "html":
            for attempt in (1, 2):
                before = para_count()
                PN.copy_html_to_clipboard(content)
                time.sleep(0.25)
                cmd_v()
                deadline = time.time() + 6
                okd = False
                while time.time() < deadline:        # 등록 검증: 문단 수 증가
                    if para_count() > before:
                        okd = True
                        break
                    time.sleep(0.35)
                if okd:
                    break
                print(f"    [재시도] html 등록 미확인 ({i+1}/{n})")
                time.sleep(1.0)
            time.sleep(0.4)
            label = content[:40].replace("\n", " ")
        else:
            size_mb = pathlib.Path(content).stat().st_size / 1024 / 1024
            wait = min(60, 12 + size_mb * 6)         # 대형 GIF(수 MB)는 업로드 등록이 오래 걸림
            registered = False
            for attempt in (1, 2):
                before = img_count()
                PN.copy_image_file_to_clipboard(content)
                time.sleep(0.25)
                cmd_v()
                deadline = time.time() + wait
                while time.time() < deadline:        # 순서 보장: 업로드 등록까지 대기
                    if img_count() > before:
                        registered = True
                        break
                    time.sleep(0.4)
                if registered:
                    break
                time.sleep(3)                        # 지연 등록 최종 확인 후 재붙임
                if img_count() > before:
                    registered = True
                    break
                print(f"    [재시도] 이미지 등록 미확인: {pathlib.Path(content).name}")
            if not registered:
                print(f"    [경고] 이미지 누락 가능: {pathlib.Path(content).name}")
            time.sleep(0.5)
            label = pathlib.Path(content).name
        if i == 0 or i % 10 == 0:                # 제목 오염 즉시 감지(입력이 제목으로 라우팅된 사고)
            tt = title_text()
            if tt and tt != "제목" and len(tt) > 4:
                sys.exit(f"[ABORT] 청크가 제목칸에 붙음({i+1}/{n}): '{tt[:30]}' — 좌표/타이밍 확인 필요")
        print(f"[{i+1}/{n}] {t}: {label}")


# ---------------------------------------------------------------- 스타일 패스
JS_NEXT_IMG = """
(() => {
  const img = Array.from(document.querySelectorAll('.se-component.se-image'))
    .find(c => !c.querySelector('.se-section').className.includes('se-section-align-center'));
  if (!img) return 'done';
  img.scrollIntoView({block:'center'});
  const mod = img.querySelector('.se-module-image') || img;
  ['mousedown','mouseup','click'].forEach(t => mod.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,button:0})));
  window.__sr='pending';
  setTimeout(() => { const al=Array.from(document.querySelectorAll('button[data-name=align]')).find(b=>b.getAttribute('data-value')==='center'&&b.offsetParent);
    if(al)al.click();
    setTimeout(()=>{window.__sr=img.querySelector('.se-section').className.includes('se-section-align-center')?'ok':'failed';},250);},450);
  return 'working';
})()"""
JS_NEXT_HR = """
(() => {
  const hr = Array.from(document.querySelectorAll('.se-component.se-horizontalLine'))
    .find(c => { const s=c.querySelector('.se-section').className; return !(s.includes('se-l-line3')&&s.includes('se-section-align-center')); });
  if (!hr) return 'done';
  hr.scrollIntoView({block:'center'});
  const mod = hr.querySelector('.se-module-horizontalLine') || hr.querySelector('hr') || hr;
  ['mousedown','mouseup','click'].forEach(t => mod.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,button:0})));
  window.__sr='pending';
  setTimeout(() => { const lay=Array.from(document.querySelectorAll('button[data-name=horizontal-line-layout]')).find(b=>b.getAttribute('data-value')==='line3'&&b.offsetParent);
    if(lay)lay.click();
    setTimeout(()=>{ const al=Array.from(document.querySelectorAll('button[data-name=align]')).find(b=>b.getAttribute('data-value')==='center'&&b.offsetParent);
      if(al)al.click();
      setTimeout(()=>{ const s=hr.querySelector('.se-section').className; window.__sr=(s.includes('se-l-line3')&&s.includes('se-section-align-center'))?'ok':'failed';},250);},300);},450);
  return 'working';
})()"""


def style_pass():
    for js, label in ((JS_NEXT_IMG, "이미지 가운데정렬"), (JS_NEXT_HR, "구분선 line3+center")):
        done = 0
        for _ in range(150):
            if chrome_js(js) == "done":
                break
            for _ in range(10):
                time.sleep(0.35)
                sr = chrome_js("window.__sr||'none'")
                if sr in ("ok",) or sr.startswith("failed"):
                    break
            done += 1
        print(f"[style] {label}: {done} 처리")
    chrome_js('(function(){var tm=document.querySelector(".se-component.se-text .se-module-text");if(tm)["mousedown","mouseup","click"].forEach(function(t){tm.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,button:0}));});return "ok";})()')


def highlight_pass(hl_texts):
    """노란배경 소제목 입히기: 진짜 트리플클릭(신뢰 이벤트)으로 문단 선택 →
    툴바 background-color 버튼 → #fff593 스와치. paste로 배경색을 넣으면
    SE가 하이라이트를 전체에 고착시키므로(실측) 반드시 이 후처리로 입힌다."""
    def find_next():
        js = ('(function(){var want=' + json.dumps([re.sub(r"\s+", "", t) for t in hl_texts], ensure_ascii=False) + ';'
              'var ps=Array.from(document.querySelectorAll(".se-component.se-text .se-text-paragraph"));'
              'var p=ps.find(function(x){var t=(x.innerText||"").replace(/\\s+/g,"");'
              'return want.indexOf(t)>=0 && !x.querySelector("mark,.se-highlight");});'
              'if(!p)return "done";p.scrollIntoView({block:"center"});var r=p.getBoundingClientRect();'
              'return JSON.stringify({x:Math.round(window.screenX+r.left+Math.min(60,r.width/3)),'
              'y:Math.round(window.screenY+(window.outerHeight-window.innerHeight)+r.top+r.height/2),'
              't:(p.innerText||"").slice(0,20)});})()')
        return chrome_js(js)

    applied = 0
    for _ in range(len(hl_texts) * 3 + 3):
        r = find_next()
        if r == "done":
            break
        try:
            c = json.loads(r)
        except json.JSONDecodeError:
            print(f"    [highlight] 좌표 실패: {r[:60]}")
            break
        click_at(c["x"], c["y"], clicks=1)
        time.sleep(0.4)
        click_at(c["x"], c["y"], clicks=3)           # 트리플클릭 = 문단 선택(신뢰 이벤트)
        time.sleep(0.6)
        chrome_js('(function(){var b=Array.from(document.querySelectorAll("button[data-name=background-color]")).find(function(x){return x.offsetParent;});if(b)b.click();return "ok";})()')
        time.sleep(0.6)
        chrome_js('(function(){var sw=Array.from(document.querySelectorAll("[data-value], [data-color]")).find(function(x){return x.offsetParent&&((x.getAttribute("data-value")||x.getAttribute("data-color"))==="#fff593");});if(sw)sw.click();return "ok";})()')
        time.sleep(0.6)
        applied += 1
        print(f"    [highlight] {c['t']}")
    print(f"[highlight] 노란배경 적용: {applied}/{len(hl_texts)}")


def set_title(title):
    xy_js = '(function(){var tt=document.querySelector(".se-documentTitle .se-text-paragraph, .se-documentTitle");tt.scrollIntoView({block:"center"});var r=tt.getBoundingClientRect();return JSON.stringify({x:Math.round(window.screenX+r.left+r.width/2),y:Math.round(window.screenY+(window.outerHeight-window.innerHeight)+r.top+r.height/2)});})()'
    for attempt in range(3):                     # 제목 검증은 최대 3회(사용자 지시)
        subprocess.run(["pbcopy"], input=title.encode())
        time.sleep(0.3)
        clip = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        if clip.strip() != title.strip():        # 다른 프로세스가 클립보드를 덮었으면 재복사
            continue
        c = json.loads(chrome_js(xy_js))         # 시도마다 좌표 재계산(스크롤·레이아웃 변동 대응)
        click_at(c["x"], c["y"], clicks=1)       # 단일클릭으로 캐럿 먼저(실측: 바로 트리플이면 씹힘)
        time.sleep(0.8)
        click_at(c["x"], c["y"], clicks=3)       # 트리플클릭(전체선택) 후 붙여넣기 = 교체라 중복 없음
        time.sleep(0.8)
        cmd_v()
        time.sleep(1.4)
        got = chrome_js('(function(){return document.querySelector(".se-documentTitle").innerText.trim();})()')
        if title[:10] in got:
            print(f"[title] 입력됨: {got[:50]}")
            return
        time.sleep(1.0)
    print(f"[title] 실패 — 수동 입력 필요: {title}")


# ---------------------------------------------------------------- 최종 검증
def verify_editor(chunks, hl_count):
    """에디터 실물 vs 청크: img/hr 경계 사이 텍스트를 위치별로 대조."""
    def norm(s):
        return re.sub(r"\s+", "", s).translate(str.maketrans("", "", ZW))

    def gaps_from_chunks():
        seq, buf = [], ""
        for t, content, _ in chunks:
            if t == "img":
                seq.append(("gap", buf)); seq.append(("img",)); buf = ""
                continue
            pieces = content.split("<hr>")
            for j, piece in enumerate(pieces):
                if j > 0:
                    seq.append(("gap", buf)); seq.append(("hr",)); buf = ""
                texts = re.findall(r"<p[^>]*>(.*?)</p>", piece, re.S)
                buf += norm("".join(_plain(x) for x in texts))
        seq.append(("gap", buf))
        return seq

    editor = json.loads(chrome_js(
        '(function(){var out=[];document.querySelectorAll(".se-component").forEach(function(c){var cl=c.className;'
        'if(cl.indexOf("se-documentTitle")>=0)return;'
        'if(cl.indexOf("se-image")>=0){out.push({k:"img"});return;}'
        'if(cl.indexOf("se-horizontalLine")>=0){out.push({k:"hr"});return;}'
        'if(cl.indexOf("se-text")>=0){out.push({k:"txt",t:(c.innerText||"")});}});'
        'return JSON.stringify(out);})()', timeout=30))
    eseq, buf = [], ""
    for it in editor:
        if it["k"] == "txt":
            buf += norm(it["t"])
        else:
            eseq.append(("gap", buf)); eseq.append((it["k"],)); buf = ""
    eseq.append(("gap", buf))

    cseq = gaps_from_chunks()
    ok = True
    if len(cseq) != len(eseq):
        print(f"[verify] 경계 수 불일치: 기대 {len(cseq)} vs 에디터 {len(eseq)}")
        ok = False
    for i, (c, e) in enumerate(zip(cseq, eseq)):
        if c[0] != e[0]:
            print(f"[verify] {i}번 종류 불일치: {c[0]} vs {e[0]}"); ok = False; break
        if c[0] == "gap" and c[1] != e[1]:
            print(f"[verify] {i}번 텍스트 불일치:\n  기대: …{c[1][:60]}\n  실제: …{e[1][:60]}")
            ok = False
    n_img_e = sum(1 for s in eseq if s[0] == "img")
    n_img_c = sum(1 for s in cseq if s[0] == "img")
    exp_hl = hl_count
    try:
        act_hl = int(chrome_js(
            'String(Array.from(document.querySelectorAll(".se-component.se-text .se-text-paragraph"))'
            '.filter(function(p){return p.querySelector("mark,.se-highlight")&&(p.innerText||"").trim();}).length)'))
    except ValueError:
        act_hl = -1
    if act_hl != exp_hl:
        print(f"[verify] 노란배경 문단 불일치: 기대 {exp_hl} vs 실제 {act_hl} (번짐 또는 누락)")
        ok = False
    print(f"[verify] 이미지 {n_img_e}/{n_img_c} | 경계 {len(eseq)}/{len(cseq)} | 노란배경 {act_hl}/{exp_hl} | "
          f"{'PASS — 누락 0' if ok else 'FAIL'}")
    return ok


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--blog-id", default=None)
    ap.add_argument("--html", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--censored", action="store_true",
                    help="가려진(검열) 캐시 이미지 사용 — 사용자가 명시적으로 요청할 때만")
    ap.add_argument("--title", default=None, help="제목 덮어쓰기(예: 화수 변경 재발행)")
    args = ap.parse_args()

    m = re.search(r"/(\d{8,})", args.target) or re.search(r"logNo=(\d{8,})", args.target)
    log = m.group(1) if m else (args.target if args.target.isdigit() else None)
    if not log:
        sys.exit("logNo를 못 찾음")
    bm = re.search(r"blog\.naver\.com/([A-Za-z0-9_-]+)/", args.target)
    blog_id = args.blog_id or (bm.group(1) if bm else "op5321")

    src = fetch_source(blog_id, log, args.html)
    global USE_CENSORED
    USE_CENSORED = args.censored
    if args.censored:
        print("[주의] --censored: 가려진 캐시 이미지 사용")
    tm = re.search(r'<meta property="og:title" content="([^"]*)"', src)
    title = args.title or (H.unescape(tm.group(1)) if tm else "")

    chunks, stats, hl_texts = build_chunks(src)
    src_paras, missing = verify_chunks_vs_source(src, chunks)
    print(f"[build] 청크 {len(chunks)} | 문단 {stats['para']} 스페이서 {stats['spacer']} | "
          f"이미지 {stats['img']}(GIF {stats['gif']}, 스티커 {stats['sticker']}) | 구분선 {stats['hr']}")
    print(f"[build] 원본 문단 {len(src_paras)} / 청크 누락 {len(missing)}")
    for t in missing[:10]:
        print("   MISSING:", t[:60])
    if stats["fail"]:
        print("[build] 이미지 실패:", stats["fail"])
    if missing or stats["fail"]:
        sys.exit("소스 대비 누락 존재 — 붙여넣기 중단")
    if args.dry_run:
        for i, (t, c, p) in enumerate(chunks[:30]):
            print(f"  {i:2} {t}: {(pathlib.Path(c).name if t=='img' else c[:70])}")
        return

    print(f"[진행] 새 글쓰기 창에 {len(chunks)}청크 복붙 — 마우스·키보드 금지")
    open_fresh_editor(blog_id)
    focus_body()
    paste_all(chunks)
    style_pass()
    highlight_pass(hl_texts)
    set_title(title)
    ok = verify_editor(chunks, len(hl_texts))
    print("[완료] 발행은 수동. " + ("검증 PASS" if ok else "검증 FAIL — 위 로그 확인"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
