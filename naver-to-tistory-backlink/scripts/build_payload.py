#!/usr/bin/env python3
"""네이버 글 하나를 티스토리 '정리본' 발행 페이로드(JSON+base64)로 조립한다.

usage: build_payload.py <logNo> <out_dir>

산출: <out_dir>/<logNo>.json  {t: title_b64, b: body_b64, len, sum, sha}
스킬 정본(1002 형식)을 그대로 따른다. naver-to-tistory-backlink/SKILL.md 참조.
"""
import sys, os, re, json, base64, hashlib, subprocess, tempfile, html as ihtml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"

DROP_PREFIXES = (
    "안녕하세요",
    "해당 글은 티스토리 블로그",
    "원본 작성일",
)


def fetch(log):
    d = tempfile.mkdtemp()
    src = os.path.join(d, "in.html")
    subprocess.run(
        ["curl", "-sSL", "-A", UA, "-e", "https://blog.naver.com/", "-o", src,
         f"https://m.blog.naver.com/op5321/{log}"], check=True)
    out = os.path.join(d, "out.md")
    meta = subprocess.run(
        ["python3", os.path.join(REPO, "_lib", "parse_smarteditor.py"), src, log, out],
        capture_output=True, text=True, check=True)
    info = json.loads(meta.stdout.strip().splitlines()[-1])
    raw = open(src, encoding="utf-8", errors="replace").read()
    info["img_count"] = raw.count("se-image-resource")
    info["md"] = open(out, encoding="utf-8").read()
    return info


def paragraphs(md):
    """본문 텍스트 단락만 뽑는다(이미지·헤딩·구분선·지도블록·해시태그 제외)."""
    # frontmatter만 걷어내고 본문 전체를 대상으로 한다
    parts = md.split("---\n", 2)
    body = parts[2] if len(parts) > 2 else md
    body = re.sub(r"^#\s.*$", "", body, count=1, flags=re.M)  # 첫 h1(제목) 제거

    out, skip_map = [], False
    for block in body.split("\n\n"):
        s = block.strip()
        if not s:
            continue
        if s.startswith("<!-- unhandled placesMap"):
            skip_map = True
            continue
        if skip_map:
            # 지도 블록 잔여(주소·체크인 안내)는 짧은 줄로 이어진다. 긴 단락이
            # 나오면 지도 블록이 끝난 것이므로 그 단락부터 다시 채택한다.
            if len(s) > 60 or s.startswith(("!", "#", "---")):
                skip_map = False
            else:
                continue
        if s.startswith(("![", "#", "---", "<!--", "[")):
            continue
        s = re.sub(r"\s*\n\s*", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        if not s:
            continue
        if any(s.startswith(p) for p in DROP_PREFIXES):
            continue
        if re.fullmatch(r"(#\S+\s*)+", s):
            continue
        out.append(s)
    return out


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build(log):
    info = fetch(log)
    title = info["title"]
    paras = paragraphs(info["md"])
    if not paras:
        raise SystemExit(f"{log}: 본문 단락 0개")

    summary = " ".join(paras)
    if len(summary) > 800:
        summary = summary[:800]
    bullets = [p for p in paras if len(p) >= 10][:6]

    li = "\n".join(f"<li>{esc(b)}</li>" for b in bullets)
    body = f"""<blockquote data-ke-style="style1">이 글은 네이버 블로그 「<a href="https://m.blog.naver.com/op5321/{log}" target="_blank" rel="noopener">박기린의 기린파크</a>」 원문을 정리한 요약본입니다. 원문 전체와 이미지는 네이버에서 볼 수 있어요.</blockquote>
<h2 data-ke-size="size26">요약</h2>
<p data-ke-size="size16">{esc(summary)}</p>
<h2 data-ke-size="size26">핵심 포인트</h2>
<ul style="list-style-type: disc;" data-ke-list-type="disc">
{li}
</ul>
<h2 data-ke-size="size26">원문 보기 (네이버 블로그)</h2>
<ul style="list-style-type: disc;" data-ke-list-type="disc">
<li>📎 원문 링크: <a href="https://m.blog.naver.com/op5321/{log}" target="_blank" rel="noopener">{esc(title)}</a></li>
<li>🌐 PC 링크: <a href="https://blog.naver.com/op5321/{log}" target="_blank" rel="noopener">https://blog.naver.com/op5321/{log}</a></li>
<li>📱 모바일 raw URL(구글 크롤러 친화): <code>https://blog.naver.com/PostView.naver?blogId=op5321&amp;logNo={log}</code></li>
<li>🖼️ 이미지 {info['img_count']}장</li>
</ul>"""

    full_title = f"{title} | 정리본"
    tb = base64.b64encode(full_title.encode()).decode()
    bb = base64.b64encode(body.encode()).decode()
    return {
        "log": log,
        "title": full_title,
        "category": info.get("category", ""),
        "img_count": info["img_count"],
        "t": tb,
        "b": bb,
        "len": len(bb),
        "sum": sum(bb.encode()),
        "sha": hashlib.sha256(bb.encode()).hexdigest(),
        "bullets": len(bullets),
        "summary_len": len(summary),
    }


if __name__ == "__main__":
    log, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    p = build(log)
    path = os.path.join(outdir, f"{log}.json")
    json.dump(p, open(path, "w"), ensure_ascii=False)
    print(json.dumps({k: v for k, v in p.items() if k not in ("t", "b")}, ensure_ascii=False))
