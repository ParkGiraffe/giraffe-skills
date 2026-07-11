#!/usr/bin/env python3
"""naver-to-naver: 네이버 블로그 글을 파싱해 재발행/이전용 draft를 만든다.

네이버 글 하나(URL 또는 logNo)를 받아, paste_to_naver.py가 바로 먹을 수 있는
draft 디렉토리(script.md + meta.json + images/)를 생성한다.

핵심은 이미지다. 네이버 본문의 인라인 이미지는 966px로 다운스케일된 '프리뷰'라,
그대로 재업로드하면 화질이 죽는다. 진짜 원본은 postfiles.pstatic.net/<경로>?type=w3840
으로 받아야 한다(원본 폭이 3840 미만이면 그 폭 그대로 = 원본). 이 스크립트는
프리뷰가 아닌 원본을 받아서 draft에 넣는다.

사용법:
  build_draft.py <네이버_글_URL_또는_logNo> [--blog-id op5321] [--out <draft_dir>]

예:
  build_draft.py https://blog.naver.com/op5321/224342012894
  build_draft.py 224342012894 --out /tmp/draft_mongil9

출력 후:
  python3 <repo>/blog/scripts/paste_to_naver.py <draft_dir>   # 네이버 새 글에 붙임
"""
import re, sys, json, argparse, subprocess, pathlib

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
REFERER = "https://blog.naver.com/"
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PARSER = REPO_ROOT / "_lib" / "parse_smarteditor.py"


def curl(url, out=None, head=False):
    cmd = ["curl", "-sSL", "-A", UA, "-e", REFERER]
    if head:
        cmd = ["curl", "-sI", "-A", UA, "-e", REFERER]
    if out:
        cmd += ["-o", str(out)]
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True, text=(out is None))


def head_info(url):
    """(http_code, content_length) — 이미지 변형 후보 크기 비교용."""
    r = curl(url, head=True)
    code, length = None, 0
    for ln in r.stdout.splitlines():
        if ln.upper().startswith("HTTP"):
            parts = ln.split()
            if len(parts) > 1:
                code = parts[1]
        if ln.lower().startswith("content-length"):
            try:
                length = int(ln.split(":", 1)[1].strip())
            except ValueError:
                pass
    return code, length


def img_path(url):
    """pstatic URL에서 도메인·쿼리를 뗀 경로(<enc>/<enc>.../<name>.<ext>)."""
    m = re.search(r"pstatic\.net/(.+?)(?:\?|$)", url)
    return m.group(1) if m else None


def download_original(url, dest):
    """열화 프리뷰가 아닌 '원본'을 받는다.

    검증된 우선순위(2026-07-12 실측):
      1. postfiles.pstatic.net/<경로>?type=w3840   (원본, 정본)
      2. blogfiles.pstatic.net/<경로>              (쿼리 없이도 원본 = w3840과 동일 바이트)
      3. mblogthumb-phinf.pstatic.net/<경로>?type=w966  (최후: 966px 프리뷰)
    w1000+·w0·쿼리없는 mblogthumb는 404. postfiles 쿼리없음은 14KB짜리 기본 썸네일이라 금지.
    파일명이 _s.jpg(모바일 썸네일)면 _s를 뗀 것도 후보에 추가.
    가장 큰 200 응답을 받는다.
    """
    path = img_path(url)
    if not path:
        return None
    cands = [
        f"https://postfiles.pstatic.net/{path}?type=w3840",
        f"https://blogfiles.pstatic.net/{path}",
        f"https://mblogthumb-phinf.pstatic.net/{path}?type=w966",
    ]
    nos = re.sub(r"_s(\.[a-zA-Z]+)$", r"\1", path)
    if nos != path:
        cands += [f"https://postfiles.pstatic.net/{nos}?type=w3840",
                  f"https://blogfiles.pstatic.net/{nos}"]
    best, best_len = None, 0
    for v in cands:
        code, length = head_info(v)
        if code == "200" and length > best_len:
            best, best_len = v, length
    if not best:
        return None
    curl(best, out=dest)
    if dest.exists() and dest.stat().st_size > 1000:
        return best_len
    return None


