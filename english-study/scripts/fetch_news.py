#!/usr/bin/env python3
"""Reddit 인기 글 수집 - english-study 스킬용.

r/games(게임 뉴스), r/gaming(게임 소식·재미), r/popular(자유 토픽)의
top-of-day 글을 모아 JSON으로 출력한다.

사용: python3 english-study/scripts/fetch_news.py
출력: {"ok": bool, "failed": [...], "candidates": {"game_news": [...], "game_fun": [...], "free_topic": [...]}}

Reddit은 기본 UA를 차단하므로 브라우저형 UA를 쓴다.
여기서도 차단되면 SKILL.md의 폴백 체인(curl + old.reddit.com)을 따른다.
"""
import json
import sys
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

SUBREDDITS = [
    ("games", "game_news"),
    ("gaming", "game_fun"),
    ("popular", "free_topic"),
]
LIMIT = 10


def fetch_top(sub, limit=LIMIT):
    url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit={limit}&raw_json=1"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    posts = []
    for child in data["data"]["children"]:
        d = child["data"]
        posts.append({
            "title": d.get("title", ""),
            "selftext": (d.get("selftext") or "")[:500],
            "score": d.get("score", 0),
            "num_comments": d.get("num_comments", 0),
            "url": "https://www.reddit.com" + d.get("permalink", ""),
            "external_url": d.get("url_overridden_by_dest") or "",
            "subreddit": d.get("subreddit", sub),
            "over_18": d.get("over_18", False),
        })
    return [p for p in posts if not p["over_18"]]


def main():
    result = {"ok": True, "failed": [], "candidates": {}}
    for sub, key in SUBREDDITS:
        try:
            result["candidates"][key] = fetch_top(sub)
        except Exception as e:
            result["failed"].append({"subreddit": sub, "error": str(e)})
    if not result["candidates"]:
        result["ok"] = False
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
