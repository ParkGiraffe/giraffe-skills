---
name: tistory-to-naver
description: Tistory 블로그 글을 네이버 블로그 에디터로 자동 마이그레이션합니다. tistory.com 게시물 URL을 받아 본문·이미지·섹션 헤딩(노란 배경 볼드)·구분선을 보존한 채 네이버 SmartEditor에 순차 페이스트합니다. 사용 시점 — 사용자가 Tistory 게시물 URL을 주면서 "네이버로 옮겨줘", "네이버에 복붙", "이전해줘", "마이그레이션", "tistory를 naver로", `/tistory-to-naver <URL>` 등을 요청할 때.
---

# tistory-to-naver — Tistory → 네이버 블로그 자동 이전

박기린(`op5321`)이 Tistory(`arnopark.tistory.com`)에서 작성했던 글을 네이버 블로그(`blog.naver.com/op5321`)로 그대로 옮길 때 쓰는 스킬.

Tistory 글을 그냥 복사해서 네이버에 붙이면:
- 이미지를 네이버가 거부함 (외부 CDN URL 차단)
- 섹션 헤딩(`<h2>`) / 구분선(`<hr>`) 같은 구조가 평문화돼서 사라짐

이 스킬은 두 문제 모두 해결한 매크로(`ParkGiraffe/tistory-to-naver-blog`)를 호출합니다.

## 언제 쓰나
- 사용자가 `https://*.tistory.com/<번호>` 형태 URL을 주면서 네이버 이전을 요청할 때
- "/tistory-to-naver <URL>" 명령으로 명시적으로 호출했을 때
- "Tistory 글 복붙", "이 글 네이버로", "마이그레이션" 같은 의도가 명확할 때

## 사전 준비 (1회)
- 매크로 도구가 클론돼 있어야 함: `~/Desktop/Project/personal/tistory-to-naver-blog/`
  (없으면 `git clone https://github.com/ParkGiraffe/tistory-to-naver-blog.git` 으로 클론)
- 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용에 터미널(또는 iTerm) 체크
  (Auto 모드의 Cmd+V 자동 전송 권한)
- Chrome 메뉴 바 → 보기 → 개발자 → "Apple Events의 자바스크립트 허용" 체크
  (코드블록 Pass 2의 osascript in-page JS 주입 권한. 코드블록 없는 글이면 불필요)

## 실행 절차 (단일 명령 — 사용자 액션 0회)

**디폴트는 `migrate.py` 원샷 파이프라인** (2026-06-12 도입, 908 기준 72초 완주).
시작 전 "약 1~2분간 키보드·마우스를 건드리지 마세요"만 고지하고 실행:

```bash
cd ~/Desktop/Project/personal/tistory-to-naver-blog
python3 migrate.py '<TISTORY_URL>' [--clear]
```

내부 6단계 (전부 자동):
1. Tistory fetch + 이미지 병렬 다운로드(6스레드) + 청크 분할
2. postwrite 탭 확보(URL 재탐색, 없으면 열기) + 임시저장 다이얼로그 JS 취소
   + `hasFocus` 폴링으로 창 포커스 보장. 에디터가 비어있지 않으면 ABORT
   (`--clear` 줘야 Cmd+A+Backspace로 초기화 — 초안 보호)
3. 제목 페이스트 (트리플클릭 선택→교체 방식이라 재시도해도 중복 없음.
   검증 비교는 NBSP(\xa0) 정규화 필수 — SE가 공백을 NBSP로 렌더링함)
4. 본문 청크 페이스트 + 청크별 등록 검증(0.2초 폴링, 3회 재시도) —
   이미지는 `se-image` 수, 텍스트는 `.se-text p` 수 증가로 확인
   (SE가 연속 텍스트를 한 컴포넌트로 합치므로 컴포넌트 수는 부정확)
5. 코드블록 Pass: `[[CODE-n]]` placeholder → native `se-code` 주입
   (`inject_code_blocks.py` 자동 호출)
6. 스타일 패스 (합성 JS만, 실입력 불필요): 모든 구분선 → `line3`
   (가운데 꺾임) + 가운데 정렬, 모든 사진 → 가운데 정렬.
   원리: 컴포넌트 합성 클릭 선택 → ~500ms 대기(property toolbar 렌더) →
   `button[data-name=horizontal-line-layout][data-value=line3]` /
   `button[data-name=align][data-value=center]` 클릭

종료 시 소요 시간 + 컴포넌트 카운트 + 잔여 marker 감사가 출력됨.
**디폴트로 migrate.py는 본문만 에디터에 붙이고 멈춤** — 카테고리 지정도 발행도 안 함.
사용자가 에디터에서 결과 검토 후 **발행 버튼만 직접 클릭**하는 게 기본 흐름.
코드블록 언어 표기는 기본 javascript — 다른 언어면 수동 변경.

레거시 단계별 실행(`run_migration.py` + `inject_code_blocks.py`)도 유지되며
디버깅 시에만 사용.

