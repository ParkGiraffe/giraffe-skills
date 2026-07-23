#!/usr/bin/env python3
"""1단계: 가입/탈퇴 카페 전수 목록을 확보해 cafes.json 으로 저장.

각 카페 레코드:
  {cafeId, cafeName, cafeUrl, status: joined|secede,
   memberKey(가입만), nickname(가입만), favorite, managing,
   cafeOpenType(탈퇴만), secedeDate(탈퇴만)}

닉네임이 카페마다 달라도 (cafeId, memberKey)가 권위 키.
"""
import json
import pathlib
import sys
import time

from chrome_bridge import ChromeBridge
import endpoints as EP


def paginate(cb, url_tmpl, extract, label="", max_pages=100):
    """page=1.. 돌며 누적. 빈 페이지 또는 '새 cafeId 없음'이면 종료.

    네이버 목록 API가 마지막 페이지 이후 같은 데이터를 반복해서 줄 수 있어,
    빈 리스트뿐 아니라 새 cafeId가 안 나오는 경우도 종료 조건으로 둔다.
    """
    out = []
    seen = set()
    for page in range(1, max_pages + 1):
        data = cb.api_get(url_tmpl.format(page=page))
        result = data.get("message", {}).get("result", {})
        items = extract(result)
        new = [c for c in items if c["cafeId"] not in seen]
        print(f"[{label}] page {page}: {len(items)} items, {len(new)} new "
              f"(total {len(out)+len(new)})", file=sys.stderr)
        if not new:
            break
        for c in new:
            seen.add(c["cafeId"])
        out.extend(new)
        time.sleep(0.2)
    return out


def get_join_cafes(cb):
    def extract(result):
        cafes = []
        for grp in result.get("groups", []):
            gname = (grp.get("group") or {}).get("groupName", "")
            for c in grp.get("cafes", []):
                cafes.append({
                    "cafeId": c.get("cafeId"),
                    "cafeName": c.get("cafeName", "").strip(),
                    "cafeUrl": c.get("cafeUrl", ""),
                    "status": "joined",
                    "memberKey": c.get("memberKey", ""),
                    "nickname": c.get("memberNickname", ""),
                    "favorite": bool(c.get("favoriteCafe")),
                    "managing": bool(c.get("managingCafe")),
                    "group": gname,
                })
        return cafes
    return paginate(cb, EP.JOIN_CAFES, extract, label="join")


def get_secede_cafes(cb):
    def extract(result):
        cafes = []
        for c in result.get("cafes", []):
            cafes.append({
                "cafeId": c.get("cafeId"),
                "cafeName": c.get("cafeName", "").strip(),
                "cafeUrl": c.get("cafeUrl", ""),
                "status": "secede",
                "cafeOpenType": c.get("cafeOpenType", ""),
                "secedeDate": c.get("secedeDate", ""),
            })
        return cafes
    return paginate(cb, EP.SECEDE_CAFES, extract, label="secede")


def main():
    corpus = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                          else "./.claude/cafe-corpus").resolve()
    corpus.mkdir(parents=True, exist_ok=True)

    cb = ChromeBridge()
    ident = cb.api_get(EP.MEMBER_IDENTIFIER)["message"]["result"]
    print(f"[me] userId={ident.get('userId')} memberKey={ident.get('memberKey')}",
          file=sys.stderr)

    joined = get_join_cafes(cb)
    secede = get_secede_cafes(cb)
    # 중복 cafeId 제거(같은 카페가 두 목록에 다 있으면 joined 우선)
    by_id = {}
    for c in secede:
        by_id[c["cafeId"]] = c
    for c in joined:
        by_id[c["cafeId"]] = c
    cafes = list(by_id.values())

    out = {
        "me": ident,
        "counts": {
            "joined": len(joined),
            "secede": len(secede),
            "unique": len(cafes),
        },
        "cafes": cafes,
    }
    dest = corpus / "cafes.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"[done] joined={len(joined)} secede={len(secede)} "
          f"unique={len(cafes)} -> {dest}", file=sys.stderr)
    for c in cafes:
        tag = c["status"][0].upper()
        nick = c.get("nickname", "")
        print(f"  [{tag}] {c['cafeId']:>10}  {c['cafeName'][:30]:30}  "
              f"{c.get('cafeUrl',''):20} {nick}", file=sys.stderr)


if __name__ == "__main__":
    main()
