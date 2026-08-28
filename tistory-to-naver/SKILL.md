---
name: tistory-to-naver
description: Tistory 블로그 글을 네이버 블로그 에디터로 자동 마이그레이션합니다. tistory.com 게시물 URL을 받아 본문·이미지·섹션 헤딩(노란 배경 볼드)·구분선을 보존한 채 네이버 SmartEditor에 순차 페이스트하고, 하단 태그 줄은 `naver-blog-tags` 방식으로 새로 뽑아 붙입니다(기본 동작). 사용 시점: 사용자가 Tistory 게시물 URL을 주면서 "네이버로 옮겨줘", "네이버에 복붙", "이전해줘", "마이그레이션", "tistory를 naver로", `/tistory-to-naver <URL>` 등을 요청할 때.
---

# tistory-to-naver — Tistory → 네이버 블로그 자동 이전

박기린(`op5321`)이 Tistory(`arnopark.tistory.com`)에서 작성했던 글을 네이버 블로그(`blog.naver.com/op5321`)로 그대로 옮길 때 쓰는 스킬.

Tistory 글을 그냥 복사해서 네이버에 붙이면:
- 이미지를 네이버가 거부함 (외부 CDN URL 차단)
- 섹션 헤딩(`<h2>`) / 구분선(`<hr>`) 같은 구조가 평문화돼서 사라짐

이 스킬은 두 문제 모두 해결한 매크로를 `scripts/`에 직접 담고 있습니다.

## 언제 쓰나
- 사용자가 `https://*.tistory.com/<번호>` 형태 URL을 주면서 네이버 이전을 요청할 때
- "/tistory-to-naver <URL>" 명령으로 명시적으로 호출했을 때
- "Tistory 글 복붙", "이 글 네이버로", "마이그레이션" 같은 의도가 명확할 때

## 사전 준비 (1회)
- 패키지: `pip install --user requests beautifulsoup4 pyobjc-framework-Cocoa pyobjc-framework-Quartz`
- 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용에 터미널(또는 iTerm) 체크
  (Auto 모드의 Cmd+V 자동 전송 권한)
- Chrome 메뉴 바 → 보기 → 개발자 → "Apple Events의 자바스크립트 허용" 체크
  (코드블록 Pass 2의 osascript in-page JS 주입 권한. 코드블록 없는 글이면 불필요)

## 제목 재작성 (기본 동작, 2026-08-24 확정)

**티스토리 원제를 그대로 옮기지 않는다.** 네이버 제목 컨벤션은 `[카테고리] 본문 : 부제`인데
티스토리 원제는 대괄호 안에 형태 토큰이 붙고(`[호그와트 레거시 - 팁]`) 구분자가 `/`라,
그대로 옮기면 같은 시리즈의 네이버 글들과 형식이 어긋난다. migrate 실행 **전에** 제목을
확정해 `--title`로 넘긴다.

1. 네이버 post-list API로 **같은 시리즈의 실제 네이버 제목**을 열거해 대괄호 표기·구분자·부제
   구성을 확인한다. 제목의 정본(SSOT)은 언제나 네이버 원본이고 티스토리가 아니다.
   ```bash
   curl -s -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15" \
     -H "Referer: https://m.blog.naver.com/op5321" \
     "https://m.blog.naver.com/api/blogs/op5321/post-list?categoryNo=0&itemCount=30&page=1" \
     | python3 -c "import sys,json,html; d=json.load(sys.stdin); [print(p.get('logNo'), html.unescape(p.get('titleWithInspectMessage',''))) for p in d['result']['items']]"
   ```
   같은 시리즈의 앞 글이 이미 옮겨져 있으면 그 글이 정답 템플릿이다. 그 네이버 글을 curl로
   받아 본문의 `arnopark.tistory.com/<번호>` 백링크를 보면, 어느 티스토리 글이 어떤 제목으로
   재작성됐는지 1:1로 확인된다.
