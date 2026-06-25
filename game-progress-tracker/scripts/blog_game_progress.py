#!/usr/bin/env python3
"""op5321 네이버 블로그에서 특정 게임 연재글의 현재 진행상황을 뽑는다.

비결정적 부분(전체 챕터 목록 웹검색·남은 챕터 계산)은 하지 않는다.
오직 결정적인 수집만 한다:
  1) 블로그 전체 글 목록을 PostTitleListAsync로 페이지네이션해 수집
  2) 게임 제목(태그)으로 필터 → 연재글만 추림
  3) 최신화(=가장 큰 logNo) 본문을 모바일 UA로 받아 태그 제거한 텍스트 출력

WebFetch는 naver 차단됨 → 반드시 curl/urllib. RSS는 최근 50개뿐이라 못 씀.
PostTitleListAsync JSON은 invalid \\escape 포함이라 json.loads 깨짐 → 정규식 파싱.

usage:
  python3 blog_game_progress.py "붉은사막"
  python3 blog_game_progress.py "붉은사막" --blog-id op5321 --max-pages 12
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile Safari/604.1")


def _get(url, referer=None, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if referer:
        req.add_header("Referer", referer)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_all_posts(blog_id, max_pages):
    """(logNo, title) 전체 목록. title은 URL 디코드된 평문."""
    base = ("https://blog.naver.com/PostTitleListAsync.naver"
            "?blogId={bid}&viewdate=&currentPage={pg}"
            "&categoryNo=0&parentCategoryNo=0&countPerPage=30")
    ref = f"https://blog.naver.com/{blog_id}"
    posts = []
    for pg in range(1, max_pages + 1):
        try:
            raw = _get(base.format(bid=blog_id, pg=pg), referer=ref)
        except Exception as e:
            sys.stderr.write(f"[warn] page {pg} 실패: {e}\n")
            break
        # json.loads는 invalid escape로 깨지므로 정규식으로 직접 추출
        pairs = re.findall(r'"logNo":"(\d+)","title":"(.*?)","categoryNo"', raw)
        if not pairs:
            break
        for ln, t in pairs:
            posts.append((ln, urllib.parse.unquote_plus(t)))
        if len(pairs) < 30:  # 마지막 페이지
            break
    return posts


def normalize(s):
    return re.sub(r"[\[\]\s_·]+", "", s).lower()


def filter_game(posts, game):
    """게임 제목이 들어간 글만. 태그형([게임] N. ...)·공백/대괄호 무시 매칭."""
    g = normalize(game)
    hits = [(ln, t) for ln, t in posts if g in normalize(t)]
    # 최신순(logNo 큰 순)
    hits.sort(key=lambda x: int(x[0]), reverse=True)
    return hits


def tag_index(posts):
    """모든 글의 [대괄호 태그]별 글 수. 매칭 0/저조 시 후보 태그 역추적용.

    예: 사용자가 '파이어레드'로 물어도 연재 태그는 '[포켓몬 파레리그]'.
    """
    counts = {}
    for _, t in posts:
        m = re.match(r"\s*\[([^\]]+)\]", t)
        if m:
            tag = m.group(1).strip()
            counts[tag] = counts.get(tag, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


def strip_html(html):
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", html)
    import html as _h
    txt = _h.unescape(txt)
    # 본문 시작(제목 줄)부터 해시태그 전까지가 핵심
    txt = re.sub(r"[​ ]", "", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def fetch_body(blog_id, log_no, limit=3500):
    url = f"https://m.blog.naver.com/{blog_id}/{log_no}"
    html = _get(url)
    txt = strip_html(html)
    # 본문 영역만: '본문 바로가기' 이후 ~ 해시태그/JSON 전까지 잘라 가독성↑
    m = re.search(r"본문 바로가기(.*?)(#\S|\{\"title\")", txt, re.S)
    body = m.group(1) if m else txt
    return body.strip()[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game", help="게임 제목 (예: 붉은사막)")
    ap.add_argument("--blog-id", default="op5321")
    ap.add_argument("--max-pages", type=int, default=12)
    args = ap.parse_args()

    posts = fetch_all_posts(args.blog_id, args.max_pages)
    hits = filter_game(posts, args.game)

    out = {
        "blog_id": args.blog_id,
        "game": args.game,
        "total_posts_scanned": len(posts),
        "matched_count": len(hits),
        "posts": [
            {"logNo": ln, "title": t,
             "url": f"https://blog.naver.com/{args.blog_id}/{ln}"}
            for ln, t in hits
        ],
    }
    # 매칭이 0이거나 1개뿐이면 태그 축약(파이어레드→파레리그) 가능성. 후보 태그 제공.
    if len(hits) <= 1:
        out["hint"] = ("매칭이 적습니다. 연재 태그가 축약형일 수 있습니다 "
                       "(예: 파이어레드→파레리그). available_tags에서 후보를 골라 재실행하세요.")
        out["available_tags"] = tag_index(posts)
    if hits:
        latest_ln, latest_title = hits[0]
        out["latest"] = {
            "logNo": latest_ln,
            "title": latest_title,
            "url": f"https://blog.naver.com/{args.blog_id}/{latest_ln}",
        }
        try:
            out["latest"]["body_excerpt"] = fetch_body(args.blog_id, latest_ln)
        except Exception as e:
            out["latest"]["body_error"] = str(e)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
