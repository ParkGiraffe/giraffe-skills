#!/usr/bin/env python3
"""네이버 SmartEditor ONE의 문서 데이터를 직접 고치는 공용 패스.

붙여넣기로는 만들 수 없는 것을 에디터 문서 JSON에서 처리한다.
- 두 장 묶음: 이웃한 사진 컴포넌트 둘을 imageStrip(에디터가 imageStrip2로 렌더) 하나로 합친다.
- 영상 순서: 대본의 영상 자리와 실제 위치(앞에 있는 사진 수)를 대조하고, 틀리면 옮긴다.

osascript의 `execute javascript`는 격리된 월드에서 돌아서 페이지의 `SmartEditor` 전역이
보이지 않는다. 그래서 <script> 태그를 주입해 페이지 월드에서 실행하고, 결과는
<html data-se-doc> 속성으로 돌려받는다 (2026-09-23 실측: 격리 월드에서는 전역이 0개).

사용하는 쪽은 탭을 못박은 chrome_js(js_source) -> str 함수를 넘긴다.
upload_to_editor.make_chrome_js, tistory-to-naver migrate.chrome_js 둘 다 이 모양이다.
"""
import json
import re

RESULT_ATTR = "data-se-doc"


def page_eval(chrome_js, body: str, timeout: int = 20) -> str:
    """body(함수 본문, return으로 문자열을 돌려줌)를 페이지 월드에서 실행한다."""
    inner = ("try{document.documentElement.setAttribute('" + RESULT_ATTR + "',"
             "String((function(){" + body + "})()))}catch(e){document.documentElement"
             ".setAttribute('" + RESULT_ATTR + "','ERR '+e+' '+String(e.stack||'').slice(0,300))}")
    wrapper = ("(function(){var s=document.createElement('script');s.textContent=%s;"
               "document.documentElement.removeAttribute('%s');"
               "document.head.appendChild(s);s.remove();"
               "return document.documentElement.getAttribute('%s')})()"
               % (json.dumps(inner), RESULT_ATTR, RESULT_ATTR))
    return chrome_js(wrapper, timeout=timeout)