2. 그 컨벤션에 맞춘 후보를 **2~3개 만들어 AskUserQuestion으로 고르게 한다.** 제목은 글에서
   가장 눈에 띄는 산출물이라 사용자가 직접 고르는 편이 낫고, 후보를 나란히 보여주면 판단이
   한 번에 끝난다. 후보끼리는 부제 축을 달리한다(위치 안내형 / 개체 나열형 / 핵심 키워드 강조형).
   부제 문구는 `naver-blog-tags/scripts/related_keywords.py`로 확인한 실제 검색 수요에서 가져온다.
3. 고른 제목을 `--title "..."`로 넘긴다.

실측(2026-08-24, 티스토리 591): 원제 `[호그와트 레거시 - 팁] 놓친 어둠의 마법 다시 배우기`를
직전 590의 네이버 제목(`[호그와트 레거시] 엄청난 양의 곱스톤 : 곱스톤 6개 위치 전부 찾기`)에
맞춰 `[호그와트 레거시] 놓친 어둠의 마법 다시 배우기 : 세바스찬 위치와 언더크로프트 가는 법`으로
재작성했다.

시리즈 선례가 없어 컨벤션을 못 찾겠으면 `/blog-title` 스킬로 후보 5개를 뽑는다.

## 실행 절차 (단일 명령, 사용자 액션 0회)

**디폴트는 `migrate_fresh_tab.py`** (2026-08-20 확정 — 883 마이그레이션 사고 이후).
시작 전 "약 1~2분간 키보드·마우스를 건드리지 마세요"만 고지하고 실행:

```bash
cd <giraffe-skills 리포 루트>
python3 tistory-to-naver/scripts/migrate_fresh_tab.py '<TISTORY_URL>' \
  --title "[카테고리] 본문 : 부제" \
  --tags "전체 태그 15~25개" --core-tags "핵심 태그 10~12개"
```

`--title`·`--tags`·`--core-tags`는 전부 실행 전에 확정해 둔다(위 "제목 재작성", 아래 "태그 새로 작성").
`--core-tags`를 빠뜨리면 본문 footer에 전체 세트 한 줄만 붙어서, 사용자가 핵심 세트를 붙일 때
쓸 줄이 글 안에 없다. 매번 같이 넘긴다.

**기존 postwrite 탭은 절대 건드리지 않는다 — 닫지도, 비우지도(`--clear` 금지),
재사용하지도 않는다. 항상 새 탭을 열어 그 탭에서만 작업한다.** 사용자가 여러 차례
반복 지시로 확정한 하드룰이다. 위반 시 벌어진 실측 사고: 탭 재사용 → 임시저장
복원분에 붙여넣어 중복·서식 전이, `--clear` → 캐럿에 남은 서식이 새 본문에 전이,
탭 닫기 시도 → beforeunload alert가 매크로 전체를 블로킹.

`migrate.py`를 직접 부르면 '첫 번째' postwrite 탭을 조준하므로 기존 탭이 있으면
사고가 난다. `migrate_fresh_tab.py`가 새 탭을 열고 '마지막' postwrite 탭 조준으로
바꿔치기한 뒤 migrate.py의 main을 그대로 실행한다. 새 탭이 비어있지 않으면
비우지 않고 ABORT한다.

**워터마크 (2026-08-20 도입)**: 다운로드되는 모든 사진 우측 하단에
`blog.naver.com/op5321`(배달의민족 도현체, 글자 높이 = 폭의 2.57%, 불투명도 150)을
자동 삽입한다 (정본은 리포 공용 `_lib/watermark.py`, `scripts/watermark.py`는 그걸 넘겨주는
래퍼다. 스타일 상수는 사용자 확정값 — 임의 변경 금지).
GIF는 프레임이 깨지므로 건너뛴다. 끄려면 `WATERMARK=0` 환경변수.
이미지 캐시(`scripts/images/`)는 매 실행 전 자동으로 비운다 — 캐시 재사용 시
이전 실행의 다른 워터마크 스타일이 섞여 들어가는 사고가 있었다.

