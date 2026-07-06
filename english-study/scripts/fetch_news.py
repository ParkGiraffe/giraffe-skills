#!/usr/bin/env python3
"""Reddit 인기 글 수집 - english-study 스킬용 (RSS 기반).

Reddit은 익명 JSON API(www/old/api.reddit.com)를 브라우저 UA로도 403 차단한다
(2026-07-06 실측). RSS(Atom)만 열려 있고, 익명 RSS는 IP당 분당 1요청 수준의
rate limit이 있어 요청을 2개로 압축했다:
  1) r/games+gaming 멀티레딧 top-of-day (게임 뉴스+소식, limit=25)
  2) r/popular top-of-day (자유 토픽, limit=10)
요청 사이에는 x-ratelimit-reset 헤더만큼 대기한다. 총 실행 약 1~2분.

사용: python3 english-study/scripts/fetch_news.py   (Bash timeout 180초 이상)
출력: {"ok": bool, "failed": [{"feed", "error"}],
       "candidates": {"game_news": [...], "game_fun": [...], "free_topic": [...]}}
각 배열은 top-of-day 순서(상단 = 고득점)다.
"""
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
ATOM = "{http://www.w3.org/2005/Atom}"
FEEDS = [
    ("games+gaming", "https://www.reddit.com/r/games+gaming/top/.rss?t=day&limit=25"),
    ("popular", "https://www.reddit.com/r/popular/top/.rss?t=day&limit=10"),
]
MAX_WAIT = 90


def reset_seconds(headers):
    try:
        return int(float(headers.get("x-ratelimit-reset", "60")))
    except (TypeError, ValueError):
        return 60


def fetch(url):
    """(xml_text, 다음 요청까지 대기초) 반환. 429면 reset만큼 기다렸다 1회 재시도."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8"), reset_seconds(resp.headers)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                time.sleep(min(reset_seconds(e.headers) + 5, MAX_WAIT))
                continue
            raise


def parse_entries(xml_text):
    posts = []
    for entry in ET.fromstring(xml_text).iter(f"{ATOM}entry"):
        link = entry.find(f"{ATOM}link")
        cat = entry.find(f"{ATOM}category")
        author = entry.findtext(f"{ATOM}author/{ATOM}name") or ""
        content = html.unescape(entry.findtext(f"{ATOM}content") or "")
        m = re.search(r'href="([^"]+)">\s*\[link\]', content)
        external = m.group(1) if m else ""
        if external.startswith("https://www.reddit.com"):
            external = ""  # 셀프 포스트는 원문 링크가 곧 레딧 글
        posts.append({
            "title": entry.findtext(f"{ATOM}title") or "",
            "url": link.get("href") if link is not None else "",
            "external_url": external,
            "subreddit": cat.get("term") if cat is not None else "",
            "author": author.removeprefix("/u/"),
            "published": entry.findtext(f"{ATOM}updated") or "",
        })
    return posts


def main():
    result = {"ok": True, "failed": [], "candidates": {}}
    wait = 0
    for i, (name, url) in enumerate(FEEDS):
        if i > 0:
            time.sleep(min(wait + 5, MAX_WAIT))
        try:
            xml_text, wait = fetch(url)
            posts = parse_entries(xml_text)
        except Exception as e:
            result["failed"].append({"feed": name, "error": str(e)})
            wait = 60
            continue
        if name == "games+gaming":
            result["candidates"]["game_news"] = [p for p in posts if p["subreddit"].lower() == "games"]
            result["candidates"]["game_fun"] = [p for p in posts if p["subreddit"].lower() == "gaming"]
        else:
            result["candidates"]["free_topic"] = posts
    if not result["candidates"]:
        result["ok"] = False
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