# 문서 패스 본체. P = {expect_images, groups, videos}
#   groups: [[첫 사진 번호(0부터, 문서 안 사진 순서), 장수], ...]. 에디터는 2장이면 imageStrip2,
#           3장이면 imageStrip3으로 렌더한다.
#   videos: [{title, after}] after = 그 영상 앞에 와야 하는 사진 수
_PASS_JS = r"""
var P = __PARAMS__;
var ed = null, eds = (window.SmartEditor && SmartEditor._editors) || {};
for (var k in eds) { ed = eds[k]; break; }
if (!ed) return JSON.stringify({ok:false, err:'SmartEditor 인스턴스 없음'});
var d = ed.getDocumentData(), cs = d.document.components;
var isImg = function(c){ return c['@ctype'] === 'image'; };
// 영상 위치를 셀 때는 묶음 안의 사진도 장수대로 센다
var weight = function(c){ return isImg(c) ? 1 : (c['@ctype'] === 'imageStrip' ? (c.images || []).length : 0); };
var isEmptyText = function(c){
  if (c['@ctype'] !== 'text') return false;
  return (c.value || []).every(function(p){
    return (p.nodes || []).every(function(n){
      return String(n.value || '').replace(/[\s​ ]/g, '') === ''; }); });
};
var rep = {ok:true, images:0, strips:0, moved:[], skipped:[], videos:[]};
var imgs = cs.filter(isImg);
rep.images = imgs.length;
if (P.expect_images != null && imgs.length !== P.expect_images)
  return JSON.stringify({ok:false, err:'사진 수 '+imgs.length+' != 대본 '+P.expect_images});

// 1) 영상 위치 검증: 영상마다 앞에 있는 사진 수를 센다
var before = function(comp){
  var n = 0; for (var i = 0; i < cs.length; i++){ if (cs[i] === comp) return n; n += weight(cs[i]); } return -1; };
var vids = cs.filter(function(c){ return c['@ctype'] === 'video'; });
var plan = [];
for (var i = 0; i < (P.videos || []).length; i++){
  var v = P.videos[i];
  var hit = vids.filter(function(c){ return JSON.stringify(c).indexOf(v.title) >= 0; });
  if (hit.length !== 1) { rep.video_check = '식별 실패: ' + v.title + ' (' + hit.length + '개)'; plan = null; break; }
  plan.push({v:v, c:hit[0]});
  rep.videos.push({title:v.title, expect:v.after, actual:before(hit[0])});
}
var wrong = false;
if (plan) {
  var order = vids.map(function(c){ return plan.findIndex(function(x){ return x.c === c; }); });
  wrong = plan.some(function(x){ return before(x.c) !== x.v.after; }) ||
          order.some(function(o, i){ return o !== i; });
}
if (wrong) {
  // 영상을 모두 빼고, 대본 순서대로 (after번째 사진 + 그 캡션 문단들) 바로 뒤에 다시 넣는다
  plan.forEach(function(x){ cs.splice(cs.indexOf(x.c), 1); });
  plan.forEach(function(x){
    var pos;
    if (x.v.after === 0) { pos = 1; }
    else {
      var n = 0; pos = -1;
      for (var i = 0; i < cs.length; i++){ n += weight(cs[i]); if (weight(cs[i]) && n >= x.v.after) { pos = i + 1; break; } }
      if (pos < 0) pos = cs.length;
      while (pos < cs.length && cs[pos]['@ctype'] === 'text' && !isEmptyText(cs[pos])) pos++;
      while (pos < cs.length && cs[pos]['@ctype'] === 'video') pos++;
    }
    cs.splice(pos, 0, x.c);
    rep.moved.push(x.v.title);
  });
}

// 2) 두 장 묶음: 뒤에서부터 합쳐야 앞 번호가 안 밀린다
var uuid = function(){ return 'SE-' + 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(ch){
  var r = crypto.getRandomValues(new Uint8Array(1))[0] & 15; return (ch === 'x' ? r : (r & 3 | 8)).toString(16); }); };
var groups = (P.groups || []).slice().sort(function(a, b){ return b[0] - a[0]; });
for (var j = 0; j < groups.length; j++){
  var g0 = groups[j][0], gn = groups[j][1], imgsNow = cs.filter(isImg);
  var members = imgsNow.slice(g0, g0 + gn);
  if (members.length !== gn) { rep.skipped.push(g0 + ': 사진 없음'); continue; }
  var ia = cs.indexOf(members[0]), ib = cs.indexOf(members[gn - 1]), mid = cs.slice(ia + 1, ib);
  if (!mid.every(function(c){ return isImg(c) || isEmptyText(c); })) { rep.skipped.push(g0 + ': 사이에 내용 있음'); continue; }
  var strip = {id: uuid(), layout: 'default', align: 'center', images: members, caption: null, '@ctype': 'imageStrip'};
  cs.splice(ia, ib - ia + 1, strip);
  rep.strips++;
}
if (wrong || rep.strips) ed.setDocumentData(d);
return JSON.stringify(rep);
"""

_VERIFY_JS = r"""
var ed = null, eds = (window.SmartEditor && SmartEditor._editors) || {};
for (var k in eds) { ed = eds[k]; break; }
var cs = ed.getDocumentData().document.components;
return JSON.stringify(cs.map(function(c){
  if (c['@ctype'] === 'image') return 'I';
  if (c['@ctype'] === 'imageStrip') return 'S' + (c.images || []).length;
  if (c['@ctype'] === 'video') return 'V';
  return null; }).filter(Boolean));
"""


def fix_media(chrome_js, expect_images=None, pairs=(), videos=(), groups=()):
    """사진 묶음과 영상 순서를 한 번에 처리하고 보고서(dict)를 돌려준다.

    pairs는 두 장 묶음의 첫 사진 번호 목록(대본 표기용 단축형), groups는 [첫 번호, 장수] 목록이다.
    """
    allg = [[p, 2] for p in pairs] + [list(g) for g in groups]
    params = {"expect_images": expect_images, "groups": allg, "videos": list(videos)}
    out = page_eval(chrome_js, _PASS_JS.replace("__PARAMS__", json.dumps(params, ensure_ascii=False)))
    if not out or out.startswith("ERR"):
        return {"ok": False, "err": out or "빈 응답"}
    return json.loads(out)


def media_sequence(chrome_js):
    """문서의 미디어 순서. I=사진, S2=두 장 묶음, V=영상."""
    return json.loads(page_eval(chrome_js, _VERIFY_JS))


_IMG_REF = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_PAIR_LINE = re.compile(r"^!\[[^\]]*\]\([^)]+\)\s+!\[[^\]]*\]\([^)]+\)\s*$")
_VIDEO_SLOT = re.compile(r"^\s*\[영상 자리\s*:\s*([^\]]+)\]\s*$")