이 스킬은 `scripts/`(변환 엔진)와 리포 공용 `_lib/`(에디터 매크로)을 함께 쓰므로
**명령은 리포 루트에서 실행**한다. 심링크로 설치된 `~/.claude/skills/tistory-to-naver`에서
`../_lib`을 찾으면 없다.

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
   (`_lib/inject_code_blocks.py` 자동 호출. `migrate.py`가 `__file__` 기준으로
   리포 루트를 계산해 부르므로 CWD와 무관하게 찾는다)
6. 스타일 패스 (합성 JS만, 실입력 불필요): 모든 구분선 → `line3`
   (가운데 꺾임) + 가운데 정렬, 모든 사진 → 가운데 정렬.
   원리: 컴포넌트 합성 클릭 선택 → ~500ms 대기(property toolbar 렌더) →
   `button[data-name=horizontal-line-layout][data-value=line3]` /
   `button[data-name=align][data-value=center]` 클릭

종료 시 소요 시간 + 컴포넌트 카운트 + 잔여 marker 감사가 출력됨.
**디폴트로 migrate.py는 본문만 에디터에 붙이고 멈춤** — 카테고리 지정도 발행도 안 함.
사용자가 에디터에서 결과 검토 후 **발행 버튼만 직접 클릭**하는 게 기본 흐름.
코드블록 언어 표기는 기본 javascript — 다른 언어면 수동 변경.

레거시 단계별 실행(`scripts/run_migration.py` + `_lib/inject_code_blocks.py`)도 유지되며
디버깅 시에만 사용.

## 태그 새로 작성 (기본 동작, 2026-07-29 확정)

**사용자가 태그를 언급하지 않아도 매번 새로 뽑는다.** 티스토리 원본 태그를 그대로 쓰지 않는다
(개수가 3~5개로 적고, `인사이드 아웃`/`인사이드아웃`처럼 공백만 다른 태그가 해시태그로 바뀌면서 중복됨).

절차는 `/naver-blog-tags` 스킬을 그대로 따른다. migrate 실행 **전에** 끝내야 `--tags`로 넘길 수 있다.

1. 원본을 curl(아이폰 UA)로 받아 제목·본문·고유명사 추출
2. `naver-blog-tags/scripts/related_keywords.py "키워드" ...`로 네이버 자동완성 수요 확인.
   맨단어가 다른 뜻과 섞이면(`빙봉`→성수동 카페, `부럽이`→노래) 합성 태그를 우선하고 맨단어는 1~2개만
3. 같은 카테고리 최근 글의 태그 구성을 템플릿으로 삼는다.
   영화감상문 템플릿(2026-07-29 모아나 글 기준): 작품명 + 작품명×(후기/리뷰/감상문/줄거리/해석/결말)
   + 등장인물 합성 + 감독·제작사 + 광역(영화감상문/영화후기/영화추천/영화)
4. **전체 세트와 핵심 세트 두 벌을 만들어 둘 다 넘긴다.** 공백 구분, `#` 없이(쉼표도 허용):
   `--tags "전체 15~25개" --core-tags "핵심 10~12개"`.
   그러면 본문 footer에 전체 태그 줄이 붙고, **빈 줄 하나를 띄운 뒤 핵심 태그 줄**이 따로 붙는다.
   사용자는 발행 레이어 태그란에 상황에 따라 위(전체)나 아래(핵심)를 골라 붙이므로, 글 안에도
   두 줄이 다 있어야 한다. 한 줄만 있으면 그 자리에서 핵심 세트를 다시 만들어야 한다
   (2026-08-24 지시. 클립보드만 2블록으로 넣고 footer를 한 줄로 두는 것은 요구를 절반만 지킨 것).
