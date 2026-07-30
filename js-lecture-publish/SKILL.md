---
name: js-lecture-publish
description: 박기린(op5321)의 티스토리 JS 강의(arnopark.tistory.com) 글을 노션 'JS 마이그레이션' 체크리스트 순서대로 한 번에 4개씩 네이버 블로그 'JavaScript 강의실' 카테고리에 발행한다. 제목을 "[JS 강의] N. ~"로 통일하고, 발행 완료된 글을 노션 체크리스트에서 체크 표시한다. 기존 tistory-to-naver(scripts/migrate.py)·_lib/publish_with_category.py를 재활용. 사용 시점: 사용자가 "JS 강의 4개 발행", "다음 4개 발행해", "/js-lecture-publish", "JS 마이그레이션 이어서" 등을 말할 때. 무인 네이버 업로드 금지·포커스 검증 필수(2026-06-16 사고 교훈), 이모지 금지.
---

# js-lecture-publish — JS 강의 티스토리→네이버 4개씩 발행

요청 1회당 노션 'JS 마이그레이션' 체크리스트의 **다음 미체크 4개**를 순서대로 네이버 'JavaScript 강의실' 카테고리에 발행하고, 제목을 통일한 뒤 노션에서 체크한다.

## 고정 대상
- 노션 체크리스트 페이지(순서·진행 소스 of truth): `3e3c6f40-e87e-822f-aa27-019ea9d79e22` ("JS 마이그레이션")
  - 본문에 `- [ ] [제목](https://arnopark.tistory.com/NNN)` 형태로 95개. 체크(`- [x]`)된 건 발행 완료.
- 매크로: 이 리포의 `tistory-to-naver/scripts/`(변환 엔진)와 `_lib/`(에디터 매크로).
  2026-07-30 외부 리포 `tistory-to-naver-blog`를 흡수해 경로가 바뀌었다.
- 네이버 블로그: `op5321`, 카테고리 **JavaScript 강의실 = testid `147`** (2026-06-25 `dump_categories.py`로 확정).

## 사전 조건 (tistory-to-naver와 동일, 1회)
손쉬운 사용에 터미널 체크 + Chrome "Apple Events의 자바스크립트 허용" 체크 + 네이버 로그인 + postwrite 탭. 자세한 건 `/tistory-to-naver` 참고.

## 절차 (요청 1회 = 4개)

### 1. 다음 4개 선정
`notion-fetch`로 위 페이지 본문을 읽어 **위에서부터 미체크(`- [ ]`) 4개**를 뽑는다. 각 항목에서 티스토리 URL과 강의 번호·제목을 파싱.
- 4개 미만 남았으면 남은 개수만. 0개면 "전부 발행 완료" 보고하고 종료.
- 현재 순서: JavaScript 강의(유데미 인트로 + 1~65) 먼저, 그다음 React 강의(1~28). React는 카테고리·프리픽스가 다를 수 있으니 React 구간 진입 전 사용자에게 확인.

### 2. 제목 통일 규칙 → "[JS 강의] N. ~"
원본 티스토리 제목에서 기존 `[JS]`/`(JS)` 프리픽스를 떼고 번호+본문만 남겨 앞에 `[JS 강의] `를 붙인다.
- "1. 자바스크립트에 대한 개요" → `[JS 강의] 1. 자바스크립트에 대한 개요`
- "(JS) 49. forEach Method" → `[JS 강의] 49. forEach Method`
- "42-2. String 내장 메소드…" → `[JS 강의] 42-2. String 내장 메소드…`
- 인트로 "유데미 자바스크립트 강의노트 시작"(번호 없음) → `[JS 강의] 0. 유데미 자바스크립트 강의노트 시작`

### 3. 4개 순차 발행 (한 건씩, 키보드 금지 고지)
"약 1~2분간 키보드·마우스를 건드리지 마세요" 고지 후, 각 글마다:
```bash
cd <giraffe-skills 리포 루트>
python3 tistory-to-naver/scripts/migrate.py '<티스토리 URL>' --clear --title '[JS 강의] N. ~'
python3 _lib/publish_with_category.py 147 "JavaScript 강의실"
```
첫 줄이 본문+코드블록을 붙이고 제목을 통일하고, 둘째 줄이 카테고리 지정 + 발행이다.
- **순차**(앞 글 발행 끝나고 다음). 발행 성공 신호 = postwrite 탭이 사라짐(리다이렉트). 실패면 거기서 멈추고 보고(이후 글 진행 금지).
- 코드블록 언어는 기본 javascript(JS 강의라 대체로 맞음). 검토 시 다른 언어면 수동.
- 진짜 사이드바 태그는 자동 안 됨. 필요하면 발행 후 사용자가 직접.

### 4. 노션 체크
4개(또는 발행 성공분만) 발행 후, `notion-update-page`의 `update_content`로 해당 줄 `- [ ]` → `- [x]`로 교체. 발행 성공한 것만 체크(부분 실패 시 성공분까지만).

### 5. 보고
발행한 제목 N개 + 다음에 나올 4개 + 남은 개수.

## 카테고리 testid (확정)
**JavaScript 강의실 = `147`** (2026-06-25 확정). 다른 글 카테고리 testid를 새로 확인해야 하면 `python3 tistory-to-naver/scripts/dump_categories.py` 실행. migrate.py 헬퍼를 재사용해 글쓰기 탭을 알아서 띄우고 카테고리 셀렉트박스를 덤프한다(발행 안 함). 관측값: 젤다 왕눈=132, GoodWishes=142, Marpia=143, Pokedex-ai=144, JavaScript 강의실=147.

**중요(2026-06-25 수정)**: `publish_with_category.py`는 원래 카테고리 검증을 "제작기" 문자열로 하드코딩해 비-제작기 카테고리에선 발행 직전 abort했다. 2번째 인자로 기대 카테고리명을 받게 일반화함 → 반드시 `_lib/publish_with_category.py 147 "JavaScript 강의실"`처럼 카테고리명을 같이 넘길 것.

## 안전 / 함정
- **무인 업로드 금지**: 발행은 사용자 opt-in(이 스킬 호출 자체가 opt-in). 각 발행 전 창 포커스 검증(migrate.py/publish 스크립트 내장)을 신뢰하되, 실패 시 즉시 중단.
- 발행은 공개 행위라 되돌리기 번거로우니 4개 초과를 한 번에 돌리지 말 것(사용자가 4개로 못박음).
- 노션 체크는 발행 **성공 확인 후**에만. 미발행을 체크하면 순서가 꼬임.
- 관련: `/tistory-to-naver`, 메모리 [[naver-upload-safety-and-spacing]], [[tistory-to-naver-use-migrate-py]], [[naver-publish-with-category-osascript]].