def plan_from_markdown(md_text: str, video_titles: dict | None = None) -> dict:
    """대본(script.md)에서 사진 수, 두 장 묶음, 영상 자리를 뽑는다.

    video_titles: 영상 자리의 파일명 -> 에디터에 올린 제목. 없으면 파일명에서 슬롯 접두어를 뗀다.
    """
    md_text = re.sub(r"<!--.*?-->", "", md_text, flags=re.S)
    n, pairs, videos, seq = 0, [], [], []
    for raw in md_text.splitlines():
        line = raw.strip()
        if line.startswith("!["):
            refs = _IMG_REF.findall(line)
            if _PAIR_LINE.match(line):
                pairs.append(n)
                seq.append("S2")
            else:
                seq += ["I"] * len(refs)
            n += len(refs)
            continue
        m = _VIDEO_SLOT.match(line)
        if m:
            fname = m.group(1).strip()
            title = (video_titles or {}).get(fname) or fname.split("_", 2)[-1].rsplit(".", 1)[0]
            videos.append({"title": title, "after": n})
            seq.append("V")
    # sequence는 최종 검증용(media_sequence와 같은 표기), fix_media에는 넘기지 않는다
    return {"expect_images": n, "pairs": pairs, "videos": videos, "sequence": seq}


# ---------------------------------------------------------------- 문서 통째로 쓰기
# 클립보드 붙여넣기는 키보드 포커스가 다른 창으로 넘어가면 그 뒤 조각이 전부 허공으로 간다
# (2026-09-23 젤다무쌍 4-4: 크롬 창 두 개 중 다른 창으로 포커스가 넘어가 44조각 중 13개만 들어감).
# 여기서는 사진을 에디터 API로 올리고 글·구분선·사진을 문서 JSON으로 한 번에 넣는다.
# 포커스, 클립보드, 마우스를 전혀 쓰지 않는다.
import base64 as _b64
import time as _time
import uuid as _uuid

_BLANK_STYLE = {"fontColor": "#141414", "fontFamily": "system", "@ctype": "nodeStyle"}
_BODY_STYLE = {"fontColor": "#212529", "fontFamily": "system", "fontSizeCode": "fs15",
               "bold": False, "@ctype": "nodeStyle"}
_H2_STYLE = {"fontColor": "#141414", "fontFamily": "system", "fontSizeCode": "fs24",
             "backgroundColor": "#fff593", "bold": True, "@ctype": "nodeStyle"}
_H3_STYLE = {"fontColor": "#212529", "fontFamily": "system", "fontSizeCode": "fs19",
             "bold": True, "@ctype": "nodeStyle"}
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def _sid():
    return f"SE-{_uuid.uuid4()}"


def _para(nodes):
    return {"id": _sid(), "nodes": nodes, "@ctype": "paragraph"}


def _node(value, style):
    return {"id": _sid(), "value": value, "style": dict(style), "@ctype": "textNode"}


def _body_nodes(text):
    """본문 한 줄. **굵게**만 살리고 나머지 마크다운 기호는 글자 그대로 둔다."""
    out, last = [], 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > last:
            out.append(_node(text[last:m.start()], _BODY_STYLE))
        out.append(_node(m.group(1), {**_BODY_STYLE, "bold": True}))
        last = m.end()
    if last < len(text) or not out:
        out.append(_node(text[last:], _BODY_STYLE))
    return out


def _run_nodes(runs):
    """[{text, bold, italic, underline, link}] -> 본문 글자 노드. 링크는 urlLink로 단다."""
    out = []
    for r in runs:
        st = {**_BODY_STYLE, "bold": bool(r.get("bold"))}
        if r.get("italic"):
            st["italic"] = True
        if r.get("underline"):
            st["underline"] = True
        n = _node(r["text"], st)
        if r.get("link"):
            n["link"] = {"url": r["link"], "@ctype": "urlLink"}
        out.append(n)
    return out or [_node("", _BODY_STYLE)]


_FS_RE = re.compile(r"font-size:\s*(\d+)px")