5. migrate 종료 후 **묻지 말고 곧바로** 클립보드에 복사한다. 형식은 `/naver-blog-tags`와 같은
   **2블록 고정**: 전체 세트 → 빈 줄 2개 → 핵심 10~12개. 사용자가 상황에 따라 위(전체)나
   아래(핵심)를 골라 붙여넣으므로, 한 블록만 넣으면 "핵심만 다시 뽑아줘"를 매번 요청하게 만든다.
   `clip.py`는 줄바꿈을 단일 공백으로 정규화하므로 2블록에는 쓸 수 없다. `pbcopy`에 직접 넣는다:

   ```bash
   python3 - <<'PY'
   import subprocess
   full = "#태그1 #태그2 ..."           # 전체 세트 15~29개
   core = "#핵심1 #핵심2 ..."           # 핵심 10~12개
   payload = full + "\n\n\n" + core    # 사이에 빈 줄 2개
   subprocess.run(["pbcopy"], input=payload.encode("utf-8"), check=True)
   assert subprocess.run(["pbpaste"], capture_output=True).stdout.decode() == payload
   PY
   ```

   핵심 블록 선정 기준: 네이버 자동완성에 실제로 잡히는 조합 우선, 글의 각 섹션과 1:1 대응,
   광역 태그(`#해리포터`, `#호그와트`처럼 경쟁이 과열된 단일어)는 제외. 복사 후 `pbpaste`로
   검증하고 두 블록의 개수를 각각 보고한다.
   본문 하단 해시태그는 시각 표시일 뿐이라 사용자가 발행 레이어 태그란에 따로 붙여야 진짜 태그가 된다

`--tags`를 생략하면 예전처럼 티스토리 원본 태그가 들어간다(2026-07-29 `migrate.py`에 추가한 플래그,
`--title`과 같은 파싱 방식이라 URL을 첫 인자로 두면 된다).

## 카테고리 지정 + 발행 (opt-in)

**기본은 자동 발행 안 함.** 사용자가 "발행까지 해줘"라고 명시할 때만 아래를 추가 실행한다
(standing 안전규칙: 무인 네이버 업로드 금지·포커스 검증 필수, 2026-06-16 사고 교훈).

```bash
# migrate.py로 본문을 붙인 뒤, 별도 단계로 카테고리 선택 + 공개 발행
python3 _lib/publish_with_category.py <categoryTestId> "<카테고리명>"
# 예: python3 _lib/publish_with_category.py 142 "GoodWishes 제작기"
```

**2번째 인자(기대 카테고리명)를 반드시 넘긴다.** 생략하면 `"제작기"`가 기본값으로 들어가서
(`publish_with_category.py:33`), 제작기 계열이 아닌 카테고리에서는 발행 직전 검증이 실패하고
exit 2로 멈춘다. 1번째 인자를 생략하면 `142`가 기본값이다.

- 네이버는 claude-in-chrome(`*.naver.com` 차단)·computer-use(브라우저=read 등급, 클릭 차단)
  둘 다 막혀서 **osascript in-page JS 주입이 유일 경로** (`_lib/inject_code_blocks.py`의
  `find_postwrite_tab`/`chrome_js`/`osa` 재사용. 같은 `_lib/`에 있어 import가 그대로 걸린다).
- DOM 셀렉터(2026-06-23 실측): 발행레이어 `button.publish_btn__`, 카테고리 셀렉트박스
  `.selectbox_button__jb1Dt`(aria-expanded로 열림 판단), 항목 `[data-testid=categoryItemText_<N>]`
  → 클릭은 `el.closest("label")`, 최종발행 `[class*=confirm_btn__]`.
- **함정**: osascript 콜마다 창을 앞으로 올리면 floating 레이어가 blur로 닫힘 →
  열기·폴링·선택·확정을 한 IIFE setTimeout 체인으로 하고 결과를 `window.__pr` 전역에 적어 폴링.
  발행 성공 신호 = postwrite 탭이 사라짐(리다이렉트).
