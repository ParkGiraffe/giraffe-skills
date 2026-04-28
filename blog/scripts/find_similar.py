#!/usr/bin/env python3
"""Find top-N similar posts from a corpus based on topic keywords.

Usage: find_similar.py <corpus_dir> "<topic>" [--category X] [--n 3]

Prints JSON: [{"log_no":..., "title":..., "category":..., "score":..., "path":...}, ...]
"""
import sys, json, re, pathlib, argparse, math
from collections import Counter


def tokenize(s: str) -> list[str]:
    # Korean + alphanumerics; split on whitespace/punct, keep 2+ char tokens
    s = s.lower()
    toks = re.findall(r"[a-z0-9가-힣]+", s)
    return [t for t in toks if len(t) >= 2]


def load_posts(corpus: pathlib.Path) -> list[dict]:
    posts_dir = corpus / "posts"
    out = []
    for p in posts_dir.glob("*.md"):
        src = p.read_text(encoding="utf-8", errors="replace")
        # parse simple frontmatter
        fm = {}
        body = src
        if src.startswith("---\n"):
            end = src.find("\n---\n", 4)
            if end > 0:
                for line in src[4:end].splitlines():
                    m = re.match(r"^(\w+):\s*(.*)$", line)
                    if m:
                        k, v = m.group(1), m.group(2).strip().strip('"')
                        fm[k] = v
                body = src[end + 5:]
        out.append({
            "log_no": fm.get("log_no", p.stem),
            "title": fm.get("title", ""),
            "category": fm.get("category", ""),
            "path": str(p),
            "body": body,
        })
    return out


def score(post: dict, query_toks: list[str], category: str | None) -> float:
    title_toks = tokenize(post["title"])
    body_toks = tokenize(post["body"])[:2000]  # cap for speed
    q_set = set(query_toks)
    s = 0.0
    # title hits weigh 5x
    for t in title_toks:
        if t in q_set:
            s += 5.0
    # body hits weigh by inverse log length
    body_counts = Counter(body_toks)
    for t in q_set:
        if t in body_counts:
            s += 1.0 + math.log1p(body_counts[t])
    if category and post["category"] == category:
        s *= 2.0
    elif category and category in post["title"]:
        s *= 1.5
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("topic")
    ap.add_argument("--category", default=None)
    ap.add_argument("--n", type=int, default=3)
    args = ap.parse_args()

    corpus = pathlib.Path(args.corpus)
    posts = load_posts(corpus)
    query_toks = tokenize(args.topic)
    scored = []
    for p in posts:
        s = score(p, query_toks, args.category)
        if s > 0:
            scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    top = scored[: args.n]
    result = [
        {
            "log_no": p["log_no"],
            "title": p["title"],
            "category": p["category"],
            "score": round(s, 2),
            "path": p["path"],
        }
        for s, p in top
    ]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
