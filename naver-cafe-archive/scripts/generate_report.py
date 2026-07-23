#!/usr/bin/env python3
"""5단계: 수집 결과를 사람이 읽는 report.md 로 정리.

소스별 개수, 카페별 글 수, 본문 완전/부분(재가입 필요) 내역, 닉네임 사전,
검색 스윕 결과(있으면)를 한 파일에 모은다. 무음 누락 없이 못 받은 것도 명시.
"""
import json
import pathlib
import sys
from collections import Counter, defaultdict


def load(p, default):
    return json.loads(p.read_text()) if p.exists() else default


def main():
    corpus = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                          else "./.claude/cafe-corpus").resolve()
    cafes = load(corpus / "cafes.json", {})
    idx = load(corpus / "index.json", [])
    nicks = load(corpus / "nicknames.json", {})
    rejoin = load(corpus / "rejoin_candidates.json", [])
    found = load(corpus / "search_found.json", [])
    cand = load(corpus / "search_candidates.json", [])

    full = [r for r in idx if r.get("partial") is False]
    part = [r for r in idx if r.get("partial") is True]
    err = [r for r in idx if r.get("partial") is None]

    by_cafe = defaultdict(lambda: {"full": 0, "part": 0, "status": "", "url": ""})
    for r in idx:
        d = by_cafe[r["cafeName"]]
        d["status"] = r["status"]
        d["url"] = r["cafeUrl"]
        if r.get("partial"):
            d["part"] += 1
        elif r.get("partial") is False:
            d["full"] += 1

    L = []
    L.append("# 네이버 카페 옛 글 아카이브 리포트\n")
    me = cafes.get("me", {})
    L.append(f"- 계정: **{me.get('userId','?')}**  (memberKey `{me.get('memberKey','')}`)")
    cnt = cafes.get("counts", {})
    L.append(f"- 카페: 가입 {cnt.get('joined','?')} / 탈퇴 {cnt.get('secede','?')} "
             f"/ 고유 {cnt.get('unique','?')}")
    L.append(f"- 수집 글: **{len(idx)}개**  "
             f"(본문 완전 {len(full)} / 부분=재가입필요 {len(part)} / 오류 {len(err)})\n")

    L.append("## 글이 있는 카페 (글 수 순)\n")
    L.append("| 글수 | 완전 | 부분 | 상태 | 카페 |")
    L.append("|---:|---:|---:|:--|:--|")
    for name, d in sorted(by_cafe.items(), key=lambda x: -(x[1]["full"] + x[1]["part"])):
        tot = d["full"] + d["part"]
        L.append(f"| {tot} | {d['full']} | {d['part']} | {d['status']} | {name} |")

    L.append("\n## 본문 재가입 필요 (부분 수집 — 제목·날짜만 확보)\n")
    L.append("아래 카페는 **탈퇴한 비공개 카페**라 본문/사진이 멤버 권한 뒤에 잠겨 있습니다. "
             "각 카페를 **재가입**한 뒤 `content.py --refresh` 를 돌리면 본문과 이미지까지 "
             "전부 받아집니다(멤버 대상 파이프라인은 검증 완료).\n")
    rc = Counter((r["cafeName"], r["cafeUrl"]) for r in part)
    L.append("| 글수 | 카페 | 바로가기 |")
    L.append("|---:|:--|:--|")
    for (name, url), n in rc.most_common():
        L.append(f"| {n} | {name} | https://cafe.naver.com/{url} |")

    L.append("\n## 닉네임 사전 (작성자 단서)\n")
    nk = nicks.get("nicknames", [])
    L.append(f"수집/시드 합쳐 **{len(nk)}개**: {', '.join(nk)}\n")
    if nicks.get("from_seed"):
        L.append(f"- 사용자 제공 시드: {', '.join(nicks.get('from_seed', []))}")
    if nicks.get("from_articles"):
        L.append(f"- 글에서 관측: {', '.join(nicks.get('from_articles', []))}")

    L.append("\n## 닉네임 검색 스윕 (S2)\n")
    if found or cand:
        L.append(f"- 검색으로 추가 확인된 **내 글(작성자 op5321 검증)**: {len(found)}개")
        for r in found[:50]:
            L.append(f"  - [{r.get('cafeName','')}] {r.get('title','')} "
                     f"({r.get('writeDate','')}) {r.get('url','')}")
        L.append(f"- 검증 불가(권한없음)·중복 후보: {len(cand)}개 "
                 f"(search_candidates.json 참고)")
    else:
        L.append("- 아직 실행 안 함. `search_sweep.py` 로 닉네임별 통합검색 + "
                 "작성자 검증을 돌리면 내 카페 목록 밖의 공개글까지 추가 발굴합니다.")

    if err:
        L.append("\n## 수집 오류 (재시도 필요)\n")
        for r in err:
            L.append(f"- [{r.get('cafeName','')}] {r.get('articleId')} "
                     f"{r.get('error','')}")

    L.append("\n## 산출물\n")
    L.append("- `index.json` — 전체 글 메타 통합 인덱스")
    L.append("- `posts/{cafeId}/{articleId}.md` — 글별 본문(frontmatter 포함)")
    L.append("- `raw/{cafeId}/{articleId}.json` — 원본 API 응답")
    L.append("- `cafes.json` / `articles.json` / `nicknames.json` / "
             "`rejoin_candidates.json`")

    (corpus / "report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"[report] {corpus/'report.md'} ({len(L)} lines)")


if __name__ == "__main__":
    main()