- 카테고리 testid는 `python3 tistory-to-naver/scripts/dump_categories.py`로 덤프하거나,
  셀렉트박스를 열어 `data-testid^=categoryItem`를 직접 확인.
  관측값: GoodWishes 제작기=142, Marpia 제작기=143, Pokedex-ai 개발기=144, 젤다 왕눈=132,
  JavaScript 강의실=147.

## 카테고리 전체 일괄 마이그레이션 (`migrate_category.py`)

한 Tistory 카테고리의 글을 시리즈 순서대로 한 번에 옮긴다.

```bash
python3 tistory-to-naver/scripts/migrate_category.py '<CATEGORY_URL>' [옵션]
  --publish <testid>  편마다 카테고리 지정+발행까지 (opt-in; 생략 시 초안만, 첫 편에서 멈춤)
  --grep <regex>      제목 필터 (예: '제작기')
  --start <N>         앞 N편 건너뛰기 (배치 재개용)
  --limit <N>         최대 N편
  --reverse           최신순 (기본 과거순)
  --dry-run           대상 목록만 출력
```

동작: 카테고리 페이지네이션을 훑어 `/숫자` 링크+제목 수집 → 제목의 시리즈 번호로 정렬 →
편마다 `scripts/migrate.py`(+`--publish` 시 `_lib/publish_with_category.py`) 순차 실행. 실패 시 중단.

- **`--publish` 없으면 첫 편만 붙고 멈춤** (migrate.py가 비어있지 않은 에디터에서 ABORT하므로).
  전체 배치를 무인으로 돌리려면 `--publish <testid>` 필수.
- **반드시 `--dry-run` 먼저**: 카테고리에 백링크 정리본(`naver-to-tistory-backlink` 산출물)이
  섞여 있으면 시리즈 번호가 중복돼 보인다. 목록 확인 후 `--grep`/`--start`로 거를 것.
- 실증: 2026-06-23 GoodWishes 제작기 13~19 7편을 `migrate.py + publish_with_category.py 142`
  순차 루프로 무사 발행(카테고리 전부 정확히 지정). 당시엔 두 스크립트가 외부 리포에 있었고,
  2026-07-30 이 리포로 흡수하며 경로만 바뀌었다.

## 변환 규칙 (`scripts/migrate_from_url.py:split_content_into_chunks`)

`blog/scripts/paste_to_naver.py`와 동일한 SmartEditor 호환 HTML을 생성합니다 (시각적으로 `/blog` 스킬 결과물과 일치).

| Tistory 마크업 | 네이버 SmartEditor HTML |
|---|---|
| **대제목** = `<h1>`, 또는 노란 배경 스팬(`<span style="background-color:...">`)을 가진 `<h2>~<h6>` | `<p><span style="font-size:24px;background-color:#fff593;"><b>텍스트</b></span></p>` + `<p><br></p>` barrier (노란 배경 24px 볼드) |
| **소제목** = 노란 배경 없이 볼드만 있는 `<h3>~<h6>` (예: Tistory `<h3><b>1. Function declaration</b>`) | `<p><span style="font-size:19px;background-color:transparent;color:#212529;"><b>텍스트</b></span></p>` + barrier (19px 볼드·배경 없음). 2026-06-27 추가 — 레벨을 뭉개 소제목이 대제목처럼 뜨던 버그 수정. 판정은 heading 안 `background-color` 스팬 유무(`_heading_has_highlight`) |
| `<hr data-ke-type="horizontalRule">` | `<hr>` (네이버가 자동으로 SmartEditor hr 블록으로 승격, 모양은 default 단선) |
| 일반 본문 `<p>`/`<div>` | `<p><span style="font-size:15px;font-weight:normal;background-color:transparent;color:#212529;">텍스트</span></p>` (헤딩 스타일 번짐 차단용 명시적 reset) |
| `<p>&nbsp;</p>` 빈 줄 | `<p><br></p>` barrier |
| `<img>` (Tistory CDN URL) | 로컬로 다운로드 후 별도 청크로 분리 → 클립보드에 파일 URL로 올려 페이스트 (네이버가 자동 업로드) |
| `<pre>` 코드블록 | Pass 1: `[[CODE-n]]` placeholder 본문 단락 + `/tmp/naver_code_blocks.json` 사이드카 → Pass 2(`_lib/inject_code_blocks.py`): native `se-code` 컴포넌트로 치환 |

