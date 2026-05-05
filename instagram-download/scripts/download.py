#!/usr/bin/env python3
"""공개 인스타그램 게시물의 사진을 로그인 없이 다운로드.

핵심 트릭: 인스타그램은 일반 UA에는 로그인 페이지로 리다이렉트하지만
Googlebot UA에는 캐러셀 JSON이 박힌 풀 페이지를 그대로 서빙한다.
그 페이지에서 대상 shortcode의 carousel_media 배열만 잘라내 각 항목의
image_versions2.candidates[0].url 을 다운로드한다.

사용법:
    download.py <url> [--index N] [--out DIR]

예시:
    download.py 'https://www.instagram.com/p/DX6ePKqj7Ny/'
    download.py 'https://www.instagram.com/p/DX6ePKqj7Ny/?img_index=2' --index 2
    download.py 'https://www.instagram.com/p/DX6ePKqj7Ny/' --out ~/Pictures
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

GOOGLEBOT_UA = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def extract_shortcode(url: str) -> str:
    m = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    if not m:
        sys.exit(f"URL에서 shortcode를 추출할 수 없음: {url}")
    return m.group(1)


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": GOOGLEBOT_UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def find_carousel_array(page: str, shortcode: str) -> list[dict]:
    """대상 shortcode에 속한 carousel_media 배열을 찾아 반환.

    페이지에는 추천 게시물 캐러셀도 함께 들어있으므로, 대상
    "code":"<shortcode>" 직후에 처음으로 등장하는 carousel_media만 채택한다
    (그 사이에 다른 "code":"…"가 끼어있으면 다른 게시물 데이터로 간주).
    """
    target = f'"code":"{shortcode}"'
    target_pos = page.find(target)
    if target_pos == -1:
        return []

    arr_pos = page.find('"carousel_media":[', target_pos)
    if arr_pos == -1:
        return []

    between = page[target_pos + len(target) : arr_pos]
    if re.search(r'"code":"[A-Za-z0-9_-]+"', between):
        return []

    return _parse_balanced_array(page, arr_pos + len('"carousel_media":'))


def _parse_balanced_array(page: str, start: int) -> list[dict]:
    depth = 0
    i = start
    in_str = False
    escape = False
    while i < len(page):
        c = page[i]
        if escape:
            escape = False
        elif c == "\\":
            escape = True
        elif c == '"' and not escape:
            in_str = not in_str
        elif not in_str:
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return json.loads(page[start : i + 1])
        i += 1
    raise ValueError("carousel_media 배열의 괄호가 맞지 않음")


def fallback_single_image(page: str) -> list[dict]:
    """단일 이미지(비-캐러셀) 게시물용 og:image 폴백."""
    m = re.search(r'<meta property="og:image" content="([^"]+)"', page)
    if not m:
        return []
    url = m.group(1).replace("&amp;", "&")
    return [{"image_versions2": {"candidates": [{"url": url}]}}]


def download_image(url: str, out_path: Path) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": CHROME_UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    out_path.write_bytes(data)
    return len(data)


def main() -> None:
    ap = argparse.ArgumentParser(description="공개 인스타그램 게시물 사진 다운로더")
    ap.add_argument("url", help="인스타그램 게시물 URL (instagram.com/p/<code>/)")
    ap.add_argument(
        "--index",
        type=int,
        default=None,
        help="캐러셀에서 N번째 이미지(1-base)만 받기 (기본: 전체)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path.home() / "Downloads",
        help="저장 폴더 (기본: ~/Downloads)",
    )
    args = ap.parse_args()

    shortcode = extract_shortcode(args.url)
    print(f"게시물 {shortcode} 페이지 가져오는 중…")
    page = fetch_html(args.url)

    items = find_carousel_array(page, shortcode)
    if not items:
        print("캐러셀을 찾지 못함, og:image 폴백…")
        items = fallback_single_image(page)
    if not items:
        sys.exit("이미지 URL을 추출할 수 없음. 비공개·삭제 게시물일 수 있음.")

    print(f"이미지 {len(items)}장 발견.")

    if args.index is not None:
        if not 1 <= args.index <= len(items):
            sys.exit(f"--index {args.index} 범위 초과 (1..{len(items)})")
        targets = [(args.index, items[args.index - 1])]
    else:
        targets = list(enumerate(items, 1))

    args.out = args.out.expanduser()
    args.out.mkdir(parents=True, exist_ok=True)
    for idx, item in targets:
        candidates = item.get("image_versions2", {}).get("candidates", [])
        if not candidates:
            print(f"[{idx}] 이미지 후보 없음 (동영상 항목으로 추정) — 건너뜀")
            continue
        url = candidates[0]["url"]
        out_path = args.out / f"instagram_{shortcode}_{idx}.jpg"
        size = download_image(url, out_path)
        print(f"[{idx}/{len(items)}] {size:,} bytes -> {out_path}")


if __name__ == "__main__":
    main()
