---
name: naver-cafe-archive
description: op5321 계정으로 과거 네이버 카페에 쓴 글을 전수 발굴·보관한다. 가입/탈퇴 카페를 모두 훑어 글 목록을 다중 소스로 교차검증하고, 본문·이미지를 markdown으로 아카이브한다. 사용 시점 — 사용자가 "내가 옛날에 카페에 쓴 글 다 찾아줘", "네이버 카페 글 백업", "/naver-cafe-archive", 탈퇴한 카페 작성글 확인 등을 말할 때. 네이버는 외부 fetch를 막으므로 로그인된 Chrome에 osascript로 JS(fetch)를 주입해 내부 API를 호출한다. 이모지 금지.
---

# naver-cafe-archive

네이버 카페에 과거 작성한 글을 **전수 발굴·보관**하는 스킬. 닉네임이 카페마다
달라도(박기린/ArnoPark/PYSep/갠스/제밀…) memberKey 기반이라 누락 없이 모은다.

## 핵심 원리

네이버는 Claude의 직접 curl/fetch를 차단한다. 그래서 **로그인된 Chrome 탭의
페이지 컨텍스트에서 fetch를 실행**한다(세션 쿠키·올바른 origin 자동 첨부).
`scripts/chrome_bridge.py` 가 osascript로 JS를 주입하고, 비동기 fetch 결과를
window 변수 폴링으로 회수한다. **포커스를 뺏지 않으므로** 사용자가 다른 탭에서
작업 중에도 백그라운드로 돌아간다.

## 사전 조건 (한 번만)

1. Chrome 메뉴 > 보기 > 개발자용 > **"Apple 이벤트의 JavaScript 허용" ON**
2. 네이버 카페에 **로그인**된 상태
3. `cafe.naver.com` 또는 `section.cafe.naver.com` 탭을 **하나 이상** 열어둘 것
   (apis.naver.com 호출의 origin 제공용)

## 실행

```
bash scripts/archive.sh [corpus_dir] [--refresh]
# 기본 corpus_dir = ./.claude/cafe-corpus
```

단계별로 따로 돌릴 수도 있다(`scripts/` 안):
1. `discover.py`  — 가입+탈퇴+즐겨찾기 카페 전수 → `cafes.json`
2. `collect.py`   — 카페별 내 글 목록 다중소스 수집 → `articles.json`, `nicknames.json`
   - 가입 카페(S1): `CafeMemberNetworkArticleListV3` (memberKey 기반, 닉네임 변경 무관)
   - 탈퇴 카페(S3): `secede-cafes/{id}/articles` (= 공식 "작성글 관리"와 동일)
3. `content.py`   — 글 본문 → `posts/{cafeId}/{articleId}.md`, `raw/`, `index.json`
4. `generate_report.py` — `report.md`
5. `search_sweep.py` (선택) — 닉네임별 통합검색 + 작성자(op5321) 검증으로
   카페 목록 밖 공개글 추가 발굴 → `search_found.json`

엔드포인트 정의는 `scripts/endpoints.py`, 과거 닉네임 시드는
`scripts/nickname_seeds.json` 에 있다.

## 탈퇴 비공개 카페 본문 (중요)

탈퇴한 **비공개** 카페의 글은 제목·날짜는 들어오지만 **본문/이미지는 멤버 권한
뒤에 잠겨** 있어 403이 난다(`partial: true, needsRejoin: true` 로 표시). 이때는:

1. `report.md` 의 "본문 재가입 필요" 목록 확인
2. 해당 카페를 **재가입** (자동으로 하지 않음 — 바깥 행위)
3. `content.py --refresh` 재실행 → 본문·이미지까지 전부 수집

(가입 카페의 멤버 전용 글은 이미 본문까지 수집된다. 재가입하면 동일하게 열림.)

## 산출물 (`corpus_dir/`)

- `index.json` — 전체 글 메타 통합 인덱스
- `posts/{cafeId}/{articleId}.md` — 글별 본문(frontmatter)
- `raw/{cafeId}/{articleId}.json` — 원본 API 응답
- `cafes.json` / `articles.json` / `nicknames.json` / `rejoin_candidates.json`
- `report.md` — 소스별/카페별 개수, 재가입 필요 목록, 닉네임 사전

## 주의

- 네이버 약관·레이트리밋 존중. 스크립트는 0.2~0.3s 슬립으로 폴라이트하게 동작.
- 재가입·탈퇴·삭제 같은 바깥 행위는 자동으로 하지 않는다.
- 이모지 금지(사용자 규칙). 고유명사 왜곡 금지.