# 네이버 SmartEditor 임베드 잔해(파서가 본문 텍스트로 잘못 뽑는 것들)
def is_artifact(s):
    if "unhandled unknown" in s:            # 링크 카드 임베드(다른 글 미리보기)
        return True
    if s in ("이 블로그의 체크인", "이 장소의 다른 글"):   # 지도 위젯 UI
        return True
    if re.match(r"^[\w.-]+\.(com|net|kr|io)$", s):         # 링크 카드의 bare 도메인
        return True
    if s.startswith("방문일 :"):            # 링크 카드 설명 줄
        return True
    return False


def clean_line(s):
    return re.sub(r"<!--\s*unhandled\s+\w+\s*-->\s*", "", s).strip()   # placesMap/table 코멘트 제거


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="네이버 글 URL 또는 logNo")
    ap.add_argument("--blog-id", default=None, help="blogId (URL로 안 주면 필요). 기본 op5321")
    ap.add_argument("--out", default=None, help="draft 디렉토리 (기본 ./draft_<logNo>)")
    args = ap.parse_args()

    m = re.search(r"/(\d{8,})", args.target) or re.search(r"logNo=(\d{8,})", args.target)
    log = m.group(1) if m else (args.target if args.target.isdigit() else None)
    if not log:
        sys.exit("logNo를 못 찾음. URL이나 숫자 logNo를 주세요.")
    bm = re.search(r"blog\.naver\.com/([A-Za-z0-9_-]+)/", args.target)
    blog_id = args.blog_id or (bm.group(1) if bm else "op5321")

    draft = pathlib.Path(args.out) if args.out else pathlib.Path(f"./draft_{log}").resolve()
    imgdir = draft / "images"
    imgdir.mkdir(parents=True, exist_ok=True)

    # 1. 본문 fetch + 파싱
    in_html = draft / "in.html"
    out_md = draft / "raw.md"
    curl(f"https://m.blog.naver.com/{blog_id}/{log}", out=in_html)
    if not in_html.exists() or in_html.stat().st_size < 2000:
        sys.exit(f"본문 fetch 실패(빈 페이지). blogId/logNo 확인: {blog_id}/{log}")
    r = subprocess.run(["python3", str(PARSER), str(in_html), log, str(out_md)],
                       capture_output=True, text=True)
    if not out_md.exists():
        sys.exit(f"파싱 실패: {r.stderr[:300]}")

    raw = out_md.read_text(encoding="utf-8").splitlines()
    title = ""
    lines = raw
    if raw and raw[0].strip() == "---":
        e = raw.index("---", 1)
        for l in raw[1:e]:
            mt = re.match(r'title:\s*"(.*)"', l)
            if mt:
                title = mt.group(1)
        lines = raw[e + 1:]

    # 2. 이미지 원본 다운로드 + 잔해 정제
    IMGRE = re.compile(r"!\[[^\]]*\]\((.+)\)")
    out, idx, ok, fail = [], 0, [], []
    for ln in lines:
        s = ln.strip()
        mi = IMGRE.match(s)
        if mi:
            idx += 1
            ext = pathlib.Path((img_path(mi.group(1)) or ".jpg")).suffix or ".jpg"
            dest = imgdir / f"{idx:03d}{ext}"
            length = download_original(mi.group(1), dest)
            if length:
                out.append(f"![]({dest})")
                ok.append((dest.name, length))
            else:
                fail.append(mi.group(1)[:70])
                out.append("")
            continue
        if "unhandled unknown" in s:
            continue
        s2 = clean_line(s)
        if is_artifact(s2):
            continue
        out.append(s2)

    # 3. draft 기록
    (draft / "script.md").write_text("\n".join(out), encoding="utf-8")
    (draft / "meta.json").write_text(
        json.dumps({"title": title, "source": f"https://blog.naver.com/{blog_id}/{log}",
                    "images": {"source_folder": str(imgdir)}},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    total = sum(l for _, l in ok) / 1024 / 1024
    print(f"TITLE: {title}")
    print(f"이미지: 성공 {len(ok)} / 실패 {len(fail)} / 총 {total:.1f} MB")
    if fail:
        print("실패 이미지:", fail)
    print(f"draft: {draft}")
    print(f"다음: python3 {REPO_ROOT}/blog/scripts/paste_to_naver.py {draft}")


if __name__ == "__main__":
    main()
