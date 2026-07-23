#!/usr/bin/env python3
"""4단계(S2): 닉네임 기반 통합검색 스윕 + 작성자 검증.

네이버 카페 통합검색(section.cafe.naver.com)은 '내용 검색'이라 닉네임으로 쳐도
남의 글이 잔뜩 섞인다. 그래서 검색 결과의 각 글을 본문 API로 열어 writer.id가
op5321인 글만 '확정'으로 거른다. 이게 S1/S3가 못 잡는(=내 카페 목록 밖) 공개글을
추가로 발굴하는 경로다.

판정:
  - 200 & writer.id == op5321  → 확정(내 글). posts/raw 저장, source=s2.
  - 200 & writer.id != op5321  → 노이즈, 버림.
  - 403/권한없음               → 작성자 검증 불가. 후보로만 기록.

출력:
  search_found.json       — 확정된 새 글(내 글)
  search_candidates.json  — 검증 불가(403) 또는 기존 인덱스에 이미 있는 매치
"""
import base64
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.parse

from chrome_bridge import ChromeBridge, _osa
import endpoints as EP

USER_ID = "op5321"
SEARCH_TAB_MATCH = "home/search/articles"

READ_JS = r"""
(function(){
 var out=[];
 function deep(doc,d){if(d>5)return;
  try{var items=doc.querySelectorAll('a[href*="ArticleRead.nhn"],a[href*="/articles/"]');
   for(var i=0;i<items.length;i++){var h=items[i].href||'';out.push(h);}}catch(e){}
  try{var ifs=doc.querySelectorAll('iframe');for(var k=0;k<ifs.length;k++)deep(ifs[k].contentWindow.document,d+1);}catch(e){}
 }
 deep(document,0);
 return JSON.stringify(Array.from(new Set(out)));
})()
"""

SCROLL_JS = r"""
(function(){function deep(doc,d){if(d>5)return;try{doc.defaultView.scrollTo(0,doc.body.scrollHeight);}catch(e){}try{var ifs=doc.querySelectorAll('iframe');for(var k=0;k<ifs.length;k++)deep(ifs[k].contentWindow.document,d+1);}catch(e){}}deep(document,0);return 'ok';})()
"""


def osa_eval_on(match, js):
    b64 = base64.b64encode(js.encode()).decode()
    m = match.replace('"', '\\"')
    script = (
        'tell application "Google Chrome"\n'
        'repeat with w in windows\n repeat with t in tabs of w\n'
        f'if (URL of t) contains "{m}" then return execute t javascript "eval(atob(\'{b64}\'))"\n'
        'end repeat\n end repeat\n error "NO_TAB"\n end tell')
    return _osa(script)


def open_search_tab(url):
    m = SEARCH_TAB_MATCH
    # 이미 검색 탭이 있으면 URL만 교체, 없으면 새 탭
    script = (
        'tell application "Google Chrome"\n'
        'repeat with w in windows\n repeat with t in tabs of w\n'
        f'if (URL of t) contains "{m}" then\n set URL of t to "{url}"\n return "reused"\n end if\n'
        'end repeat\n end repeat\n'
        f'make new tab at end of tabs of window 1 with properties {{URL:"{url}"}}\n'
        'return "new"\n end tell')
    return _osa(script)


def parse_ids(href):
    """ArticleRead.nhn?clubid=NNN&articleid=NNN 또는 /cafes/NNN/articles/NNN 에서 추출."""
    try:
        dec = urllib.parse.unquote(href)
    except Exception:
        dec = href
    m = re.search(r"clubid=(\d+).*?articleid=(\d+)", dec)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"/cafes/(\d+)/articles/(\d+)", dec)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def search_nickname(nick, scrolls=4):
    q = urllib.parse.quote(nick)
    url = (f"https://section.cafe.naver.com/ca-fe/home/search/articles"
           f"?q={q}&em=1&sortBy=date")
    open_search_tab(url)
    time.sleep(5)
    seen = set()
    for _ in range(scrolls):
        try:
            raw = osa_eval_on(SEARCH_TAB_MATCH, READ_JS)
            for h in json.loads(raw):
                cid, aid = parse_ids(h)
                if cid and aid:
                    seen.add((cid, aid))
        except Exception as e:
            print(f"  [read err] {e}", file=sys.stderr)
        osa_eval_on(SEARCH_TAB_MATCH, SCROLL_JS)
        time.sleep(1.5)
    return seen


def main():
    corpus = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--")
                          else "./.claude/cafe-corpus").resolve()
    nicks = json.loads((corpus / "nicknames.json").read_text())["nicknames"]
    # 이미 아는 articleId 집합
    known = set()
    idx_path = corpus / "index.json"
    if idx_path.exists():
        for r in json.loads(idx_path.read_text()):
            known.add((r["cafeId"], r["articleId"]))

    cb = ChromeBridge()
    found, candidates = [], []
    verified_seen = set()

    for ni, nick in enumerate(nicks, 1):
        hits = search_nickname(nick)
        new_hits = [(c, a) for (c, a) in hits if (c, a) not in verified_seen]
        print(f"[{ni}/{len(nicks)}] q='{nick}': {len(hits)} hits, "
              f"{len(new_hits)} to verify", file=sys.stderr)
        for (cid, aid) in new_hits:
            verified_seen.add((cid, aid))
            if (cid, aid) in known:
                candidates.append({"cafeId": cid, "articleId": aid, "nick": nick,
                                   "reason": "already_in_index"})
                continue
            try:
                payload = cb.api_get(EP.ARTICLE_CONTENT.format(
                    cafe_id=cid, article_id=aid, menu_id=""))
            except Exception as e:
                if "403" in str(e) or "401" in str(e):
                    candidates.append({"cafeId": cid, "articleId": aid,
                                       "nick": nick, "reason": "no_permission",
                                       "url": f"https://cafe.naver.com/ArticleRead.nhn?clubid={cid}&articleid={aid}"})
                continue
            art = payload.get("result", {}).get("article") or {}
            writer = art.get("writer", {}) or {}
            wid = writer.get("id", "")
            if wid == USER_ID:
                found.append({
                    "cafeId": cid, "articleId": aid, "nick_query": nick,
                    "title": art.get("subject", ""),
                    "writeDate": art.get("writeDate", ""),
                    "writerNick": writer.get("nick", ""),
                    "cafeName": (payload.get("result", {}).get("cafe") or {}).get("name", ""),
                    "url": f"https://cafe.naver.com/ArticleRead.nhn?clubid={cid}&articleid={aid}",
                    "source": "s2",
                })
                print(f"    [CONFIRMED] {cid}/{aid} {art.get('subject','')[:40]}",
                      file=sys.stderr)
            time.sleep(0.25)
        time.sleep(0.5)

    (corpus / "search_found.json").write_text(
        json.dumps(found, ensure_ascii=False, indent=2))
    (corpus / "search_candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2))
    print(f"\n[done] confirmed-new={len(found)} candidates={len(candidates)}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