## 카테고리 지정 + 발행 (opt-in)

**기본은 자동 발행 안 함.** 사용자가 "발행까지 해줘"라고 명시할 때만 아래를 추가 실행한다
(standing 안전규칙: 무인 네이버 업로드 금지·포커스 검증 필수, 2026-06-16 사고 교훈).

```bash
# migrate.py로 본문을 붙인 뒤, 별도 단계로 카테고리 선택 + 공개 발행
python3 publish_with_category.py <categoryTestId>   # 예: 142 = GoodWishes 제작기
```

- 네이버는 claude-in-chrome(`*.naver.com` 차단)·computer-use(브라우저=read 등급, 클릭 차단)
  둘 다 막혀서 **osascript in-page JS 주입이 유일 경로** (`inject_code_blocks.py`의
  `find_postwrite_tab`/`chrome_js`/`osa` 재사용).
- DOM 셀렉터(2026-06-23 실측): 발행레이어 `button.publish_btn__`, 카테고리 셀렉트박스
  `.selectbox_button__jb1Dt`(aria-expanded로 열림 판단), 항목 `[data-testid=categoryItemText_<N>]`
  → 클릭은 `el.closest("label")`, 최종발행 `[class*=confirm_btn__]`.
- **함정**: osascript 콜마다 창을 앞으로 올리면 floating 레이어가 blur로 닫힘 →
  열기·폴링·선택·확정을 한 IIFE setTimeout 체인으로 하고 결과를 `window.__pr` 전역에 적어 폴링.
  발행 성공 신호 = postwrite 탭이 사라짐(리다이렉트).
- 카테고리 testid는 셀렉트박스 열어 `data-testid^=categoryItem` 덤프로 확인.
  관측값: GoodWishes 제작기=142, Marpia 제작기=143, Pokedex-ai 개발기=144, 젤다 왕눈=132.

## 카테고리 전체 일괄 마이그레이션 (`migrate_category.py`)

한 Tistory 카테고리의 글을 시리즈 순서대로 한 번에 옮긴다.

```bash
python3 migrate_category.py '<CATEGORY_URL>' [옵션]
  --publish <testid>  편마다 카테고리 지정+발행까지 (opt-in; 생략 시 초안만, 첫 편에서 멈춤)
  --grep <regex>      제목 필터 (예: '제작기')
  --start <N>         앞 N편 건너뛰기 (배치 재개용)
  --limit <N>         최대 N편
  --reverse           최신순 (기본 과거순)
  --dry-run           대상 목록만 출력
```

동작: 카테고리 페이지네이션을 훑어 `/숫자` 링크+제목 수집 → 제목의 시리즈 번호로 정렬 →
편마다 `migrate.py`(+`--publish` 시 `publish_with_category.py`) 순차 실행. 실패 시 중단.

- **`--publish` 없으면 첫 편만 붙고 멈춤** (migrate.py가 비어있지 않은 에디터에서 ABORT하므로).
  전체 배치를 무인으로 돌리려면 `--publish <testid>` 필수.
- **반드시 `--dry-run` 먼저**: 카테고리에 백링크 정리본(`naver-to-tistory-backlink` 산출물)이
  섞여 있으면 시리즈 번호가 중복돼 보인다. 목록 확인 후 `--grep`/`--start`로 거를 것.
- 실증: 2026-06-23 GoodWishes 제작기 13~19 7편을 `migrate.py + publish_with_category.py 142`
  순차 루프로 무사 발행(카테고리 전부 정확히 지정).

## 변환 규칙 (`migrate_from_url.py:split_content_into_chunks`)

`giraffe-skills/blog/scripts/paste_to_naver.py`와 동일한 SmartEditor 호환 HTML을 생성합니다 (시각적으로 `/blog` 스킬 결과물과 일치).

| Tistory 마크업 | 네이버 SmartEditor HTML |
|---|---|
| `<h1>` ~ `<h6>` (속에 `<span style="background-color:...">` 있어도 됨) | `<p><span style="font-size:24px;background-color:#fff593;"><b>텍스트</b></span></p>` + `<p><br></p>` barrier (`/blog` 스킬과 동일한 노란 배경 24px 볼드 시그니처) |
| `<hr data-ke-type="horizontalRule">` | `<hr>` (네이버가 자동으로 SmartEditor hr 블록으로 승격, 모양은 default 단선) |
| 일반 본문 `<p>`/`<div>` | `<p><span style="font-size:15px;font-weight:normal;background-color:transparent;color:#212529;">텍스트</span></p>` (헤딩 스타일 번짐 차단용 명시적 reset) |
| `<p>&nbsp;</p>` 빈 줄 | `<p><br></p>` barrier |
| `<img>` (Tistory CDN URL) | 로컬로 다운로드 후 별도 청크로 분리 → 클립보드에 파일 URL로 올려 페이스트 (네이버가 자동 업로드) |
| `<pre>` 코드블록 | Pass 1: `[[CODE-n]]` placeholder 본문 단락 + `/tmp/naver_code_blocks.json` 사이드카 → Pass 2(`inject_code_blocks.py`): native `se-code` 컴포넌트로 치환 |