def ops_from_html_chunks(chunks):
    """붙여넣기용 청크({'type':'html'|'image'})를 문서 빌더 목록으로 바꾼다.

    tistory-to-naver처럼 SmartEditor 붙여넣기용 HTML을 만드는 파이프라인이 쓴다.
    <p> 하나가 문단 하나, <br>은 문단 나눔, 빈 <p>는 빈 줄, <hr>은 구분선이다.
    24px 노란 바탕 문단은 ## 제목, 19px 문단은 ### 제목으로 본다.
    """
    from bs4 import BeautifulSoup, NavigableString
    ops = []

    def walk(node, st, runs):
        for ch in node.children:
            if isinstance(ch, NavigableString):
                t = re.sub(r"[ \t\n\r]+", " ", str(ch))
                if t:
                    runs.append({**st, "text": t})
                continue
            if ch.name == "br":
                runs.append({"br": True})
                continue
            nst = dict(st)
            style = ch.get("style", "") or ""
            if ch.name in ("b", "strong") or "font-weight:bold" in style.replace(" ", ""):
                nst["bold"] = True
            if "font-weight:normal" in style.replace(" ", ""):
                nst["bold"] = False
            if ch.name in ("i", "em"):
                nst["italic"] = True
            if ch.name == "u":
                nst["underline"] = True
            if ch.name == "a" and ch.get("href"):
                nst["link"] = ch["href"]
            walk(ch, nst, runs)

    for c in chunks:
        if c["type"] == "image":
            ops.append(("img", c["path"]))
            continue
        soup = BeautifulSoup(c["content"], "html.parser")
        for el in soup.find_all(["p", "hr"], recursive=False) or soup.find_all(["p", "hr"]):
            if el.name == "hr":
                ops.append(("hr",))
                continue
            text = el.get_text()
            if not text.replace("\xa0", "").strip():
                ops.append(("blank", 1))
                continue
            span = el.find("span", style=True)
            fs = _FS_RE.search(span["style"]) if span else None
            if fs and fs.group(1) == "24":
                ops.append(("h", 2, text.strip()))
                continue
            if fs and fs.group(1) == "19":
                ops.append(("h", 3, text.strip()))
                continue
            runs = []
            walk(el, {}, runs)
            line = []
            for r in runs + [{"br": True}]:
                if r.get("br"):
                    if line:
                        line[0]["text"] = line[0]["text"].lstrip()
                        line[-1]["text"] = line[-1]["text"].rstrip()
                        line = [x for x in line if x["text"]]
                    ops.append(("rp", line) if line else ("blank", 1))
                    line = []
                else:
                    line.append(r)
            # 마지막 br 표식이 만든 빈 줄은 원래 없던 것이므로 걷어낸다
            if ops and ops[-1] == ("blank", 1) and runs and not runs[-1].get("br"):
                ops.pop()
    return ops


def skeleton_from_ops(ops):
    """paste_to_naver.parse_to_ops 결과를 컴포넌트 목록으로. 사진 자리는 {"__img": 번호}."""
    comps, paras, n_img = [], [], 0

    def flush():
        if paras:
            comps.append({"id": _sid(), "layout": "default", "value": list(paras), "@ctype": "text"})
            paras.clear()

    for op in ops:
        kind = op[0]
        if kind == "blank":
            paras.extend(_para([_node("", _BLANK_STYLE)]) for _ in range(op[1]))
        elif kind == "h":
            paras.append(_para([_node(op[2], _H2_STYLE if op[1] <= 2 else _H3_STYLE)]))
        elif kind == "p":
            paras.append(_para(_body_nodes(op[1])))
        elif kind == "rp":
            paras.append(_para(_run_nodes(op[1])))
        elif kind == "hr":
            flush()
            comps.append({"id": _sid(), "layout": "line3", "@ctype": "horizontalLine"})
        elif kind == "img":
            flush()
            comps.append({"__img": n_img})
            n_img += 1
    flush()
    if not comps or comps[-1].get("@ctype") != "text":
        comps.append({"id": _sid(), "layout": "default",
                      "value": [_para([_node("", _BLANK_STYLE)])], "@ctype": "text"})
    return comps


_UPLOAD_JS = r"""
var box = document.getElementById('se-doc-upload');
var tas = box ? Array.from(box.querySelectorAll('textarea')) : [];
var files = tas.map(function(t){
  var s = atob(t.value), a = new Uint8Array(s.length);
  for (var i = 0; i < s.length; i++) a[i] = s.charCodeAt(i);
  return new File([a], t.getAttribute('data-name'), {type: t.getAttribute('data-type')});
});
var ed = null, eds = (window.SmartEditor && SmartEditor._editors) || {};
for (var k in eds) { ed = eds[k]; break; }
window.__seDocUploadN = files.length;
ed.focusFirstText();
ed.execCommand('insertImagesByFile', {data: files.map(function(f){ return {file: f, fileName: f.name}; })});
return String(files.length);
"""

_UPLOAD_STATE_JS = r"""
var names = __NAMES__;
var ed = null, eds = (window.SmartEditor && SmartEditor._editors) || {};
for (var k in eds) { ed = eds[k]; break; }
var imgs = ed.getDocumentData().document.components.filter(function(c){
  return c['@ctype'] === 'image' && names.indexOf(c.fileName) >= 0; });
return JSON.stringify({n: imgs.length, done: imgs.filter(function(c){ return c.path && c.src; }).length});
"""

