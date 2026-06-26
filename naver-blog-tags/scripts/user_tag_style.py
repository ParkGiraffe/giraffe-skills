#!/usr/bin/env python3
"""사용자가 기존 글에 실제로 단 네이버 블로그 태그를 읽어 '태그 형식'을 학습한다.

원리(이 블로그 환경 전용):
- 사용자는 네이버에 먼저 쓰고 티스토리(arnopark)에 '정리본' 백링크를 만든다.
- 티스토리 정리본 본문엔 m.blog.naver.com/<id>/<logNo> 백링크가 박혀 있다.
- 네이버 모바일 글 HTML 안 JSON 의 "tagNames" 필드에 진짜 태그가 들어있다
  (표준 JSON 이스케이프: \\"tagNames\\":\\"\\uXXXX,...\\").
- 네이버는 WebFetch 차단 → curl + iPhone UA + Referer 로만 읽힌다.

사용:
    python3 user_tag_style.py <검색어> [--limit N] [--blog op5321] [--tistory arnopark]
    python3 user_tag_style.py --logno 224321870566 [224324010450 ...]   # 직접 지정

출력: 글별 태그 목록 + 전체 빈도. 가장 비슷한 글의 태그가 새 글 태그의 템플릿.
"""
import sys, re, json, codecs, argparse, urllib.parse, subprocess
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")


def curl(url, referer):
    return subprocess.run(
        ["curl", "-sL", "-A", UA, "-H", f"Referer: {referer}", url],
        capture_output=True, text=True).stdout


def search_tistory(tistory, term):
    """arnopark 티스토리에서 검색어로 글 id 목록을 모은다."""
    url = f"https://{tistory}.tistory.com/search/{urllib.parse.quote(term)}"
    h = curl(url, f"https://{tistory}.tistory.com/")
    ids = set(re.findall(r'href="/(\d+)"', h))
    ids |= set(re.findall(re.escape(tistory) + r'\.tistory\.com/(\d+)"', h))
    return sorted(ids, key=int)


def tistory_to_naver_logno(tistory, post_id):
    """정리본 글에서 네이버 백링크 logNo 를 뽑는다."""
    h = curl(f"https://{tistory}.tistory.com/{post_id}", f"https://{tistory}.tistory.com/")
    m = re.search(r'm\.blog\.naver\.com/\w+/(\d+)', h)
    if not m:
        m = re.search(r'blog\.naver\.com/\w+/(\d+)', h) or \
            re.search(r'logNo=(\d+)', h)
    return m.group(1) if m else None


def naver_tags(blog, logno):
    """네이버 모바일 글에서 tagNames 를 디코드해 태그 리스트를 반환."""
    h = curl(f"https://m.blog.naver.com/{blog}/{logno}", "https://m.blog.naver.com/")
    tags = []
    for raw in re.findall(r'tagNames\\":\\"(.*?)\\"', h):
        try:
            dec = codecs.decode(raw, "unicode_escape")
        except Exception:
            dec = raw
        tags += [t for t in dec.split(",") if t.strip()]
    seen = []
    for t in tags:
        if t not in seen:
            seen.append(t)
    return seen


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("term", nargs="?", help="티스토리 검색어")
    ap.add_argument("--blog", default="op5321")
    ap.add_argument("--tistory", default="arnopark")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--logno", nargs="+", help="네이버 logNo 직접 지정")
    a = ap.parse_args(argv)

    jobs = []  # (label, logno)
    if a.logno:
        jobs = [(ln, ln) for ln in a.logno]
    elif a.term:
        ids = search_tistory(a.tistory, a.term)[: a.limit]
        with ThreadPoolExecutor(max_workers=8) as ex:
            for pid, ln in zip(ids, ex.map(lambda p: tistory_to_naver_logno(a.tistory, p), ids)):
                if ln:
                    jobs.append((f"tistory/{pid}", ln))
    else:
        ap.error("검색어 또는 --logno 필요")

    freq = Counter()
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda j: (j[0], j[1], naver_tags(a.blog, j[1])), jobs))
    for label, ln, tags in results:
        print(f"\n[{label}  logNo={ln}]  ({len(tags)})")
        print("   " + (" · ".join(tags) if tags else "(태그 없음)"))
        freq.update(tags)
    print("\n===== 태그 빈도 =====")
    for t, c in freq.most_common():
        print(f"{c:>2}  #{t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