핵심 트릭: 본문 청크엔 항상 `font-weight:normal; background-color:transparent;` 를 명시 — 네이버 sanitizer가 이전 헤딩 스타일을 본문 단락에 번지게 하는 버그를 막음.

**왜 native 소제목 컴포넌트를 안 쓰는가**: 네이버 SmartEditor의 paste 핸들러는 chromium의 `source-rfh-token` + 자체 `data-input-buffer` 토큰 둘 다 매칭돼야만 메모리에서 원본 컴포넌트를 복원합니다. 외부 매크로(터미널 Python AppKit)에서 만든 클립보드엔 이 토큰이 없으므로 어떤 SmartEditor 마크업을 박아도 **모두 본문 컴포넌트로 normalize됨**. 실측으로 정답 마크업을 한 자도 안 바꾸고 페이스트해도 본문 15px 볼드로 떨어짐을 확인. native 컴포넌트 inject는 in-process 자동화로만 가능 — 소제목은 시각 표시(노란 배경)로 충분해서 매크로 paste 를 유지.

**단, 코드블록은 in-process 주입이 됨** (2026-06-11 실측): osascript `execute javascript` (Chrome "Apple Events의 자바스크립트 허용" 필요)로 페이지 안에서 툴바 `button[data-name=code]` 를 클릭하면 에디터 자신의 핸들러가 정상 컴포넌트를 만들고, `.se-code-source-editor` textarea 에 native value setter + `input` 이벤트로 코드를 넣으면 모델이 수용함. 단 SE 는 합성(synthetic) paste/insertText 를 `isTrusted` 로 거부하므로, 캐럿 위치 잡기(트리플클릭)와 placeholder 삭제(Backspace)는 Quartz CGEvent 실제 입력으로 쏴야 함. 이 조합이 `inject_code_blocks.py` (Pass 2). 같은 원리로 소제목도 native 화 가능하지만 현재는 코드블록만 적용.

## 자동 footer 첨부

마이그레이션 시 글 맨 밑에 다음 형식의 footer가 자동으로 붙습니다.

```
해당 글은 티스토리 블로그 <원본 URL>의 글을 마이그레이션한 글입니다.

원본 작성일 : YYYY년 MM월 DD일

#태그1 #태그2 #태그3 ...
```

- 원본 URL은 링크(`<a href>`)로 자동 변환
- 작성일은 Tistory `<meta property="article:published_time">` 태그에서 추출 (ISO 8601 → 한국어 날짜 포맷)
- `published_time` 메타가 없으면 작성일 줄은 생략됨
- 태그는 Tistory `<div class="tags"><a rel="tag">…</a></div>` 에서 추출. 다중 단어 태그(`젤다 사당 공략`)는 내부 공백을 제거해 단일 해시태그(`#젤다사당공략`)로 변환
- **주의**: 이 해시태그는 본문 평문일 뿐 네이버의 진짜 태그(사이드바 태그 입력란)가 아님 — 검색·태그 페이지엔 안 잡히고 시각 표시만 함. 진짜 태그는 페이스트 종료 후 사용자가 직접 사이드바에 입력해야 함
- 구현: `migrate_from_url.py:_build_footer_html`, 태그 추출은 `fetch_post`

## 한계

- macOS 전용 (AppKit·NSPasteboard·osascript 의존)
- Tistory 외 다른 블로그 플랫폼은 지원 안 함 (셀렉터가 `.tt_article_useless_p_margin`, `.entry-content`, `<article>` 순)
- 동영상·iframe은 평문화될 가능성 (현재 스크립트 미대응)
- 코드블록 textarea 는 `maxlength=5000` — 5천 자 초과 코드는 잘림 (분할 필요)
- Pass 2 는 화면 좌표 기반 실제 클릭을 쓰므로 실행 중 다른 창을 띄우거나 입력하면 오작동
- 네이버 sanitizer 정책이 바뀌면 본문 스타일 번짐이 재발할 수 있음 — `paste_to_naver.py`의 `BODY_SPAN_STYLE`/`HEADING_SPAN_STYLE`을 같이 갱신할 것

## 의존 도구
- `ParkGiraffe/tistory-to-naver-blog` (외부 리포)
  - `run_migration.py`, `migrate_from_url.py`, `inject_code_blocks.py` (Pass 2)
  - 패키지: `requests`, `beautifulsoup4`, `pyobjc-framework-Cocoa` (스크립트가 자동 설치),
    `pyobjc-framework-Quartz` (Pass 2 CGEvent 용)

## 관련 스킬
- `/blog` — 네이버 블로그 새 글 자동 작성 + 페이스트 (`paste_to_naver.py` 정본 보유)
- `/blog-learn` — 네이버 블로그 코퍼스 학습