_BUILD_JS = r"""
var P = __PARAMS__;
var ed = null, eds = (window.SmartEditor && SmartEditor._editors) || {};
for (var k in eds) { ed = eds[k]; break; }
var d = ed.getDocumentData(), cs = d.document.components;
var up = cs.filter(function(c){ return c['@ctype'] === 'image' && P.names.indexOf(c.fileName) >= 0; });
var byName = {};
up.forEach(function(c){ (byName[c.fileName] = byName[c.fileName] || []).push(c); });
var out = [cs[0]];   // documentTitle
cs[0].title[0].nodes[0].value = P.title;
for (var i = 0; i < P.comps.length; i++){
  var c = P.comps[i];
  if (c.__img == null) { out.push(c); continue; }
  var nm = P.names[c.__img], hit = (byName[nm] || []).shift();
  if (!hit) return JSON.stringify({ok:false, err:'업로드된 사진 없음: ' + nm});
  out.push(hit);
}
var left = Object.keys(byName).filter(function(k){ return byName[k].length; });
if (left.length) return JSON.stringify({ok:false, err:'쓰이지 않은 업로드 사진: ' + left.join(',')});
d.document.components = out;
ed.setDocumentData(d);
return JSON.stringify({ok:true, comps: out.length, images: up.length});
"""

_CHUNK = 180_000


def editor_file_name(name):
    """에디터가 저장하는 사진 파일명. 공백을 '_'로 바꾼다(괄호 등은 그대로, 2026-09-26 실측).

    업로드 완료를 파일명으로 확인하는 곳은 전부 이 이름으로 비교해야 한다. 원래 이름으로
    비교하면 'Pokmon GO.jpg' 같은 사진에서 완료를 영영 못 보고 멈춘다(2026-09-26 사고).
    """
    return name.replace(" ", "_")


def write_document(chrome_js, title, ops, log=print):
    """글 전체를 에디터에 쓴다. 사진 업로드 -> 문서 JSON 교체 순서다. 성공하면 사진 수를 돌려준다."""
    comps = skeleton_from_ops(ops)
    paths = [op[1] for op in ops if op[0] == "img"]
    names = [editor_file_name(p.rsplit("/", 1)[-1]) for p in paths]
    if len(set(names)) != len(names):
        raise RuntimeError("사진 파일명이 겹침. 파일명으로 업로드 결과를 짝지으므로 이름이 모두 달라야 한다")

    # 1) 파일을 숨은 textarea에 base64로 나눠 싣는다. DOM이라 격리 월드와 페이지 월드가 함께 본다.
    chrome_js("(function(){var b=document.getElementById('se-doc-upload');if(b)b.remove();"
              "b=document.createElement('div');b.id='se-doc-upload';b.style.display='none';"
              "document.body.appendChild(b);return 'ok'})()")
    for i, p in enumerate(paths):
        data = _b64.b64encode(open(p, "rb").read()).decode("ascii")
        ctype = "image/gif" if p.lower().endswith(".gif") else (
            "image/png" if p.lower().endswith(".png") else "image/jpeg")
        chrome_js("(function(){var t=document.createElement('textarea');t.id='se-up-%d';"
                  "t.setAttribute('data-name',%s);t.setAttribute('data-type','%s');"
                  "document.getElementById('se-doc-upload').appendChild(t);return 'ok'})()"
                  % (i, json.dumps(names[i]), ctype))
        for off in range(0, len(data), _CHUNK):
            got = chrome_js("(function(){var t=document.getElementById('se-up-%d');t.value+='%s';"
                            "return String(t.value.length)})()" % (i, data[off:off + _CHUNK]), timeout=30)
        if got != str(len(data)):
            raise RuntimeError(f"사진 전송 실패: {names[i]} ({got}/{len(data)})")
    log(f"      사진 {len(paths)}장 전송")

    # 2) 에디터 API로 업로드하고, 모두 올라갈 때까지 기다린다
    r = page_eval(chrome_js, _UPLOAD_JS)
    if r != str(len(paths)):
        raise RuntimeError(f"업로드 시작 실패: {r}")
    st = {}
    for _ in range(240):
        _time.sleep(1.0)
        st = json.loads(page_eval(chrome_js, _UPLOAD_STATE_JS.replace(
            "__NAMES__", json.dumps(names, ensure_ascii=False))))
        if st["n"] == len(paths) and st["done"] == len(paths):
            break
    else:
        raise RuntimeError(f"업로드가 끝나지 않음: {st}")
    chrome_js("(function(){var b=document.getElementById('se-doc-upload');if(b)b.remove();return 'ok'})()")
    log(f"      업로드 완료 {st['done']}장")

    # 3) 글·구분선·사진을 대본 순서대로 넣은 문서로 교체
    params = {"title": title, "comps": comps, "names": names}
    res = json.loads(page_eval(chrome_js, _BUILD_JS.replace(
        "__PARAMS__", json.dumps(params, ensure_ascii=False)), timeout=60))
    if not res.get("ok"):
        raise RuntimeError(f"문서 교체 실패: {res.get('err')}")
    return len(paths)


