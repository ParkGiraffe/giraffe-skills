#!/usr/bin/env python3
"""네이버 블로그 글에 올라가지 않은 로컬 사진을 찾아 '미수록' 폴더로 분류.

핵심 트릭: 네이버 블로그 발행 이미지 URL 경로에는 업로드 당시의 **원본 파일명**이
그대로 보존된다 (se-image-resource img 태그의 src basename). 따라서 발행된
파일명 집합과 로컬 폴더의 파일명 집합을 비교(차집합)하면 미수록 사진이 나온다.

파일명이 전혀 겹치지 않으면(업로드 시 리네임된 경우) --hash 폴백으로 전환:
발행 이미지를 받아 dHash를 구하고 로컬 dHash와 해밍거리로 매칭한다.

기본 동작은 '이동'(move). 원본 보존이 필요하면 --copy.

사용법:
    classify.py <BLOG_URL> <LOCAL_DIR> [--dest 미수록] [--copy] [--hash] [--dry-run]

예시:
    classify.py "https://blog.naver.com/op5321/224295471965" "/path/output"
    classify.py "https://blog.naver.com/op5321/224295471965" "/path/output" --dry-run
    classify.py "<URL>" "/path/output" --copy --dest 미수록
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import ssl
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
IMG_EXTS = (".jpg", ".jpeg", ".png")

# python.org 빌드는 시스템 CA를 못 찾는 경우가 많음 → certifi 우선, 없으면 검증 우회
try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    SSL_CTX = ssl.create_default_context()
    SSL_CTX.check_hostname = False
    SSL_CTX.verify_mode = ssl.CERT_NONE


def urlopen(req_or_url, timeout=30):
    if isinstance(req_or_url, str):
        req_or_url = urllib.request.Request(req_or_url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req_or_url, timeout=timeout, context=SSL_CTX)


def parse_blog_url(url: str):
    """blog.naver.com/<id>/<logNo> 또는 PostView.naver?blogId=&logNo= 모두 처리."""
    q = urllib.parse.urlparse(url).query
    qs = urllib.parse.parse_qs(q)
    if "blogId" in qs and "logNo" in qs:
        return qs["blogId"][0], qs["logNo"][0]
    m = re.search(r"blog\.naver\.com/([^/?#]+)/(\d+)", url)
    if m:
        return m.group(1), m.group(2)
    sys.exit(f"URL에서 blogId/logNo를 추출할 수 없음: {url}")


def fetch_post_html(blog_id: str, log_no: str) -> str:
    api = f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
    with urlopen(api) as r:
        return r.read().decode("utf-8", errors="replace")


def published_names(html: str):
    """se-image-resource img 태그 src의 basename(파일명) 집합."""
    names = set()
    for tag in re.findall(r'<img[^>]*class="se-image-resource"[^>]*>', html):
        m = re.search(r'src="([^"]+)"', tag)
        if not m:
            continue
        path = m.group(1).split("?")[0]
        name = urllib.parse.unquote(os.path.basename(path))
        names.add(name)
    return names


def published_urls(html: str):
    """발행 이미지의 (파일명, 다운로드용 URL) 목록 — hash 폴백용. 원본 화질로."""
    out = []
    for tag in re.findall(r'<img[^>]*class="se-image-resource"[^>]*>', html):
        m = re.search(r'src="([^"]+)"', tag)
        if not m:
            continue
        raw = m.group(1)
        base = raw.split("?")[0]
        name = urllib.parse.unquote(os.path.basename(base))
        out.append((name, base + "?type=w773"))  # 적당한 중간 화질
    return out


def local_images(d: str):
    return [f for f in os.listdir(d)
            if f.lower().endswith(IMG_EXTS)
            and not f.startswith("._")
            and os.path.isfile(os.path.join(d, f))]


def dhash(path, Image):
    im = Image.open(path).convert("L").resize((9, 8), Image.LANCZOS)
    px = list(im.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            i = row * 9 + col
            bits = (bits << 1) | (1 if px[i] > px[i + 1] else 0)
    return bits


def hamming(a, b):
    return bin(a ^ b).count("1")


def main():
    ap = argparse.ArgumentParser(description="네이버 글 미수록 로컬 사진을 분류")
    ap.add_argument("url", help="네이버 블로그 글 URL")
    ap.add_argument("local_dir", help="대조할 로컬 사진 폴더")
    ap.add_argument("--dest", default="미수록", help="만들 하위 폴더명(기본 미수록)")
    ap.add_argument("--copy", action="store_true", help="이동 대신 복사(원본 보존)")
    ap.add_argument("--hash", action="store_true", help="파일명 대신 dHash로 매칭")
    ap.add_argument("--threshold", type=int, default=8, help="dHash 해밍거리 매칭 임계(기본 8)")
    ap.add_argument("--dry-run", action="store_true", help="실제 이동 없이 결과만 출력")
    args = ap.parse_args()

    local_dir = os.path.abspath(os.path.expanduser(args.local_dir))
    if not os.path.isdir(local_dir):
        sys.exit(f"로컬 폴더가 없음: {local_dir}")

    blog_id, log_no = parse_blog_url(args.url)
    print(f"블로그 {blog_id} / 글 {log_no} 조회 중...")
    html = fetch_post_html(blog_id, log_no)

    local = local_images(local_dir)
    print(f"로컬 사진 {len(local)}장 / ", end="")

    use_hash = args.hash
    if not use_hash:
        pub = published_names(html)
        overlap = pub & set(local)
        print(f"발행 파일명 {len(pub)}개 (로컬과 일치 {len(overlap)}개)")
        if pub and not overlap:
            print("경고: 파일명이 하나도 안 맞음 → 업로드 시 리네임 추정. --hash 모드로 자동 전환.")
            use_hash = True
        else:
            missing = sorted(set(local) - pub)

    if use_hash:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            sys.exit("--hash 모드는 pillow 필요: pip install --user pillow")
        purls = published_urls(html)
        print(f"발행 이미지 {len(purls)}개 dHash 계산(다운로드)...")
        pub_hashes = []
        for name, u in purls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": UA,
                                                          "Referer": "https://blog.naver.com/"})
                with urlopen(req) as r:
                    tmp = os.path.join("/tmp", "_pub_" + re.sub(r"\W", "_", name))
                    open(tmp, "wb").write(r.read())
                pub_hashes.append(dhash(tmp, Image))
                os.remove(tmp)
            except Exception as e:
                print(f"  발행 이미지 실패 {name}: {e}")
        missing = []
        for f in sorted(local):
            try:
                h = dhash(os.path.join(local_dir, f), Image)
            except Exception as e:
                print(f"  로컬 해시 실패 {f}: {e}")
                continue
            if all(hamming(h, ph) > args.threshold for ph in pub_hashes):
                missing.append(f)

    print(f"\n미수록(로컬에만 있음): {len(missing)}장")
    if args.dry_run:
        for n in missing[:60]:
            print("  ", n)
        if len(missing) > 60:
            print(f"  ... 외 {len(missing)-60}장")
        print("\n[dry-run] 실제 이동 안 함. 확정하려면 --dry-run 빼고 재실행.")
        return

    dst = os.path.join(local_dir, args.dest)
    os.makedirs(dst, exist_ok=True)
    op = shutil.copy2 if args.copy else shutil.move
    n = 0
    for name in missing:
        s = os.path.join(local_dir, name)
        if not os.path.isfile(s):
            continue
        op(s, os.path.join(dst, name))
        # macOS ._ 동반 파일도 함께
        cs = os.path.join(local_dir, "._" + name)
        if os.path.isfile(cs):
            op(cs, os.path.join(dst, "._" + name))
        n += 1
    verb = "복사" if args.copy else "이동"
    print(f"{verb} 완료: {n}장 → {dst}")


if __name__ == "__main__":
    main()
