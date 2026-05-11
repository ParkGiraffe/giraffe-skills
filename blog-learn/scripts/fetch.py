#!/usr/bin/env python3
"""Fetch entire Naver blog archive for a given blogId.

Usage:
  fetch.py <blogId> <corpus_dir> [--limit N] [--refresh]

Writes:
  <corpus_dir>/raw/rss.xml
  <corpus_dir>/raw/html/{logNo}.html
  <corpus_dir>/posts/{logNo}.md
  <corpus_dir>/index.json
"""
import sys, os, re, json, time, subprocess, pathlib, hashlib, urllib.parse, html as html_lib
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

HERE = pathlib.Path(__file__).resolve().parent
PARSER = HERE.parent.parent / "_lib" / "parse_smarteditor.py"


def curl(url: str, referer: str | None = None, retries: int = 3) -> tuple[int, bytes]:
    for attempt in range(retries):
        cmd = ["curl", "-sS", "-L", "-A", UA, "-w", "\n__HTTP__%{http_code}__", url]
        if referer:
            cmd[3:3] = ["-e", referer]
        try:
            out = subprocess.check_output(cmd, timeout=30)
        except subprocess.CalledProcessError as e:
            out = e.output or b""
        m = re.search(rb"\n__HTTP__(\d+)__$", out)
        code = int(m.group(1)) if m else 0
        body = out[:m.start()] if m else out
        if code == 200:
            return code, body
        if code in (429, 503):
            time.sleep(2 ** attempt)
            continue
        if code == 0:
            time.sleep(1 + attempt)
            continue
        return code, body
    return code, body


