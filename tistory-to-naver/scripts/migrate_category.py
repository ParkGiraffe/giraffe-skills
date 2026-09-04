#!/usr/bin/env python3
"""Batch-migrate every post in a Tistory category to Naver, in order.

Wraps migrate.py (per-post paste) and, optionally, publish_with_category.py
(category + publish). Publishing is OPT-IN: without --publish, each post is
left as a draft in the editor for you to review and publish by hand, and the
loop stops after the first one (migrate.py aborts on a non-empty editor).
With --publish <testid>, each post is migrated AND published before moving to
the next, so the whole category goes through unattended.

Usage:
  python3 migrate_category.py <CATEGORY_URL> [options]

Options:
  --publish <testid>  set this category (Naver categoryItemText id) and publish
                      each post before the next. e.g. 142 = GoodWishes 제작기.
                      OMIT to only paste drafts (default, safe).
  --grep <regex>      only posts whose title matches (e.g. '제작기')
  --start <N>         skip the first N matched posts (resume a batch)
  --limit <N>         migrate at most N posts
  --reverse           process newest-first (default: oldest-first)
  --dry-run           just list what would be migrated, do nothing

Discovery: walks the category's paginated list pages, collecting
<a href="/NUM"> links and their titles. Series posts like
"[... 제작기] 13. ..." are ordered by the leading number when present,
otherwise by ascending post id.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))          # <repo>/tistory-to-naver/scripts
REPO = os.path.dirname(os.path.dirname(HERE))              # <repo>
# 기존 postwrite 탭을 절대 건드리지 않는 새 탭 경로가 디폴트다.
# migrate.py 를 직접 부르면 '첫 번째' postwrite 탭을 조준해서, 사용자가 손으로
# 쓰던 초안 위에 덮어쓰는 사고가 난다 (2026-08-21).
MIGRATE = os.path.join(HERE, "migrate_fresh_tab.py")
PUBLISH = os.path.join(REPO, "_lib", "publish_with_category.py")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _encode(url):
    """비ASCII 경로를 percent-encoding 한다.

    티스토리 카테고리 URL 은 '/category/잡동사니 게임일기/로스트아크' 처럼 한글이
    그대로 들어오는데, urlopen 은 요청 라인을 ascii 로 encode 하므로 그대로 넘기면
    UnicodeEncodeError 로 죽는다. 이미 인코딩된 %XX 는 다시 인코딩하지 않는다.
    """
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        parts.scheme, parts.netloc,
        urllib.parse.quote(parts.path, safe="/%"),
        urllib.parse.quote(parts.query, safe="=&%"),
        parts.fragment,
    ))


def fetch(url):
    req = urllib.request.Request(_encode(url), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def discover(category_url):
    """Return [(post_id:int, title:str, url:str)] for every post in the category."""
    seen = {}
    for page in range(1, 21):  # generous page cap
        sep = "&" if "?" in category_url else "?"
        h = fetch(f"{category_url}{sep}page={page}")
        found_this_page = False
        # match list anchors: href="/NUM" ... > title text (title may be nested)
        for m in re.finditer(r'href="/(\d+)"[^>]*>(?:\s*<[^>]+>)*\s*([^<>]{4,90})</', h):
            pid = int(m.group(1))
            title = html.unescape(m.group(2).strip())
            if not title or title.isdigit() or title in ("본문 바로가기",):
                continue
            if pid not in seen:
                seen[pid] = title
                found_this_page = True
        # stop when a page adds nothing new (end of pagination)
        if page > 1 and not found_this_page:
            break
    rows = [(pid, t, f"https://arnopark.tistory.com/{pid}") for pid, t in seen.items()]
    return rows


def series_key(row):
    """Sort by the leading series number in the title if present, else post id."""
    pid, title, _ = row
    m = re.search(r"]\s*(\d+)\.", title)
    return (0, int(m.group(1))) if m else (1, pid)


def run(cmd):
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("category_url")
    ap.add_argument("--publish", metavar="TESTID", default=None)
    ap.add_argument("--publish-name", default=None,
                    help="발행 전 검증에 쓸 카테고리명. 생략하면 publish_with_category.py "
                         "기본값('제작기')으로 검증돼서 다른 카테고리에선 멈춘다.")
    ap.add_argument("--private", action="store_true",
                    help="비공개로 발행 (--publish 와 함께 쓴다)")
    ap.add_argument("--manifest", default=None,
                    help="편별 제목·태그를 담은 JSON. [{id, title, tags, core_tags}, ...] "
                         "형식이며, 주어지면 대상 목록과 순서를 이 파일이 결정한다.")
    ap.add_argument("--grep", default=None)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--reverse", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    manifest = {}
    if a.manifest:
        with open(a.manifest, encoding="utf-8") as f:
            entries = json.load(f)
        manifest = {int(e["id"]): e for e in entries}
        rows = [(int(e["id"]), e.get("title", ""),
                 f"https://arnopark.tistory.com/{int(e['id'])}") for e in entries]
        print(f"[manifest] {len(rows)}편을 {a.manifest} 에서 읽었습니다 (카테고리 탐색 생략)")
    else:
        rows = discover(a.category_url)
    if a.grep:
        rx = re.compile(a.grep)
        rows = [r for r in rows if rx.search(r[1])]
    if not manifest:
        rows.sort(key=series_key, reverse=a.reverse)
    elif a.reverse:
        rows.reverse()
    rows = rows[a.start:]
    if a.limit:
        rows = rows[: a.limit]

    print(f"== {len(rows)} post(s) to migrate "
          f"({'publish ' + a.publish if a.publish else 'draft-only'}) ==")
    for pid, title, url in rows:
        print(f"  {pid}  {title[:60]}")
    if a.dry_run:
        print("(dry-run; nothing done)")
        return
    if not a.publish:
        print("\nNOTE: no --publish, so only the FIRST post will paste; "
              "migrate.py aborts on a non-empty editor. Publish it, then rerun "
              "with --start to continue, or pass --publish <testid> for the full batch.")

    for i, (pid, title, url) in enumerate(rows, 1):
        print(f"\n########## [{i}/{len(rows)}] MIGRATE {pid} : {title[:50]} ##########")
        cmd = [sys.executable, MIGRATE, url]
        entry = manifest.get(pid, {})
        if entry.get("title"):
            cmd += ["--title", entry["title"]]
        if entry.get("tags"):
            cmd += ["--tags", entry["tags"]]
        if entry.get("core_tags"):
            cmd += ["--core-tags", entry["core_tags"]]
        if run(cmd) != 0:
            print(f"[STOP] migrate failed at {pid}")
            sys.exit(1)
        if a.publish:
            print(f"########## [{i}/{len(rows)}] PUBLISH {pid} (cat {a.publish}) ##########")
            pcmd = [sys.executable, PUBLISH, a.publish]
            if a.publish_name:
                pcmd.append(a.publish_name)
            if a.private:
                pcmd.append("--private")
            if run(pcmd) != 0:
                print(f"[STOP] publish failed at {pid}")
                sys.exit(2)
        else:
            print("[draft pasted; stopping — publish manually or use --publish]")
            break
    print("\n== done ==")


if __name__ == "__main__":
    main()
