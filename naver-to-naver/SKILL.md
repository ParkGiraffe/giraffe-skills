---
name: naver-to-naver
description: 네이버 블로그 글을 네이버 블로그로 복사·재발행합니다. 두 용도 — (1) 기존 글 재발행(네이버 검색에 안 잡히는 글을 원본 화질 그대로 새 글로 다시 올림), (2) 다른 네이버 블로그 글 마이그레이션. 인라인 이미지가 966px 열화 프리뷰라 그대로 재업로드하면 화질이 죽는 문제를 postfiles ?type=w3840 원본 다운로드로 해결하고, 네이버 임베드 잔해를 정제한 뒤 paste_to_naver.py로 새 글에 페이스트합니다. 사용 시점 — 사용자가 네이버 글 URL/logNo를 주며 "재발행", "다시 올려", "네이버 글 복사", "네이버에서 네이버로 옮겨", "검색 안 잡히는데 다시 발행", "다른 네이버 블로그 글 가져와" 등을 요청할 때 반드시 사용. tistory→naver가 아니라 naver→naver인 점에 주의.
---

# naver-to-naver — 네이버 → 네이버 글 복사·재발행

네이버 블로그 글 하나를 **원본 화질 그대로** 네이버 블로그 새 글로 다시 올리는 스킬.

## 두 가지 용도

1. **기존 글 재발행** — 내 글(예: `op5321`)이 발행됐는데 네이버 검색에 안 잡힐 때, 같은 내용을 새 글로 다시 올려 재색인을 노린다. 새 글이 하나 더 생기므로 **옛 글은 사용자가 직접 삭제**한다(삭제는 스킬이 못 함).
2. **다른 네이버 블로그 글 마이그레이션** — 다른 블로그(다른 blogId)의 글을 내 블로그로 옮긴다. `--blog-id`로 소스 블로그 지정.

## 언제 쓰나
- 네이버 글 URL/logNo를 주며 "재발행 / 다시 올려 / 네이버 글 복사 / 네이버→네이버 / 검색 안 잡히는데 다시 발행"
- "다른 네이버 블로그 이 글 내 블로그로 가져와"
- tistory URL이면 이 스킬이 아니라 `/tistory-to-naver`.

## 재발행 전 먼저 확인 (검색 누락 케이스)
"검색 안 됨"이 꼭 재발행으로 풀리는 건 아니다. 재발행은 중복글을 만들고 근본 원인(품질필터)까지 복사할 수 있으니, 먼저 값싼 수단을 권한다.
- 글이 `robots: noindex`인지 curl로 확인(아니면 네이버가 색인을 막은 게 아님 = 지연/필터).
- **블로그 전체 문제 vs 이 글만**: 다른 최근 글이 네이버 검색에 잡히면(`m.search.naver.com/search.naver?where=m_blog&query=...`에 blogId 노출) 블로그는 정상, 이 글만 누락 → 글 특이적 필터 가능성. 제목의 급조 신조어·투자/과금 유도 문구 등이 후보.
- **먼저 권할 것**: 네이버 서치어드바이저 URL 수집요청(사용자), 또는 글 수정 후 재저장(URL·나이 유지, 중복 없음). 재발행은 이것들이 안 될 때.

## 실행 절차

### 1. draft 생성 (원본 이미지 포함) — 안전, 로컬
```bash
python3 scripts/build_draft.py <네이버_글_URL_또는_logNo> [--blog-id op5321] [--out <draft_dir>]
```
- curl(아이폰 UA + `Referer: https://blog.naver.com/`)로 `m.blog` 본문 fetch → `_lib/parse_smarteditor.py`로 마크다운 추출.
- **이미지를 원본으로 다운로드**(아래 "이미지 원본 규칙"). 인라인 프리뷰가 아니라 `postfiles ?type=w3840` 원본.
- 네이버 임베드 잔해 정제(아래).
- `<draft_dir>/script.md` + `meta.json`(images.source_folder) + `images/` 생성.
- 출력의 제목·이미지 수·실패 수·총 용량을 사용자에게 보고. 실패 이미지가 있으면 그 URL을 확인.

### 2. 네이버 새 글쓰기 탭 확보
- claude-in-chrome은 `*.naver.com` 하드블록 → **osascript 경로만 유효**([[feedback_naver_no_webfetch]]: 읽기는 curl, 쓰기는 osascript).
- `osascript -e 'tell application "Google Chrome" to get URL of tabs of windows'`로 탭 확인. 없으면 `https://blog.naver.com/<myId>/postwrite` 새 탭. 임시저장 다이얼로그가 뜨면 JS로 취소.

### 3. 본문 페이스트
```bash
python3 <repo>/blog/scripts/paste_to_naver.py <draft_dir>
```
- `script.md`를 텍스트/이미지 청크로 쪼개 클립보드→Cmd+V로 순차 주입. 이미지는 `NSURL` 파일로 올려 네이버가 자동 업로드(그래서 원본 파일이어야 화질 유지).
- 사진-먼저·캡션-후·여백 규칙은 paste_to_naver가 자동 적용(`/blog` 스킬과 동일 정본). 제목(`#`)은 본문에서 빠지고 터미널에 출력됨.
- CGEvent 실제 클릭·키입력이라 **실행 ~1~2분간 사용자가 마우스·키보드를 건드리면 안 됨**을 사전 고지.

### 4. 제목 입력 + 검토 + 발행
- 제목은 `pbcopy` → 제목칸 클릭 → Cmd+V로 자동 입력(또는 사용자가 붙여넣기).
- **발행 클릭은 기본 수동**(사용자가 에디터에서 검토 후). "발행까지 해줘" 명시 시에만 `tistory-to-naver-blog` 리포의 `publish_with_category.py <categoryTestId>`로 카테고리 지정+공개 발행.