def fetch_rss(blog_id: str, dest: pathlib.Path) -> list[dict]:
    url = f"https://rss.blog.naver.com/{blog_id}.xml"
    code, body = curl(url)
    if code != 200:
        print(f"[rss] HTTP {code}", file=sys.stderr)
        return []
    dest.write_bytes(body)
    text = body.decode("utf-8", errors="replace")
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", text, re.DOTALL):
        blk = m.group(1)
        def grab(tag):
            mm = re.search(rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", blk, re.DOTALL) \
                or re.search(rf"<{tag}>([^<]*)</{tag}>", blk, re.DOTALL)
            return mm.group(1).strip() if mm else ""
        link = grab("link")
        log_no = ""
        mm = re.search(r"/(\d{6,})(?:\?|$)", link)
        if mm: log_no = mm.group(1)
        items.append({
            "log_no": log_no,
            "title": grab("title"),
            "category": grab("category"),
            "link": link,
            "pubDate": grab("pubDate"),
            "description": grab("description"),
        })
    return items


def fetch_archive_page(blog_id: str, page: int) -> list[dict]:
    """Use PostTitleListAsync.naver which returns JSON-like payload with logNo list."""
    url = (f"https://blog.naver.com/PostTitleListAsync.naver?"
           f"blogId={blog_id}&currentPage={page}&categoryNo=0&parentCategoryNo=&countPerPage=30")
    code, body = curl(url, referer=f"https://blog.naver.com/{blog_id}")
    if code != 200:
        return []
    text = body.decode("utf-8", errors="replace")
    # response is JSON-ish. Try direct json.
    try:
        data = json.loads(text)
    except Exception:
        # sometimes it's wrapped or has trailing commas; try to salvage logNos
        nos = re.findall(r'"logNo"\s*:\s*"?(\d+)"?', text)
        titles = re.findall(r'"title"\s*:\s*"([^"]*)"', text)
        return [{"log_no": n, "title": t} for n, t in zip(nos, titles)]
    posts = []
    # shape: {"resultMessage":"Success","postList":[{"logNo":"...","title":"...","categoryName":"..."}, ...], "totalCount":N}
    for p in data.get("postList", []) if isinstance(data, dict) else []:
        raw_title = p.get("title", "")
        try:
            title = urllib.parse.unquote_plus(raw_title)
        except Exception:
            title = raw_title
        posts.append({
            "log_no": str(p.get("logNo", "")),
            "title": html_lib.unescape(title),
            "category_no": str(p.get("categoryNo", "")),
            "date": p.get("addDate", ""),
        })
    return posts


def enumerate_archive(blog_id: str, limit: int | None = None) -> list[dict]:
    all_posts: dict[str, dict] = {}
    page = 1
    empty_streak = 0
    while True:
        posts = fetch_archive_page(blog_id, page)
        if not posts:
            empty_streak += 1
            if empty_streak >= 2:
                break
            page += 1
            time.sleep(0.3)
            continue
        empty_streak = 0
        new = 0
        for p in posts:
            if p["log_no"] and p["log_no"] not in all_posts:
                all_posts[p["log_no"]] = p
                new += 1
        print(f"[archive] page {page}: {len(posts)} items, {new} new, total {len(all_posts)}",
              file=sys.stderr)
        if new == 0:
            break
        if limit and len(all_posts) >= limit:
            break
        page += 1
        time.sleep(0.3)
    return list(all_posts.values())


def fetch_post(blog_id: str, log_no: str, raw_dir: pathlib.Path,
               posts_dir: pathlib.Path) -> dict | None:
    raw_path = raw_dir / f"{log_no}.html"
    md_path = posts_dir / f"{log_no}.md"
    if not raw_path.exists():
        url = f"https://m.blog.naver.com/{blog_id}/{log_no}"
        code, body = curl(url, referer=f"https://m.blog.naver.com/{blog_id}")
        if code != 200:
            print(f"[post {log_no}] HTTP {code}", file=sys.stderr)
            return None
        raw_path.write_bytes(body)
    # parse
    out = subprocess.check_output(
        ["python3", str(PARSER), str(raw_path), log_no, str(md_path)],
        stderr=subprocess.STDOUT,
    )
    try:
        rec = json.loads(out.decode("utf-8").strip().splitlines()[-1])
    except Exception:
        return None
    rec["raw"] = str(raw_path)
    rec["md"] = str(md_path)
    rec["hash"] = hashlib.sha1(raw_path.read_bytes()).hexdigest()[:12]
    return rec


def main():
    if len(sys.argv) < 3:
        print("usage: fetch.py <blogId> <corpus_dir> [--limit N] [--refresh]",
              file=sys.stderr); sys.exit(2)
    blog_id = sys.argv[1]
    corpus = pathlib.Path(sys.argv[2]).resolve()
    limit = None
    refresh = False
    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--limit":
            limit = int(sys.argv[i+1]); i += 2
        elif sys.argv[i] == "--refresh":
            refresh = True; i += 1
        else:
            i += 1

    raw = corpus / "raw"
    html_dir = raw / "html"
    posts_dir = corpus / "posts"
    drafts_dir = corpus / "drafts"
    for d in (raw, html_dir, posts_dir, drafts_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 1. RSS (fast seed)
    rss_items = fetch_rss(blog_id, raw / "rss.xml")
    print(f"[rss] {len(rss_items)} items", file=sys.stderr)

    # 2. Full archive via PostTitleListAsync
    archive = enumerate_archive(blog_id, limit=limit)
    print(f"[archive] total {len(archive)}", file=sys.stderr)

    # merge: archive is authoritative for log_no list, RSS adds description
    by_log = {p["log_no"]: dict(p) for p in archive if p.get("log_no")}
    for item in rss_items:
        if item["log_no"] in by_log:
            by_log[item["log_no"]].setdefault("description", item.get("description", ""))
        elif item["log_no"]:
            by_log[item["log_no"]] = item

    # existing index
    idx_path = corpus / "index.json"
    existing = {}
    if idx_path.exists() and not refresh:
        try:
            existing = {p["log_no"]: p for p in json.loads(idx_path.read_text())}
        except Exception:
            existing = {}

    log_nos = list(by_log.keys())
    if limit:
        log_nos = log_nos[:limit]

    # 3. fetch each post (skip already cached)
    to_fetch = [ln for ln in log_nos if ln not in existing or refresh
                or not (html_dir / f"{ln}.html").exists()
                or not (posts_dir / f"{ln}.md").exists()]
    print(f"[fetch] {len(to_fetch)}/{len(log_nos)} need download", file=sys.stderr)

    done = dict(existing)
    errors = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(fetch_post, blog_id, ln, html_dir, posts_dir): ln
                for ln in to_fetch}
        for i, fut in enumerate(as_completed(futs)):
            ln = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:
                print(f"[post {ln}] ERR {e}", file=sys.stderr)
                errors += 1
                continue
            if rec is None:
                errors += 1
                continue
            merged = dict(by_log.get(ln, {}))
            merged.update(rec)
            done[ln] = merged
            if (i + 1) % 10 == 0:
                print(f"[fetch] {i+1}/{len(to_fetch)}", file=sys.stderr)
            time.sleep(0.3)

    # merge posts we didn't fetch but have in archive (metadata only)
    for ln, meta in by_log.items():
        if ln not in done:
            done[ln] = meta

    records = sorted(done.values(), key=lambda r: r.get("log_no", ""), reverse=True)
    idx_path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(f"[done] {len(records)} records, errors={errors}, index={idx_path}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
