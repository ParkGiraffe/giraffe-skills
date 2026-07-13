#!/usr/bin/env python3
"""네이버 검색 노출(서치 블락) 검수.

글별로 네이버 모바일 블로그탭 검색에 실제로 잡히는지 확인한다.
- 쿼리: 글 제목에서 [카테고리]·번호를 뗀 핵심 문구(+ 부제 분리 시 두 쿼리)
- 판정: 검색 결과 HTML에 해당 logNo(정확 매칭) 또는 blogId가 있는가
- 보조: 글 robots 메타(noindex면 네이버가 색인 자체를 막은 것 — 별개 문제)

사용법:
  check_search.py <URL_또는_logNo> [<URL_또는_logNo> ...] [--blog-id op5321]
  check_search.py --recent N [--blog-id op5321]        # 최근 N개 글 일괄

해석 가이드(중요):
  - 특정 글만 미노출 + 다른 글은 노출 → 그 글 특이(품질/노출 필터 의심). 재발행·수정 검토.
  - 전부 미노출 → 블로그 단위 문제 또는 색인 지연. 서치어드바이저 확인.
  - 발행 직후는 색인 전일 수 있음 → 몇 시간 뒤 재검수.
"""
import re, sys, time, argparse, subprocess, urllib.parse
import html as H

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def curl(url, referer="https://blog.naver.com/"):
    r = subprocess.run(["curl", "-sSL", "-A", UA, "-e", referer, url],
                       capture_output=True, text=True, timeout=30)
    return r.stdout or ""


def fetch_post(blog_id, log, retries=4):
    """제목·robots 메타. m.blog SSR이 불안정하므로 재시도.
    글이 삭제/비공개면 블로그 홈으로 떨어져 엉뚱한 og:title이 잡힘 — logNo 포함 여부로 진짜 글인지 검증."""
    for _ in range(retries):
        h = curl(f"https://m.blog.naver.com/{blog_id}/{log}")
        m = re.search(r'<meta property="og:title" content="([^"]*)"', h)
        if m and log in h:
            rb = re.search(r'<meta name="robots" content="([^"]*)"', h)
            return H.unescape(m.group(1)), (rb.group(1) if rb else "?")
        time.sleep(1.5)
    return None, "?"


def queries_from_title(title):
    """제목 → 검색 쿼리 후보. [카테고리] N. 프리픽스 제거, 본문:서브 분리."""
    t = re.sub(r"^\[[^\]]*\]\s*", "", title)
    t = re.sub(r"^\d+\.\s*", "", t)
    qs = [t.strip()]
    for sep in (" : ", " - "):
        if sep in t:
            a, b = t.split(sep, 1)
            qs += [a.strip(), b.strip()]
            break
    return [q for q in dict.fromkeys(qs) if len(q) >= 4][:3]


def search_hit(query, blog_id, log):
    enc = urllib.parse.quote(query)
    h = curl(f"https://m.search.naver.com/search.naver?where=m_blog&query={enc}",
             referer="https://m.search.naver.com/")
    return (f"{blog_id}/{log}" in h), (blog_id in h)


def recent_posts(blog_id, n):
    """post-list API(스로틀 잦음 — 재시도) → 실패 시 RSS."""
    for _ in range(6):
        h = curl(f"https://m.blog.naver.com/api/blogs/{blog_id}/post-list?categoryNo=0&itemCount={n}&page=1",
                 referer=f"https://m.blog.naver.com/{blog_id}")
        import json
        try:
            items = json.loads(h).get("result", {}).get("items", [])
        except Exception:
            items = []
        if items:
            return [(str(p["logNo"]), H.unescape(p.get("titleWithInspectMessage", ""))) for p in items[:n]]
        time.sleep(2)
    rss = curl(f"https://rss.blog.naver.com/{blog_id}.xml")
    out = []
    for it in re.findall(r"<item>(.*?)</item>", rss, re.S)[:n]:
        lm = re.search(r"/(\d{10,})", it)
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        if lm:
            out.append((lm.group(1), H.unescape(tm.group(1).strip()) if tm else ""))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="*")
    ap.add_argument("--blog-id", default="op5321")
    ap.add_argument("--recent", type=int, default=0)
    args = ap.parse_args()

    posts = []
    if args.recent:
        posts = recent_posts(args.blog_id, args.recent)
    for t in args.targets:
        m = re.search(r"/(\d{8,})", t) or re.search(r"logNo=(\d{8,})", t)
        log = m.group(1) if m else (t if t.isdigit() else None)
        if log:
            posts.append((log, None))
    if not posts:
        ap.error("대상 없음: logNo/URL을 주거나 --recent N")

    blocked, ok = [], []
    for log, title in posts:
        if not title:
            title, robots = fetch_post(args.blog_id, log)
        else:
            _, robots = fetch_post(args.blog_id, log)
        if not title:
            print(f"[{log}] 글 확인 불가(삭제/비공개/fetch 실패) — 건너뜀")
            continue
        hit_exact = hit_blog = False
        used = ""
        for q in queries_from_title(title):
            e, b = search_hit(q, args.blog_id, log)
            hit_exact |= e
            hit_blog |= b
            if e:
                used = q
                break
            time.sleep(0.8)
        status = "노출 OK" if hit_exact else "미노출"
        extra = f" (robots={robots})" if "noindex" in robots.lower() else ""
        print(f"[{log}] {status}{extra} | {title[:46]}" + (f" | 쿼리='{used}'" if used else ""))
        (ok if hit_exact else blocked).append((log, title))

    print()
    print(f"결과: 노출 {len(ok)} / 미노출 {len(blocked)}")
    if blocked and ok:
        print("해석: 블로그는 정상 색인 중 — 미노출 글은 글 특이 필터/지연 의심.")
        print("      발행 직후면 몇 시간 뒤 재검수, 지속되면 수정 재저장 또는 naver-to-naver 재발행(+가리기).")
    elif blocked:
        print("해석: 전부 미노출 — 블로그 단위 문제/색인 지연 가능. 서치어드바이저에서 확인.")
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