핵심 트릭: 본문 청크엔 항상 `font-weight:normal; background-color:transparent;` 를 명시 — 네이버 sanitizer가 이전 헤딩 스타일을 본문 단락에 번지게 하는 버그를 막음.

**왜 native 소제목 컴포넌트를 안 쓰는가**: 네이버 SmartEditor의 paste 핸들러는 chromium의 `source-rfh-token` + 자체 `data-input-buffer` 토큰 둘 다 매칭돼야만 메모리에서 원본 컴포넌트를 복원합니다. 외부 매크로(터미널 Python AppKit)에서 만든 클립보드엔 이 토큰이 없으므로 어떤 SmartEditor 마크업을 박아도 **모두 본문 컴포넌트로 normalize됨**. 실측으로 정답 마크업을 한 자도 안 바꾸고 페이스트해도 본문 15px 볼드로 떨어짐을 확인. native 컴포넌트 inject는 in-process 자동화로만 가능 — 소제목은 시각 표시(노란 배경)로 충분해서 매크로 paste 를 유지.

**단, 코드블록은 in-process 주입이 됨** (2026-06-11 실측): osascript `execute javascript` (Chrome "Apple Events의 자바스크립트 허용" 필요)로 페이지 안에서 툴바 `button[data-name=code]` 를 클릭하면 에디터 자신의 핸들러가 정상 컴포넌트를 만들고, `.se-code-source-editor` textarea 에 native value setter + `input` 이벤트로 코드를 넣으면 모델이 수용함. 단 SE 는 합성(synthetic) paste/insertText 를 `isTrusted` 로 거부하므로, 캐럿 위치 잡기(트리플클릭)와 placeholder 삭제(Backspace)는 Quartz CGEvent 실제 입력으로 쏴야 함. 이 조합이 `_lib/inject_code_blocks.py` (Pass 2). 같은 원리로 소제목도 native 화 가능하지만 현재는 코드블록만 적용.

## 자동 footer 첨부

마이그레이션 시 글 맨 밑에 다음 형식의 footer가 자동으로 붙습니다.

```
해당 글은 티스토리 블로그 <원본 URL>의 글을 마이그레이션한 글입니다.

원본 작성일 : YYYY년 MM월 DD일

#전체태그1 #전체태그2 ... #전체태그25

#핵심태그1 #핵심태그2 ... #핵심태그12
```

- 원본 URL은 링크(`<a href>`)로 자동 변환
- 작성일은 Tistory `<meta property="article:published_time">` 태그에서 추출 (ISO 8601 → 한국어 날짜 포맷)
- `published_time` 메타가 없으면 작성일 줄은 생략됨
- 태그는 `--tags`로 넘긴 값이 우선이고, 생략하면 Tistory `<div class="tags"><a rel="tag">…</a></div>` 에서 추출. 다중 단어 태그(`젤다 사당 공략`)는 내부 공백을 제거해 단일 해시태그(`#젤다사당공략`)로 변환. **기본 흐름은 `--tags`로 새로 뽑아 넘기는 것**(위 "태그 새로 작성" 절 참고)
- **핵심 태그 줄은 `--core-tags`로 넘긴 값이고, 전체 세트 아래 빈 줄 하나를 띄워 따로 붙는다.**
  넘기지 않으면 그 줄이 통째로 빠진다. 클립보드 2블록과 짝이 맞아야 하므로 항상 같이 넘긴다
- **주의**: 이 해시태그는 본문 평문일 뿐 네이버의 진짜 태그(사이드바 태그 입력란)가 아님 — 검색·태그 페이지엔 안 잡히고 시각 표시만 함. 진짜 태그는 페이스트 종료 후 사용자가 직접 사이드바에 입력해야 함
- 구현: `scripts/migrate_from_url.py:_build_footer_html`, 태그 추출은 `fetch_post`

