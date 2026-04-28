#!/usr/bin/env python3
"""Extract `[]` tag patterns from a Naver blog corpus, optionally filtered by category.

Usage: extract_patterns.py <corpus_dir> [--category "팝업/굿즈/오프"] [--all-categories]

Reads <corpus_dir>/index.json (produced by blog-learn) and prints JSON describing:
  - tag_pattern: the convention observed (e.g., "[IP/브랜드 + 형태]" 2-word combo)
  - tags: list of {tag, count, kind, example_titles}
  - kind_words: trailing tokens used as "형태" (팝업, 굿즈, 박람회, 탐방 ...)
  - ip_words: leading tokens used as "IP/브랜드"
  - sample_titles: up to 30 raw titles for context
  - delimiters: subtitle delimiter usage (e.g., "/" frequency)

Stable JSON output so the calling skill can ground its candidate generation in
real data instead of guessing.
"""
import argparse
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict


TAG_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(.*)$")


def load_index(corpus: pathlib.Path) -> list[dict]:
    idx_path = corpus / "index.json"
    if not idx_path.exists():
        print(f"error: {idx_path} not found. Run /blog-learn first.", file=sys.stderr)
        sys.exit(2)
    with idx_path.open(encoding="utf-8") as f:
        return json.load(f)


def parse_tag(title: str) -> tuple[str | None, str]:
    m = TAG_RE.match(title)
    if not m:
        return None, title
    return m.group(1).strip(), m.group(2).strip()


def split_tag(tag: str) -> tuple[str, str | None]:
    """Split `[IP 형태]` into (ip, kind) heuristically.

    The user's observed convention is two-word: leading IP/brand + trailing kind.
    Some tags are single-word (e.g., `[굿즈탐방]`); return (tag, None) in that case.
    """
    parts = tag.split()
    if len(parts) == 1:
        return parts[0], None
    return " ".join(parts[:-1]), parts[-1]


def analyze(posts: list[dict], category: str | None) -> dict:
    if category:
        posts = [p for p in posts if p.get("category") == category]

    tag_counter: Counter = Counter()
    tag_examples: dict[str, list[str]] = defaultdict(list)
    kind_counter: Counter = Counter()
    ip_counter: Counter = Counter()
    delimiter_counter: Counter = Counter()
    sample_titles: list[str] = []
    body_after_tag: list[str] = []

    for p in posts:
        title = p.get("title", "")
        sample_titles.append(title)
        tag, rest = parse_tag(title)
        if tag is None:
            continue
        tag_counter[tag] += 1
        if len(tag_examples[tag]) < 3:
            tag_examples[tag].append(title)
        ip, kind = split_tag(tag)
        if kind is None:
            kind_counter[ip] += 1
        else:
            ip_counter[ip] += 1
            kind_counter[kind] += 1
        body_after_tag.append(rest)
        for ch in "/":
            delimiter_counter[ch] += rest.count(ch)

    tags_sorted = [
        {
            "tag": tag,
            "count": cnt,
            "examples": tag_examples[tag],
        }
        for tag, cnt in tag_counter.most_common()
    ]

    return {
        "category": category or "(all)",
        "post_count": len(posts),
        "tagged_count": sum(tag_counter.values()),
        "tag_pattern": "[IP/브랜드 + 형태] (관측: 2단어 조합 우세, 단일어도 일부)",
        "tags": tags_sorted,
        "kind_words": kind_counter.most_common(),
        "ip_words": ip_counter.most_common(),
        "subtitle_delimiters": dict(delimiter_counter),
        "subtitle_samples": body_after_tag[:20],
        "sample_titles": sample_titles[:30],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--category", default=None,
                    help='Restrict analysis to this category, e.g. "팝업/굿즈/오프"')
    ap.add_argument("--all-categories", action="store_true",
                    help="Also include cross-category breakdown")
    args = ap.parse_args()

    corpus = pathlib.Path(args.corpus)
    posts = load_index(corpus)

    out = analyze(posts, args.category)

    if args.all_categories and args.category:
        out["all_categories"] = analyze(posts, None)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
