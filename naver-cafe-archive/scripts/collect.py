#!/usr/bin/env python3
"""2단계: 카페별 내가 쓴 글 목록을 다중 소스로 수집해 articles.json 으로.

소스:
  S1 (가입 카페): CafeMemberNetworkArticleListV3 — articleid + menuid + nickname
  S3 (탈퇴 카페): secede-cafes/{id}/articles — articleId (menuid 없음)

글 레코드(articleId 기준 union, cafe 단위):
  {cafeId, cafeUrl, cafeName, status, articleId, menuId, subject, writeDate,
   nickname, commentCount, sources:[s1|s3]}

부산물: nicknames.json — 카페목록 + 글 writernickname + 시드(갠스/제밀 등) 합집합.
        2차 검색 스윕(search_sweep.py)이 이걸 입력으로 쓴다.
"""
import json
import pathlib
import sys
import time

from chrome_bridge import ChromeBridge
import endpoints as EP

PER_PAGE = 50


def collect_s1(cb, cafe):
    """가입 카페: 멤버 네트워크 글 목록을 totalCount까지 페이지네이션."""
    cid, mkey = cafe["cafeId"], cafe["memberKey"]
    arts, nicks = {}, set()
    page, total = 1, None
    while True:
        url = EP.S1_MEMBER_ARTICLES.format(
            cafe_id=cid, member_key=mkey, per_page=PER_PAGE, page=page)
        result = cb.api_get(url)["message"]["result"]
        total = result.get("totalCount", 0) if total is None else total
        lst = result.get("articleList", [])
        if not lst:
            break
        for a in lst:
            aid = a.get("articleid")
            if aid is None:
                continue
            nick = a.get("writernickname", "")
            if nick:
                nicks.add(nick)
            arts[aid] = {
                "articleId": aid,
                "menuId": a.get("menuid"),
                "subject": a.get("subject", ""),
                "writeDate": a.get("writedt", ""),
                "writeTs": a.get("writeDateTimestamp"),
                "nickname": nick,
                "commentCount": a.get("commentcount", 0),
                "openyn": a.get("openyn", ""),
                "sources": ["s1"],
            }
        if len(arts) >= total or page * PER_PAGE >= total:
            break
        page += 1
        time.sleep(0.2)
    return arts, nicks


def collect_s3(cb, cafe):
    """탈퇴 카페: 작성글 관리 목록을 lastPage까지."""
    cid = cafe["cafeId"]
    arts, nicks = {}, set()
    page = 1
    while page <= 200:
        url = EP.S3_SECEDE_ARTICLES.format(cafe_id=cid, page=page)
        result = cb.api_get(url)["message"]["result"]
        lst = result.get("articles", [])
        if not lst:
            break
        for a in lst:
            aid = a.get("articleId")
            if aid is None:
                continue
            arts[aid] = {
                "articleId": aid,
                "menuId": None,
                "subject": a.get("subject", ""),
                "writeDate": a.get("writeDate", ""),
                "writeTs": None,
                "nickname": "",
                "commentCount": 0,
                "openyn": "",
                "sources": ["s3"],
            }
        pi = result.get("pageInfo", {})
        if pi.get("lastPage") or page * pi.get("perPage", 15) >= pi.get("totalCount", 0):
            break
        page += 1
        time.sleep(0.2)
    return arts, nicks


def main():
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    # --cafe <id> 의 값은 위 pos에 섞이므로 제거
    if "--cafe" in sys.argv:
        cafe_val = sys.argv[sys.argv.index("--cafe") + 1]
        pos = [a for a in pos if a != cafe_val]
    corpus = pathlib.Path(pos[0] if pos else "./.claude/cafe-corpus").resolve()
    cafes_data = json.loads((corpus / "cafes.json").read_text())
    cafes = cafes_data["cafes"]

    only = None
    if "--cafe" in sys.argv:
        only = int(sys.argv[sys.argv.index("--cafe") + 1])
        cafes = [c for c in cafes if c["cafeId"] == only]

    cb = ChromeBridge()
    all_nicks = set()
    out_cafes = []
    grand = 0
    for i, cafe in enumerate(cafes, 1):
        try:
            if cafe["status"] == "joined":
                arts, nicks = collect_s1(cb, cafe)
            else:
                arts, nicks = collect_s3(cb, cafe)
        except Exception as e:
            print(f"[{i}/{len(cafes)}] ERR {cafe['cafeName'][:24]}: {e}",
                  file=sys.stderr)
            out_cafes.append({**cafe, "articles": [], "error": str(e)})
            continue
        all_nicks |= nicks
        if cafe.get("nickname"):
            all_nicks.add(cafe["nickname"])
        grand += len(arts)
        out_cafes.append({
            "cafeId": cafe["cafeId"], "cafeUrl": cafe["cafeUrl"],
            "cafeName": cafe["cafeName"], "status": cafe["status"],
            "cafeOpenType": cafe.get("cafeOpenType", ""),
            "articles": list(arts.values()),
        })
        tag = cafe["status"][0].upper()
        print(f"[{i}/{len(cafes)}] [{tag}] {cafe['cafeName'][:26]:26} "
              f"{len(arts):4d} articles", file=sys.stderr)
        time.sleep(0.2)

    (corpus / "articles.json").write_text(
        json.dumps({"cafes": out_cafes, "total": grand},
                   ensure_ascii=False, indent=2))

    # nickname 사전: 관측 + 시드 합집합
    seed_path = pathlib.Path(__file__).parent / "nickname_seeds.json"
    seeds = json.loads(seed_path.read_text()) if seed_path.exists() else {}
    seed_nicks = set(seeds.get("user_provided", [])) | set(seeds.get("observed", []))
    merged = sorted(all_nicks | seed_nicks)
    (corpus / "nicknames.json").write_text(json.dumps({
        "userId": "op5321",
        "nicknames": merged,
        "from_articles": sorted(all_nicks),
        "from_seed": sorted(seed_nicks),
    }, ensure_ascii=False, indent=2))

    print(f"\n[done] {grand} articles across {len(out_cafes)} cafes", file=sys.stderr)
    print(f"[nicknames] {len(merged)}: {', '.join(merged)}", file=sys.stderr)


if __name__ == "__main__":
    main()