# ---------------------------------------------------------------- 영상: 파일 창 없이 올리고 자리에 끼우기
# 네이티브 파일 선택 창을 키보드로 조작하면 포커스·시스템 팝업에 자주 막힌다 (2026-09-23 4-4에서 중단).
# 여기서는 127.0.0.1 임시 서버로 파일을 내주고, 페이지가 받아 업로더의 file input에 넣는다.
# 영상은 캐럿 자리에 들어가므로, 다 올린 뒤 문서 JSON에서 [영상 자리 : 파일] 문단 자리로 옮긴다.
import functools as _ft
import http.server as _hs
import threading as _th
import urllib.parse as _up

_VIDEO_POPUP = ".se-popup-video-upload"


class _Handler(_hs.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Allow-Headers", "*")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


def serve_dir(root):
    """root를 127.0.0.1의 빈 포트로 내준다. (server, port). 끝나면 server.shutdown()."""
    srv = _hs.ThreadingHTTPServer(("127.0.0.1", 0), _ft.partial(_Handler, directory=str(root)))
    _th.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _popup_text(chrome_js):
    return chrome_js("(function(){var p=document.querySelector('%s');"
                     "return p?p.innerText.replace(/\\s+/g,' '):'closed'})()" % _VIDEO_POPUP)


def video_count(chrome_js):
    return int(page_eval(chrome_js, "return String(SmartEditor._editors[Object.keys(SmartEditor._editors)[0]]"
                                    ".getDocumentData().document.components.filter(function(c){"
                                    "return c['@ctype']==='video'}).length)"))


def upload_video(chrome_js, port, relpath, title, log=print, timeout=900):
    """영상 하나를 업로드해 본문에 넣는다(위치는 place_videos_at_slots가 잡는다)."""
    before = video_count(chrome_js)
    if chrome_js("(function(){var b=document.querySelector('button[data-name=video]');"
                 "if(!b)return 'none';b.click();return 'clicked'})()") != "clicked":
        raise RuntimeError("동영상 툴바 버튼 없음")
    for _ in range(20):
        _time.sleep(0.5)
        if _popup_text(chrome_js) != "closed":
            break
    else:
        raise RuntimeError("업로더 레이어가 안 열림")
    # file input은 "동영상 추가"를 눌러야 생긴다. 합성 클릭은 파일 창을 띄우지 못하고 input만 만든다
    chrome_js("(function(){var b=document.querySelector('%s .nvu_btn_append.nvu_local');"
              "if(b)b.click();return 'ok'})()" % _VIDEO_POPUP)
    _time.sleep(1.0)
    url = f"http://127.0.0.1:{port}/" + _up.quote(relpath)
    name = relpath.rsplit("/", 1)[-1]
    r = page_eval(chrome_js, """
      var inp = document.querySelector('input[type=file][accept*=".mp4"]');
      if (!inp) return 'no-input';
      document.documentElement.setAttribute('data-se-vid', 'fetching');
      fetch(%s).then(function(r){ if (!r.ok) throw new Error('HTTP ' + r.status); return r.blob(); })
        .then(function(b){
          var dt = new DataTransfer(); dt.items.add(new File([b], %s, {type: 'video/mp4'}));
          inp.files = dt.files; inp.dispatchEvent(new Event('change', {bubbles: true}));
          document.documentElement.setAttribute('data-se-vid', 'set ' + b.size); })
        .catch(function(e){ document.documentElement.setAttribute('data-se-vid', 'ERR ' + e); });
      return 'started';""" % (json.dumps(url), json.dumps(name)))
    if r != "started":
        raise RuntimeError(f"파일 입력 못 찾음: {r}")
    t0 = _time.time()
    while _time.time() - t0 < timeout:
        _time.sleep(3)
        st = chrome_js("document.documentElement.getAttribute('data-se-vid')") or ""
        if st.startswith("ERR"):
            raise RuntimeError(f"영상 전달 실패: {st}")
        pt = _popup_text(chrome_js)
        if st.startswith("set") and "업로드 완료" in pt and "진행중" not in pt and "추출중" not in pt:
            break
    else:
        raise RuntimeError("영상 업로드 시간 초과")
    got = chrome_js("""(function(){var p=document.querySelector('%s');var i=p&&p.querySelector('input.nvu_inp');
      if(!i)return 'no-input';var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      s.call(i,%s);i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('change',{bubbles:true}));
      return i.value})()""" % (_VIDEO_POPUP, json.dumps(title, ensure_ascii=False)))
    if got != title:
        raise RuntimeError(f"영상 제목 입력 실패: {got}")
    _time.sleep(0.8)
    if chrome_js("(function(){var b=document.querySelector('%s .nvu_btn_submit');if(!b)return 'none';"
                 "b.click();return 'clicked'})()" % _VIDEO_POPUP) != "clicked":
        raise RuntimeError("완료 버튼 없음")
    for _ in range(30):
        _time.sleep(1)
        if video_count(chrome_js) > before:
            log(f"      {name} 업로드 ({int(_time.time() - t0)}초)")
            return
    raise RuntimeError("본문에 영상이 안 들어감")


_SLOT_JS = r"""
var P = __PARAMS__;   // [{file, title}]
var ed = SmartEditor._editors[Object.keys(SmartEditor._editors)[0]];
var d = ed.getDocumentData(), cs = d.document.components;
var uuid = function(){ return 'SE-' + 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(ch){
  var r = crypto.getRandomValues(new Uint8Array(1))[0] & 15; return (ch === 'x' ? r : (r & 3 | 8)).toString(16); }); };
var ptext = function(p){ return (p.nodes || []).map(function(n){ return n.value || ''; }).join(''); };
var rep = {ok: true, placed: []};
for (var i = 0; i < P.length; i++){
  var v = P[i];
  var vid = cs.filter(function(c){ return c['@ctype'] === 'video' && c.mediaMeta && c.mediaMeta.title === v.title; });
  if (vid.length !== 1) return JSON.stringify({ok: false, err: '영상 ' + v.title + ' ' + vid.length + '개'});
  cs.splice(cs.indexOf(vid[0]), 1);
  var ci = -1, pi = -1;
  for (var j = 0; j < cs.length && ci < 0; j++){
    if (cs[j]['@ctype'] !== 'text') continue;
    for (var k = 0; k < cs[j].value.length; k++){
      if (ptext(cs[j].value[k]).indexOf('[영상 자리') >= 0 && ptext(cs[j].value[k]).indexOf(v.file) >= 0) { ci = j; pi = k; break; }
    }
  }
  if (ci < 0) return JSON.stringify({ok: false, err: '영상 자리 없음: ' + v.file});
  var t = cs[ci], head = t.value.slice(0, pi), tail = t.value.slice(pi + 1), repl = [];
  if (head.length) repl.push({id: t.id, layout: t.layout, value: head, '@ctype': 'text'});
  repl.push(vid[0]);
  if (tail.length) repl.push({id: uuid(), layout: t.layout, value: tail, '@ctype': 'text'});
  Array.prototype.splice.apply(cs, [ci, 1].concat(repl));
  rep.placed.push(v.title);
}
ed.setDocumentData(d);
return JSON.stringify(rep);
"""


def place_videos_at_slots(chrome_js, slots):
    """slots: [{file, title}]. 각 영상을 자기 [영상 자리 : file] 문단 자리로 옮기고 그 문단을 지운다."""
    out = page_eval(chrome_js, _SLOT_JS.replace("__PARAMS__", json.dumps(list(slots), ensure_ascii=False)),
                    timeout=60)
    if not out or out.startswith("ERR"):
        return {"ok": False, "err": out or "빈 응답"}
    return json.loads(out)


# ---------------------------------------------------------------- 사진만 이어 붙이기
# 사진 폴더를 통째로 본문에 올릴 때 쓴다(photo-folder-to-naver). 사진은 127.0.0.1 임시 서버로
# 내주고 페이지가 fetch해 에디터 API(insertImagesByFile)로 넣는다. 키보드·클립보드를 안 쓴다.
# 완료 판정은 파일명이 아니라 '사진 수 증가 + 전부 업로드됨'으로 한다.
_IMG_STATE_JS = r"""
var ed = SmartEditor._editors[Object.keys(SmartEditor._editors)[0]];
var im = ed.getDocumentData().document.components.filter(function(c){ return c['@ctype'] === 'image'; });
return JSON.stringify({n: im.length, done: im.filter(function(c){ return c.path && c.src; }).length,
                       names: im.map(function(c){ return String(c.fileName); })});
"""

_INSERT_JS = r"""
var P = __PARAMS__;   // {urls, names, types}
var ed = SmartEditor._editors[Object.keys(SmartEditor._editors)[0]];
window.__seUp = 'fetching';
Promise.all(P.urls.map(function(u, i){
  return fetch(u).then(function(r){ if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + P.names[i]); return r.blob(); })
    .then(function(b){ return new File([b], P.names[i], {type: P.types[i]}); });
})).then(function(fs){
  ed.execCommand('insertImagesByFile', {data: fs.map(function(f){ return {file: f, fileName: f.name}; })});
  window.__seUp = 'ok ' + fs.length;
}).catch(function(e){ window.__seUp = 'ERR ' + e; });
return 'started';
"""

_SORT_JS = r"""
var ed = SmartEditor._editors[Object.keys(SmartEditor._editors)[0]];
var d = ed.getDocumentData(), cs = d.document.components;
var order = __ORDER__;   // 에디터 파일명 순서
var im = cs.filter(function(c){ return c['@ctype'] === 'image'; });
var rank = function(c){ var i = order.indexOf(String(c.fileName)); return i < 0 ? 1e9 : i; };
im.sort(function(a, b){ return rank(a) - rank(b); });
var rest = cs.filter(function(c){ return im.indexOf(c) < 0; });
var tail = rest.length > 1 && rest[rest.length - 1]['@ctype'] === 'text' ? rest.pop() : null;
d.document.components = rest.concat(im).concat(tail ? [tail] : []);
ed.setDocumentData(d);
return JSON.stringify(ed.getDocumentData().document.components
  .filter(function(c){ return c['@ctype'] === 'image'; }).map(function(c){ return String(c.fileName); }));
"""


def _ctype(path):
    p = path.lower()
    return "image/gif" if p.endswith(".gif") else "image/png" if p.endswith(".png") else (
        "image/webp" if p.endswith(".webp") else "image/jpeg")


def append_images(chrome_js, paths, batch=10, log=print, batch_timeout=180):
    """paths(한 폴더 안)의 사진을 주어진 순서대로 본문에 올리고 그 순서로 정렬한다.

    에디터 사진 파일명 목록(최종 순서)을 돌려준다. 순서가 어긋나거나 업로드가 멈추면 예외.
    """
    import os
    if not paths:
        return []
    root = os.path.dirname(paths[0])
    if any(os.path.dirname(p) != root for p in paths):
        raise ValueError("사진은 한 폴더 안에 있어야 한다")
    enames = [editor_file_name(os.path.basename(p)) for p in paths]
    if len(set(enames)) != len(enames):
        raise ValueError("에디터 파일명이 겹침(공백/밑줄만 다른 파일)")
    srv, port = serve_dir(root)
    try:
        for i in range(0, len(paths), batch):
            part = paths[i:i + batch]
            before = json.loads(page_eval(chrome_js, _IMG_STATE_JS))["n"]
            params = {"urls": [f"http://127.0.0.1:{port}/" + _up.quote(os.path.basename(p)) for p in part],
                      "names": enames[i:i + batch], "types": [_ctype(p) for p in part]}
            r = page_eval(chrome_js, _INSERT_JS.replace("__PARAMS__", json.dumps(params, ensure_ascii=False)))
            if r != "started":
                raise RuntimeError(f"업로드 시작 실패: {r}")
            t0 = _time.time()
            while True:
                _time.sleep(1.5)
                flag = page_eval(chrome_js, "return String(window.__seUp)")
                if flag.startswith("ERR"):
                    raise RuntimeError(f"{params['names'][0]}부터 업로드 실패: {flag}")
                s = json.loads(page_eval(chrome_js, _IMG_STATE_JS))
                if s["n"] == before + len(part) and s["done"] == s["n"]:
                    break
                if _time.time() - t0 > batch_timeout:
                    raise RuntimeError(f"{params['names'][0]}부터 {batch_timeout}초 안에 안 끝남: "
                                       f"사진 {s['n']}(기대 {before + len(part)}), 완료 {s['done']}, {flag}")
            log(f"      사진 {i + len(part)}/{len(paths)}")
    finally:
        srv.shutdown()
    final = json.loads(page_eval(chrome_js, _SORT_JS.replace("__ORDER__", json.dumps(enames, ensure_ascii=False)),
                                 timeout=60))
    ours = [n for n in final if n in set(enames)]
    if ours != enames:
        raise RuntimeError(f"정렬 후 순서가 다름: 기대 {len(enames)}장, 실제 {len(ours)}장")
    return final
