#!/usr/bin/env python3
"""3단계: articles.json의 각 글 본문을 받아 markdown + raw json + index.json 으로.

본문 API(article.cafe.naver.com/gw/v4)는 두 가지 응답을 준다:
  - 멤버이고 읽기권한 있음 → result.article.contentHtml (full)
  - 탈퇴/비공개/권한없음   → result.{subject,summary,...} (contentHtml 없음, 요약만)
                            → partial=True, needsRejoin=True 로 표시하고 카페를 재가입 후보에 올림.

출력:
  posts/{cafeId}/{articleId}.md   (frontmatter + 본문 또는 요약)
  raw/{cafeId}/{articleId}.json   (원본 응답)
  index.json                      (전 글 메타 통합)

증분: raw json이 이미 있고 --refresh 아니면 재요청 skip.
"""
import html as html_lib
import json
import pathlib
import re
import sys
import time

from chrome_bridge import ChromeBridge
import endpoints as EP


def fmt_date(v):
    """epoch ms(int/숫자문자열) → 'YYYY.MM.DD. HH:MM' (KST). 그 외는 그대로."""
    import datetime
    s = str(v)
    if re.fullmatch(r"\d{12,13}", s):
        dt = datetime.datetime.utcfromtimestamp(int(s) / 1000) + datetime.timedelta(hours=9)
        return dt.strftime("%Y.%m.%d. %H:%M")
    return v


def html_to_text(h: str) -> str:
    if not h:
        return ""
    h = re.sub(r"<\s*br\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"</\s*(p|div|li|h[1-6]|tr)\s*>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", "", h)
    h = html_lib.unescape(h)
    h = re.sub(r"\n{3,}", "\n\n", h)
    return h.strip()


def parse_article(data: dict) -> dict:
    """v4 응답을 정규화. full이면 contentHtml, 아니면 summary."""
    result = data.get("result", {})
    art = result.get("article")
    if isinstance(art, dict) and art.get("contentHtml") is not None:
        writer = art.get("writer", {}) or {}
        return {
            "subject": art.get("subject", ""),
            "writeDate": fmt_date(art.get("writeDate", "")),
            "writerNick": writer.get("nick", "") or writer.get("id", ""),
            "menuName": (art.get("menu") or {}).get("name", ""),
            "readCount": art.get("readCount"),
            "commentCount": art.get("commentCount"),
            "contentHtml": art.get("contentHtml", ""),
            "partial": False,
            "needsRejoin": False,
        }
    # 제한 응답
    writer = result.get("writer", {}) or {}
    return {
        "subject": result.get("subject", ""),
        "writeDate": result.get("writeDate", ""),
        "writerNick": writer.get("nick", "") or writer.get("id", ""),
        "menuName": (result.get("menuViewModel") or {}).get("name", ""),
        "readCount": result.get("readCount"),
        "commentCount": result.get("commentCount"),
        "contentHtml": "",
        "summary": result.get("summary", ""),
        "partial": True,
        "needsRejoin": not result.get("open", True),
    }


def write_md(dest: pathlib.Path, cafe: dict, a: dict, parsed: dict, url: str):
    fm = {
        "title": parsed["subject"] or a.get("subject", ""),
        "cafeName": cafe["cafeName"],
        "cafeId": cafe["cafeId"],
        "cafeUrl": cafe["cafeUrl"],
        "articleId": a["articleId"],
        "writeDate": parsed["writeDate"] or a.get("writeDate", ""),
        "nickname": parsed["writerNick"] or a.get("nickname", ""),
        "menu": parsed.get("menuName", ""),
        "status": cafe["status"],
        "sources": a.get("sources", []),
        "partial": parsed["partial"],
        "needsRejoin": parsed["needsRejoin"],
        "url": url,
    }
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, str):
            lines.append(f'{k}: "{v}"')
        else:
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---\n")
    lines.append(f"# {fm['title']}\n")
    if parsed["partial"]:
        lines.append("> [부분 수집] 본문 전체는 멤버/공개 권한이 없어 요약만 확보. "
                     "재가입하면 전체 본문을 받을 수 있습니다.\n")
        if parsed.get("summary"):
            lines.append(parsed["summary"])
    else:
        lines.append(html_to_text(parsed["contentHtml"]))
    dest.write_text("\n".join(lines), encoding="utf-8")


