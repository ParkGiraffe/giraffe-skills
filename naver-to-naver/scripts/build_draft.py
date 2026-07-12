#!/usr/bin/env python3
"""naver-to-naver: 네이버 블로그 글을 파싱해 재발행/이전용 draft를 만든다.

네이버 글 하나(URL 또는 logNo)를 받아, paste_to_naver.py가 바로 먹을 수 있는
draft 디렉토리(script.md + meta.json + images/)를 생성한다.

핵심 두 가지:
1) 이미지 원본. 인라인 이미지는 966px 다운스케일 '프리뷰'라 그대로 재업로드하면 화질이 죽는다.
   진짜 원본은 postfiles.pstatic.net/<경로>?type=w3840 (원본 폭이 3840 미만이면 그 폭 = 원본).
2) GIF·스티커. 네이버 GIF는 '동영상형' 컴포넌트라 SmartEditor 파서가 이미지로 분류하지 못하고,
   스티커(OGQ)도 별도 컴포넌트다. 그래서 이 스크립트는 parse_smarteditor의 미디어 분류에 기대지 않고
   se-component를 DOM 순서로 직접 순회해 이미지/GIF/스티커/strip을 전부 잡는다. GIF는 w3840로도
   애니메이션(다프레임)이 보존된다(실측: 73프레임 그대로).

사용법:
  build_draft.py <네이버_글_URL_또는_logNo> [--blog-id op5321] [--out <draft_dir>]

출력 후:
  python3 <repo>/blog/scripts/paste_to_naver.py <draft_dir>   # 네이버 새 글에 붙임
  python3 <this-skill>/scripts/style_pass.py                  # 사진 가운데정렬 + 구분선 line3
"""
import re, sys, json, argparse, subprocess, pathlib, html as H

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
REFERER = "https://blog.naver.com/"
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

MEDIA_RE = re.compile(r'https?://([a-z0-9-]+\.pstatic\.net)/([^"?\s\\]+\.(?:jpe?g|png|gif))', re.I)


def curl(url, out=None, head=False):
    cmd = (["curl", "-sI"] if head else ["curl", "-sSL"]) + ["-A", UA, "-e", REFERER]
    if out:
        cmd += ["-o", str(out)]
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True, text=(out is None))


def head_len(url):
    r = curl(url, head=True)
    code, length = None, 0
    for ln in r.stdout.splitlines():
        if ln.upper().startswith("HTTP"):
            p = ln.split()
            if len(p) > 1:
                code = p[1]
        if ln.lower().startswith("content-length"):
            try:
                length = int(ln.split(":", 1)[1].strip())
            except ValueError:
                pass
    return code, length


def download_original(dom, path, dest):
    """열화 프리뷰가 아닌 '원본'을 받는다. GIF도 w3840로 애니메이션 보존.

    - storep-phinf(OGQ 스티커): 그 도메인은 postfiles 변환이 안 되니 원본 URL 직접.
    - 그 외: postfiles ?type=w3840 → blogfiles → mblogthumb ?type=w966 순으로 가장 큰 200.
    """
    if "storep-phinf" in dom:                      # OGQ 스티커 — type 필수 + HEAD 미지원이라 GET으로 직접
        for q in ("?type=p100_100", "?type=f120_120"):
            curl(f"https://{dom}/{path}{q}", out=dest)
            if dest.exists() and dest.stat().st_size > 500:
                return dest.stat().st_size
        return 0
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
        c, l = head_len(v)
        if c == "200" and l > best_len:
            best, best_len = v, l
    if not best:
        return 0
    curl(best, out=dest)
    return dest.stat().st_size if dest.exists() and dest.stat().st_size > 500 else 0


def strip_tags(s):
    s = re.sub(r"<[^>]+>", "", s)
    return H.unescape(s).replace("\xa0", " ").strip()


