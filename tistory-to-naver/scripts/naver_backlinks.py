#!/usr/bin/env python3
"""티스토리 글 안의 티스토리 내부 링크를 네이버 이관본 링크로 바꾼다.

왜 필요한가: 연재 글은 선행 글을 티스토리 주소로 링크해 둔다. 네이버로 옮기고
나면 그 링크는 네이버 밖으로 나가고, 티스토리 원본을 지운 뒤에는 아예 죽는다
(실측 2026-09-19: arnopark.tistory.com/566 은 403). 이미 옮겨 둔 네이버 글이
있으면 그쪽으로 걸어야 내부 연결이 산다.

매핑 원리: 이관된 네이버 글 본문에는 `해당 글은 티스토리 블로그 <URL>의 글을
마이그레이션한 글입니다.` 라는 백링크가 들어간다. 그래서 네이버 블로그 내부
검색으로 티스토리 URL을 그대로 찾으면 이관본이 나온다. 766편을 전수 크롤링할
필요가 없다(요청 1~2회면 끝난다).

검색 결과는 토큰 분해 때문에 566 대신 5660 같은 글이 딸려 올 수 있어, 후보 글을
한 번 받아 정확히 `<host>/<번호>` 가 들어있는지 확인한 뒤에만 채택한다.

사용:
    python3 naver_backlinks.py 566 604 606        # 매핑 조회만
    from naver_backlinks import rewrite_internal_links
    n = rewrite_internal_links(soup, blog_id="op5321")
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from html import unescape as html_unescape

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, ".backlink_cache.json")

TISTORY_HOST = "arnopark.tistory.com"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 "
      "Safari/604.1")

# 네이버는 WebFetch 계열을 막으므로 curl + iPhone UA + Referer 로만 읽힌다.
def _curl(url, referer="https://m.blog.naver.com"):
    out = subprocess.run(
        ["curl", "-s", "-A", UA, "-H", f"Referer: {referer}", url],
        capture_output=True, timeout=20)
    return out.stdout.decode("utf-8", "replace")


def _load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)
    except Exception:
        pass


_TITLE_SUFFIX_RE = re.compile(r"\s*:\s*네이버 블로그\s*$")


def _verify(log_no, tistory_no, blog_id, host):
    """후보 글이 정말 그 티스토리 번호를 백링크로 갖고 있으면 네이버 제목을 준다.

    아니면 None. 검색이 토큰 분해로 566 대신 5660 을 물어오는 경우를 걸러낸다.
    """
    html = _curl(f"https://m.blog.naver.com/{blog_id}/{log_no}",
                 referer=f"https://m.blog.naver.com/{blog_id}")
    if not re.search(rf"{re.escape(host)}/{tistory_no}(?!\d)", html):
        return None
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    title = _TITLE_SUFFIX_RE.sub("", html_unescape(m.group(1)).strip()) if m else ""
    return title or ""


def lookup(tistory_no, blog_id="op5321", host=TISTORY_HOST, cache=None):
    """티스토리 글 번호 -> {"logNo": ..., "title": ...}. 이관본이 없으면 None."""
    tistory_no = str(tistory_no)
    own = cache is None
    if own:
        cache = _load_cache()
    key = f"{host}/{tistory_no}"
    if key in cache:
        return cache[key]

    html = _curl(f"https://m.blog.naver.com/PostSearchList.naver"
                 f"?blogId={blog_id}&searchText={host}%2F{tistory_no}",
                 referer=f"https://m.blog.naver.com/{blog_id}")
    found = None
    for log_no in dict.fromkeys(re.findall(r"logNo=(\d+)", html)):
        title = _verify(log_no, tistory_no, blog_id, host)
        if title is not None:
            found = {"logNo": log_no, "title": title}
            break

    cache[key] = found
    if own:
        _save_cache(cache)
    return found


def resolve_many(numbers, blog_id="op5321", host=TISTORY_HOST):
    """여러 번호를 한 번에 조회한다. 캐시는 마지막에 한 번만 쓴다."""
    cache = _load_cache()
    todo = [n for n in dict.fromkeys(str(x) for x in numbers)
            if f"{host}/{n}" not in cache]
    if todo:
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(lambda n: lookup(n, blog_id, host, cache), todo))
        _save_cache(cache)
    return {n: cache.get(f"{host}/{n}") for n in
            dict.fromkeys(str(x) for x in numbers)}


_LINK_RE = re.compile(
    rf"https?://(?:www\.)?{re.escape(TISTORY_HOST)}/(\d+)(?![\d])")


def rewrite_internal_links(soup, blog_id="op5321", host=TISTORY_HOST,
                           verbose=True):
    """본문 soup 안의 티스토리 내부 링크를 네이버 이관본 링크로 바꾼다.

    바꾸는 곳:
      - <a href>  : 주소 자체
      - <a> 텍스트: 티스토리는 링크 텍스트를 URL 로 두는 경우가 많다. 변환기가
                    href 를 버리고 텍스트만 남기므로 텍스트가 실제 결과물이다.
      - <figure data-ke-type="opengraph"> 의 data-og-* : 링크 카드 주소

    반환: 바꾼 링크 수. 이관본이 없는 링크는 건드리지 않고 그대로 둔다.
    """
    link_re = re.compile(
        rf"https?://(?:www\.)?{re.escape(host)}/(\d+)(?![\d])")

    numbers = set()
    for a in soup.find_all("a", href=True):
        m = link_re.search(a["href"])
        if m:
            numbers.add(m.group(1))
    for fig in soup.select('figure[data-ke-type="opengraph"]'):
        for attr in ("data-og-source-url", "data-og-url"):
            m = link_re.search(fig.get(attr, "") or "")
            if m:
                numbers.add(m.group(1))
    if not numbers:
        return 0

    mapping = resolve_many(sorted(numbers), blog_id, host)

    def naver_url(n):
        rec = mapping.get(n)
        return f"https://blog.naver.com/{blog_id}/{rec['logNo']}" if rec else None

    changed = 0
    for a in soup.find_all("a", href=True):
        m = link_re.search(a["href"])
        if not m:
            continue
        new = naver_url(m.group(1))
        if not new:
            continue
        old_href = a["href"]
        a["href"] = link_re.sub(new, old_href)
        # 링크 텍스트가 주소면 같이 바꾼다 (변환기가 href 를 버리므로 이쪽이 본체).
        for node in list(a.strings):
            if link_re.search(str(node)):
                node.replace_with(link_re.sub(new, str(node)))
        changed += 1

    # 링크 카드: 속성뿐 아니라 화면에 찍히는 제목·호스트 텍스트까지 바꾼다.
    # 변환기가 카드의 p.og-title / p.og-host 텍스트를 본문에 그대로 실어 보내므로,
    # 여기를 두면 네이버 글에 티스토리 원제와 호스트가 남는다.
    for fig in soup.select('figure[data-ke-type="opengraph"]'):
        num = None
        for attr in ("data-og-source-url", "data-og-url"):
            m = link_re.search(fig.get(attr, "") or "")
            if m:
                num = m.group(1)
                break
        if not num:
            continue
        new = naver_url(num)
        if not new:
            continue
        rec = mapping[num]
        for attr in ("data-og-source-url", "data-og-url"):
            if fig.get(attr):
                fig[attr] = link_re.sub(new, fig[attr])
        for a in fig.find_all("a"):
            for attr in ("href", "data-source-url"):
                if a.get(attr) and link_re.search(a[attr]):
                    a[attr] = link_re.sub(new, a[attr])
        if rec.get("title"):
            fig["data-og-title"] = rec["title"]
            node = fig.select_one("p.og-title")
            if node:
                node.string = rec["title"]
        if fig.get("data-og-host"):
            fig["data-og-host"] = "blog.naver.com"
        node = fig.select_one("p.og-host")
        if node:
            node.string = "blog.naver.com"
        changed += 1

    if verbose:
        for n in sorted(numbers, key=int):
            rec = mapping.get(n)
            if rec:
                print(f"      링크 치환: {host}/{n} -> "
                      f"blog.naver.com/{blog_id}/{rec['logNo']}")
            else:
                print(f"      링크 유지: {host}/{n} (네이버 이관본 없음)")
    return changed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for n, rec in resolve_many(sys.argv[1:]).items():
        if rec:
            print(f"{TISTORY_HOST}/{n} -> blog.naver.com/op5321/{rec['logNo']}"
                  f"  ({rec.get('title', '')})")
        else:
            print(f"{TISTORY_HOST}/{n} -> (이관본 없음)")