### 5. (재발행 모드) 옛 글 삭제
- 새 글 발행을 확인한 뒤, **사용자가 직접** 옛 글을 삭제한다. 스킬은 삭제를 수행하지 않는다.

## 이미지 원본 규칙 (이 스킬의 핵심)

네이버 본문 인라인 이미지는 **966px로 다운스케일된 프리뷰**다. 그대로 재업로드하면 화질이 죽는다. PC에서 이미지를 클릭하면 고화질이 뜨는 이유가 이것 — 별도의 큰 버전을 부른다. 실측(2026-07-12):

| URL 형태 | 결과 |
|---|---|
| `postfiles`/`mblogthumb` `?type=w966` (인라인·PC클릭 프리뷰) | 966px 프리뷰(열화) |
| `postfiles.pstatic.net/<경로>` 쿼리 없음 | 14KB짜리 기본 썸네일(더 나쁨) |
| **`postfiles.pstatic.net/<경로>?type=w3840`** | **원본**(원본 폭이 3840 미만이면 그 폭 그대로 = 진짜 원본) |
| `blogfiles.pstatic.net/<경로>` 쿼리 없음 | 원본(w3840과 바이트 동일) |
| `?type=w1000`/`w0`, 쿼리없는 `mblogthumb` | 404 |

- **정본은 `postfiles + ?type=w3840`.** `w3840`은 "최대 3840폭"이라 원본이 그보다 작으면 원본을 그대로 준다(업스케일 아님).
- `build_draft.py`의 `download_original`이 이 우선순위(w3840 → blogfiles → w966)로 가장 큰 200 응답을 받는다. 파일명이 `_s.jpg`면 `_s`를 뗀 것도 시도.
- 주의: 재업로드해도 네이버가 다시 다운스케일하지만, **원본을 올려야** 새 글의 "PC 클릭 고화질"이 원본으로 저장된다. 프리뷰를 올리면 새 글도 프리뷰가 최대치가 됨.

## 네이버 임베드 잔해 정제

`parse_smarteditor.py`는 네이버의 지도 위젯·링크 카드·표를 본문 텍스트로 잘못 뽑는다. 그대로 두면 요약/본문이 오염되니 제거한다(`build_draft.py`가 자동):
- `<!-- unhandled placesMap -->` / `<!-- unhandled table -->` 코멘트 → 코멘트만 떼고 뒤 텍스트(주소 등)는 유지.
- `<!-- unhandled unknown -->`로 시작하는 줄 → **줄 통째로 삭제**(다른 글 링크 카드 임베드).
- `이 블로그의 체크인`, `이 장소의 다른 글`(지도 위젯 UI), bare 도메인 줄(`blog.naver.com`), `방문일 :`로 시작하는 줄(링크 카드 설명) → 삭제.

## 하드룰

- **무인 발행 금지** — 네이버 업로드를 사용자 부재/미확인 상태로 돌리지 말 것(2026-06-16 대형 사고). 매크로 실행 전 사용자가 자리에 있고 "진행" 의사가 있는지 확인. 발행 클릭은 기본 수동.
- **마우스·키보드 비접촉** — paste_to_naver는 좌표 기반 실제 클릭이라, 도는 동안 다른 창을 띄우거나 입력하면 엉뚱한 곳에 붙는다. 실행 전 "1~2분 건드리지 마세요" 고지.
- **삭제는 사용자 몫** — 재발행으로 생긴 중복 옛 글 삭제는 스킬이 하지 않는다(영구 삭제는 금지 동작).
- **이미지는 반드시 원본(w3840)** — 프리뷰 재업로드 금지.
- **이모지 금지** — SKILL.md·스크립트 산출물에 한 글자도. (단 본문은 사용자 원문 그대로 옮기므로 원문 이모지는 유지됨.)
- **네이버 읽기는 curl, 쓰기는 osascript** — WebFetch·claude-in-chrome navigate는 네이버에서 막힘.

## 함정
- macOS 전용(AppKit·osascript·CGEvent). Chrome "Apple Events의 자바스크립트 허용" + 손쉬운 사용에 터미널 체크 필요(1회).
- 이미지 수십 장 원본이면 수백 MB가 될 수 있음(정상). `build_draft.py`가 총 용량을 보고.
- 소스가 다른 블로그면 `--blog-id`로 지정(URL로 주면 자동 추출).
- 재발행이 검색 문제를 항상 푸는 건 아님 — "재발행 전 먼저 확인" 참조.

## 의존
- `curl`(아이폰 UA), `python3`, macOS `sips`(이미지 검증 시)
- `_lib/parse_smarteditor.py`(리포 공유, `blog-learn`·`naver-to-tistory-backlink`와 동일)
- `blog/scripts/paste_to_naver.py`(네이버 페이스트 정본)
- `~/Desktop/Project/personal/tistory-to-naver-blog/publish_with_category.py`(카테고리+발행 opt-in)
- `scripts/build_draft.py`(이 스킬 — URL→원본이미지 draft 생성)

## 관련 스킬·메모리
- `/tistory-to-naver` — 반대 소스(티스토리→네이버). 네이버 페이스트 기계장치를 공유.
- `/blog` — 네이버 새 글 작성 + `paste_to_naver.py` 정본.
- `/naver-to-tistory-backlink` — 네이버 글의 티스토리 정리본(구글 SEO용, 네이버 검색과 별개).
- 메모리: `feedback_naver_no_webfetch`(읽기 curl/쓰기 osascript), `reference_naver_blog_url`.