def bold_md(p):
    """문단 HTML → 텍스트. 인라인 볼드(`<b>..</b>`)를 `**..**` 마크다운으로 보존.
    paste_to_naver가 `**..**`를 <b>로 렌더하므로 문장 중 일부 볼드까지 살아남는다."""
    def repl(m):
        inner = re.sub(r"<[^>]+>", "", m.group(1)).replace("​", "").strip()
        return f"**{inner}**" if inner else ""
    s = re.sub(r"<b>(.*?)</b>", repl, p, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    return H.unescape(s).replace("​", "").replace("\xa0", " ").strip()


def components(html):
    """se-component 블록을 DOM 순서로 산출: (kind, block)."""
    starts = [m.start() for m in re.finditer(r'<div class="se-component ', html)]
    starts.append(len(html))
    for i in range(len(starts) - 1):
        blk = html[starts[i]:starts[i + 1]]
        m = re.match(r'<div class="se-component (se-[A-Za-z]+)', blk)
        yield (m.group(1) if m else "unknown"), blk


def media_in(blk):
    """블록 안 pstatic 미디어를 enc-path 기준 중복 제거해 순서대로. (dom, path) 리스트.
    같은 이미지의 여러 크기(blur/w800/mp4)는 path가 같아 1개로 합쳐짐. GIF는 path가 .gif로 끝남."""
    seen, out = set(), []
    for m in MEDIA_RE.finditer(blk):
        dom, path = m.group(1), m.group(2)
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((dom, path))
    return out


def para_lines(blk):
    """se-text 블록의 문단들을 줄 리스트로. 헤딩(소제목)은 `## `로.

    네이버 소제목은 `se-fs-fs{N>=20}` 폰트클래스 스팬 + `<b>`로 마킹된다(노란배경 24px 볼드).
    parse_smarteditor.render_text와 동일 판정 — 안 하면 소제목이 전부 평문 본문으로 떨어진다."""
    ps = re.findall(r'<p[^>]*class="se-text-paragraph[^"]*"[^>]*>(.*?)</p>', blk, re.S)
    if not ps:
        ps = re.findall(r"<p[^>]*>(.*?)</p>", blk, re.S)
    out = []
    for p in ps:
        t = strip_tags(p).replace("​", "").strip()
        if not t:
            out.append("")
            continue
        m = re.search(r"se-fs-fs(\d+)", p)
        size = int(m.group(1)) if m else 0
        if size >= 20 and "background-color:#fff593" in p:
            out.append(f"## {t}")      # 노란배경 소제목(진짜 목차) → paste가 24px 노랑볼드
        elif size >= 20:
            out.append(f"### {t}")     # 배경없는 큰 볼드(감탄 강조) → 19px 볼드, 노랑 아님
        else:
            out.append(bold_md(p))     # 본문: 인라인 볼드(<b>) 를 **볼드**로 보존
    return out if out else [strip_tags(blk).replace("​", "").strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--blog-id", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    m = re.search(r"/(\d{8,})", args.target) or re.search(r"logNo=(\d{8,})", args.target)
    log = m.group(1) if m else (args.target if args.target.isdigit() else None)
    if not log:
        sys.exit("logNo를 못 찾음.")
    bm = re.search(r"blog\.naver\.com/([A-Za-z0-9_-]+)/", args.target)
    blog_id = args.blog_id or (bm.group(1) if bm else "op5321")

    draft = pathlib.Path(args.out).resolve() if args.out else pathlib.Path(f"./draft_{log}").resolve()
    imgdir = draft / "images"
    imgdir.mkdir(parents=True, exist_ok=True)

    in_html = draft / "in.html"
    curl(f"https://m.blog.naver.com/{blog_id}/{log}", out=in_html)
    if not in_html.exists() or in_html.stat().st_size < 2000:
        sys.exit("본문 fetch 실패.")
    html = in_html.read_text(encoding="utf-8", errors="replace")

    tm = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    title = H.unescape(tm.group(1)) if tm else ""

    out, idx, ok, fail, gifs, stickers = [], 0, [], [], 0, 0
    for kind, blk in components(html):
        if kind == "se-documentTitle":
            continue
        if kind == "se-text":
            out.extend(para_lines(blk))
            out.append("")
        elif kind == "se-horizontalLine":
            out.append("")
            out.append("---")
            out.append("")
        elif kind in ("se-image", "se-imageStrip", "se-sticker"):
            for dom, path in media_in(blk):
                idx += 1
                ext = pathlib.Path(path).suffix.lower() or ".jpg"
                dest = imgdir / f"{idx:03d}{ext}"
                if dest.exists() and dest.stat().st_size > 500:   # 재실행 시 기존 파일 재사용
                    size = dest.stat().st_size
                else:
                    size = download_original(dom, path, dest)
                if size:
                    out.append(f"![]({dest})")
                    ok.append((dest.name, size))
                    if ext == ".gif":
                        gifs += 1
                    if "storep-phinf" in dom:
                        stickers += 1
                else:
                    fail.append(f"{dom}/{path[:50]}")
        # se-placesMap / se-oglink / se-video 등은 건너뜀(본문 텍스트 오염 방지)

    (draft / "script.md").write_text("\n".join(out), encoding="utf-8")
    (draft / "meta.json").write_text(
        json.dumps({"title": title, "source": f"https://blog.naver.com/{blog_id}/{log}",
                    "images": {"source_folder": str(imgdir)}}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    total = sum(l for _, l in ok) / 1024 / 1024
    print(f"TITLE: {title}")
    print(f"미디어: 성공 {len(ok)} (그중 GIF {gifs}, 스티커 {stickers}) / 실패 {len(fail)} / 총 {total:.1f} MB")
    if fail:
        print("실패:", fail)
    print(f"draft: {draft}")
    print(f"다음: python3 {REPO_ROOT}/blog/scripts/paste_to_naver.py {draft}")


if __name__ == "__main__":
    main()