def main():
    args = sys.argv[1:]
    refresh = "--refresh" in args
    pos = [a for a in args if not a.startswith("--")]
    corpus = pathlib.Path(pos[0] if pos else "./.claude/cafe-corpus").resolve()

    data = json.loads((corpus / "articles.json").read_text())
    posts_dir = corpus / "posts"
    raw_dir = corpus / "raw"

    cb = ChromeBridge()
    index = []
    rejoin = {}
    fetched = errs = partials = skipped = 0

    jobs = []
    for cafe in data["cafes"]:
        for a in cafe.get("articles", []):
            jobs.append((cafe, a))
    print(f"[content] {len(jobs)} articles to process", file=sys.stderr)

    for n, (cafe, a) in enumerate(jobs, 1):
        cid, aid = cafe["cafeId"], a["articleId"]
        rj = raw_dir / str(cid) / f"{aid}.json"
        md = posts_dir / str(cid) / f"{aid}.md"
        rj.parent.mkdir(parents=True, exist_ok=True)
        md.parent.mkdir(parents=True, exist_ok=True)
        url = EP.article_web_url(cafe["cafeUrl"], aid)

        if rj.exists() and not refresh:
            payload = json.loads(rj.read_text())
            skipped += 1
        else:
            menu = a.get("menuId") or ""
            try:
                payload = cb.api_get(EP.ARTICLE_CONTENT.format(
                    cafe_id=cid, article_id=aid, menu_id=menu))
                rj.write_text(json.dumps(payload, ensure_ascii=False))
                fetched += 1
                time.sleep(0.25)
            except Exception as e:
                msg = str(e)
                # 403/401 = 권한 없음(탈퇴/완전비공개). 실패가 아니라 재가입 필요 케이스로
                # 목록 메타만 가지고 부분 레코드를 남긴다.
                if "HTTP 403" in msg or "HTTP 401" in msg:
                    payload = {"result": {"subject": a.get("subject", ""),
                                          "writeDate": a.get("writeDate", ""),
                                          "open": False, "_permissionDenied": True}}
                    rj.write_text(json.dumps(payload, ensure_ascii=False))
                    time.sleep(0.15)
                else:
                    errs += 1
                    print(f"[{n}/{len(jobs)}] ERR {cid}/{aid}: {msg[:80]}",
                          file=sys.stderr)
                    index.append({**a, "cafeId": cid, "cafeName": cafe["cafeName"],
                                  "cafeUrl": cafe["cafeUrl"], "url": url,
                                  "error": msg[:120], "partial": None})
                    continue

        parsed = parse_article(payload)
        write_md(md, cafe, a, parsed, url)
        if parsed["partial"]:
            partials += 1
            rejoin.setdefault(cid, {"cafeName": cafe["cafeName"],
                                    "cafeUrl": cafe["cafeUrl"],
                                    "status": cafe["status"], "count": 0})
            rejoin[cid]["count"] += 1
        index.append({
            "cafeId": cid, "cafeName": cafe["cafeName"], "cafeUrl": cafe["cafeUrl"],
            "status": cafe["status"], "articleId": aid,
            "title": parsed["subject"] or a.get("subject", ""),
            "writeDate": parsed["writeDate"] or a.get("writeDate", ""),
            "nickname": parsed["writerNick"] or a.get("nickname", ""),
            "menu": parsed.get("menuName", ""),
            "commentCount": parsed.get("commentCount"),
            "sources": a.get("sources", []),
            "partial": parsed["partial"], "needsRejoin": parsed["needsRejoin"],
            "url": url, "md": str(md.relative_to(corpus)),
        })
        if n % 20 == 0:
            print(f"[{n}/{len(jobs)}] fetched={fetched} skip={skipped} "
                  f"partial={partials} err={errs}", file=sys.stderr)

    index.sort(key=lambda r: (r["cafeName"], str(r.get("writeDate", ""))))
    (corpus / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2))
    (corpus / "rejoin_candidates.json").write_text(
        json.dumps(list(rejoin.values()), ensure_ascii=False, indent=2))
    print(f"\n[done] total={len(index)} fetched={fetched} skipped={skipped} "
          f"partial={partials} err={errs}", file=sys.stderr)
    print(f"[rejoin] {len(rejoin)} cafes need rejoin for full body", file=sys.stderr)


if __name__ == "__main__":
    main()