## 한계

- macOS 전용 (AppKit·NSPasteboard·osascript 의존)
- Tistory 외 다른 블로그 플랫폼은 지원 안 함 (셀렉터가 `.tt_article_useless_p_margin`, `.entry-content`, `<article>` 순)
- 동영상·iframe은 평문화될 가능성 (현재 스크립트 미대응)
- 코드블록 textarea 는 `maxlength=5000` — 5천 자 초과 코드는 잘림 (분할 필요)
- Pass 2 는 화면 좌표 기반 실제 클릭을 쓰므로 실행 중 다른 창을 띄우거나 입력하면 오작동
- 네이버 sanitizer 정책이 바뀌면 본문 스타일 번짐이 재발할 수 있음 — `paste_to_naver.py`의 `BODY_SPAN_STYLE`/`HEADING_SPAN_STYLE`을 같이 갱신할 것

## 의존 도구

2026-07-30에 외부 리포 `ParkGiraffe/tistory-to-naver-blog`를 이 리포로 흡수했다. 그 리포는 더 쓰지 않는다.

- `tistory-to-naver/scripts/` (변환 엔진)
  - `migrate.py` (원샷), `migrate_from_url.py` (fetch·변환·청크), `migrate_category.py` (카테고리 일괄),
    `run_migration.py` (레거시 단계별), `dump_categories.py` (카테고리 ID 덤프),
    `upload_draft.py` (로컬 초안 업로드)

### 글쓰기 탭 규칙 (2026-08-07 실측, 위반 시 매크로가 죽는다)

**항상 새 탭을 연다. 기존 탭을 닫지도, 비워서 재사용하지도 않는다.**

- **닫지 마라.** 작성 중인 글이 있는 postwrite 탭을 닫으면 beforeunload 네이티브 alert가 뜬다.
  네이티브 alert는 CGEvent 입력과 osascript JS를 전부 삼켜서, 붙여넣기가 허공으로 가고
  이후 모든 단계가 조용히 실패한다(붙였는데 문단 수가 그대로면 이 상황이다).
- **비우지 마라.** Cmd+A + Backspace로 지우고 재사용하면 SE가 캐럿에 남은 인라인 서식을
  유지해서, 다음 붙여넣기 때 소제목의 노란 배경이 본문 전체에 번진다
  (notion-to-naver/SKILL.md의 취소선 사고와 같은 원인).
- 임시저장 복원 다이얼로그는 **뜬 뒤에야 닫을 수 있다.** 새 탭 로딩 후 6초쯤 기다렸다가
  전체 `button` 중 텍스트가 `취소`이고 `offsetParent`가 있는 것을 클릭한다.
  `.se-canvas`가 준비되자마자 `.se-popup button`만 훑으면 아직 안 뜬 다이얼로그를 놓쳐
  임시저장이 복원된 채로 붙여넣게 된다. 복원됐으면 지우지 말고 중단한다.
- `_lib/` (리포 공용 에디터 매크로)
  - `inject_code_blocks.py` (Pass 2), `publish_with_category.py` (카테고리 지정 + 발행),
    `naver_inspect.py` (에디터 상태 조회, 디버깅용)
- 패키지: `requests`, `beautifulsoup4`, `pyobjc-framework-Cocoa`,
  `pyobjc-framework-Quartz` (Pass 2 CGEvent 용)

## 관련 스킬
- `/blog`: 네이버 블로그 새 글 자동 작성 + 페이스트 (`paste_to_naver.py` 정본 보유)
- `/blog-learn`: 네이버 블로그 코퍼스 학습
- `/naver-blog-tags`: `--tags`로 넘길 태그를 뽑는 절차
- `/js-lecture-publish`: 이 스킬의 `migrate.py` + `publish_with_category.py`를 4개씩 묶어 돌리는 배치
