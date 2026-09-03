---
name: blog
description: Generate a Naver blog draft (script + SmartEditor-compatible HTML + title candidates + hashtags + category) for the user's blog "박기린의 기린파크" (op5321), in a clear analytical style (명료한 분석글, ~입니다 체) — NOT a mimicked personal voice. Use when the user says "/blog <topic>", "블로그 글 써줘", "네이버 블로그 초안 만들어줘", or asks to draft/write a new blog post. The blog corpus (/blog-learn) must NOT be used to imitate the user's writing voice; it is at most a reference for category names. NEVER use emojis anywhere in the output — the user explicitly forbids them in their writing.
---

# blog — 대본 + SmartEditor HTML 생성

주제 한 줄(또는 정리 노트)을 받아 **명료한 분석글(~입니다 체)**로 블로그 초안을 만듭니다.

## 보이스 규칙 (최우선)
- **코퍼스 말투 모방 금지.** 과거에 코퍼스로 사용자의 말투를 흉내냈으나, 애매하게 따라하면 안 쓰니만 못하다는 사용자 피드백(2026-06-16)으로 폐기. `style-guide.md`의 종결어미·호흡·말투 패턴은 더 이상 따르지 않음.
- **기본 보이스 = 명료한 분석글.** 군더더기 없는 설명체, 정보 전달 우선. 모든 문장은 **`~입니다`/`~합니다` 체로 통일** (구어체 종결어미·감탄사·이모티콘 금지).
- 사용자가 다른 톤을 명시하면 그 지시를 우선.

## 전사 모드 (사용자 노트 → 블로그) — 최우선 원칙

사용자가 이미 정리해둔 노트(Notion 페이지·문서 등)를 "블로그로 옮겨줘"라고 하면, 이것은 **창작이 아니라 전사(transcription)**다. 기본 요구는 "내가 적어놓은 걸 ~입니다 체로, 제목·구분선·사진을 내 원래 스타일대로 넣어서 에디터에 복붙"이다. 다음을 반드시 지킬 것 (2026-06-16 사용자 피드백: "너의 자아가 너무 강해. 글을 창작하라는 게 아니라 노션에 적어놓은 걸 옮겨달라는 거야").

- **노트의 섹션/세션 이름을 그대로 소제목으로 쓴다.** 임의로 새 소제목(예: "IndexedDB 임시저장")을 만들거나 순서를 재구성하지 말 것. 노트에 있는 소제목만 유지.
- **본문은 사용자가 쓴 내용을 `~입니다` 체로 변환만 한다.** 문장을 풀어 설명하거나 살을 붙이거나 배경 맥락을 창작하지 말 것. 노트에 없는 내용은 쓰지 않는다.
- **사진은 노트에 있던 위치 그대로** 넣는다. 임의로 빼거나 옮기지 말 것.
- 제목·구분선·사진 정렬은 사용자의 기존 스타일대로(노란 배경 24px 볼드 소제목, `<hr>` 구분선, 사진 가운데).
- **구조 결정(몇 편으로 나눌지·톤·범위)은 멋대로 하지 말고 사용자에게 묻거나 사용자 지시를 따른다.** 요청 없이 분할·요약·확장하지 말 것.
- 내용이 비어 있는 섹션(제목만 있는 경우)은 그 사실을 사용자에게 알리고 어떻게 할지 확인.

## 전제
- 코퍼스(`./.claude/blog-corpus/`)는 **필수 아님**. 있으면 카테고리명 참조용으로만 쓰고, **말투/문체 학습에는 절대 쓰지 않음**. 없어도 작성 진행.

## 입력
```
/blog "<주제>" [--category <이름>] [--images <폴더>] [--length short|normal|long]
```

예: `/blog "붉은사막 30화 루드빅 2차전 공략" --images ./shots/`

## 절차

### 1. 소스 수집
- 주제 문자열 또는 사용자가 정리해 둔 노트(Notion 페이지 등). 노트가 있으면 그 내용·사진·섹션 구분을 출처로 삼아 재구성.
- (선택) 카테고리명이 필요하면 `index.json`에서 실제 카테고리 목록만 확인. **코퍼스 본문/style-guide로 말투를 학습하지 않음.**

### 2. 대본 작성
명료한 분석글로 직접 작성. 작성 시:
- **이모지 절대 금지** (한 개도 쓰지 말 것)
- **모든 문장 `~입니다`/`~합니다` 체로 통일.** 구어체·감탄사·말끝 흐림 금지.
- 정보 전달과 논리적 흐름 우선. 한 섹션 = 한 주제. 불필요한 수식어·감상 군더더기 제거.
- 구조: `# {제목}` → 도입 1~2단락 → `---` 또는 `## {소제목}` 반복 → 마무리
- 이미지 자리는 `[스크린샷: 설명]` 또는 `![](경로)`로 마킹. `--images` 폴더가 있으면 파일명 힌트를 주고, 없으면 placeholder만.
- `--length`: short ≈ 600~800자, normal ≈ 1200~1800자, long ≈ 2500자+

결과를 `./.claude/blog-corpus/drafts/{YYYY-MM-DD}-{slug}/script.md`에 frontmatter(`title`, `category`, `date`) + 본문으로 저장.

### 3. SmartEditor HTML 생성
```bash
python3 ~/.claude/skills/blog/scripts/md_to_smarteditor.py \
  .claude/blog-corpus/drafts/.../script.md \
  .claude/blog-corpus/drafts/.../post.html \
  [--images <폴더>]
```
`md_to_smarteditor.py`는 이모지가 포함되면 exit 3으로 실패함. 실패하면 대본을 재생성하고 재시도.

### 4. 메타 생성
`./.claude/blog-corpus/drafts/.../meta.json`을 직접 작성:
```json
{
  "title_candidates": ["후보1", "후보2", ...5개],
  "hashtags": ["#태그1", ...],
  "category": "추천 카테고리",
  "length": "normal"
}
```
- 제목 후보 5개: 기린님 과거 제목 패턴(`[시리즈] N. 부제 / vs 보스`, `[게임명] 리뷰`, `[외식] 상호 방문기` 등) 참조
- 해시태그: 스타일 가이드에서 관측된 포스트당 평균 개수만큼. 이모지 없이.
- 카테고리: `index.json`에서 관찰된 실제 카테고리명 중 하나 선택

### 5. 자체 검수
```bash
grep -rP '[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]' .claude/blog-corpus/drafts/<dir>/
```
결과가 비어야 함. 비어있지 않으면 해당 파일을 수정하고 재검수.

이어서 `korean-writing` 스킬의 검증 패스를 돌린다. 규칙 정본과 판정법이 그 스킬에 있다.

```bash
python3 korean-writing/scripts/lint.py .claude/blog-corpus/drafts/<dir>/script.md
```

종료 코드가 0이 아니면 업로드하지 않는다. `고침` 갈래는 `--fix`로 반영하고, `검토`·`제목`
갈래는 사람이 판단해 고친 뒤 다시 돌린다. 대본이 300자 이상이면
`korean-writing/references/judgments.md` 끝의 지시문으로 적대적 검증 2단계까지 돌린다.

### 6. 사용자 보고 (필수 템플릿)

드래프트 작성을 마치면 **반드시** 아래 4가지를 사용자에게 출력해야 한다. 하나라도 빼먹지 말 것.

**(a) 산출 파일 경로** — `script.md`, `post.html`, `meta.json` 절대경로

**(b) 제목 후보 5개** — 추천 1개 굵게 + 나머지 4개

**(c) 해시태그 + 카테고리**

**(d) 네이버 업로드 안내** — **디폴트는 Claude가 직접 자동 업로드** (아래 7-1 osascript 오케스트레이션). "업로드해줘" 한 마디면 탭 열기부터 제목 입력까지 Claude가 전부 수행한다고 안내. 수동 실행을 원하는 경우를 위해 드래프트 경로를 박은 명령 한 줄도 같이 출력:
```bash
python3 ~/.claude/skills/blog/scripts/paste_to_naver.py \
  .claude/blog-corpus/drafts/2026-04-14-pokopia-46-cubone-marowak
```

**(e) 수정 가이드** — 수정 요청은 "수정: XX" 또는 "제목 다시 뽑아줘" 등 자연어로 받으면 drafts/ 같은 폴더에서 in-place 갱신한다고 안내

### 7. 네이버 업로드 매크로 (검증된 최종 워크플로)

`post.html`을 브라우저에서 Cmd+A/Cmd+C 하는 방식은 Naver가 `file://` 이미지를 거부해서 이미지가 안 붙음. **검증된 해결책**: `paste_to_naver.py` 매크로.

```bash
python3 ~/.claude/skills/blog/scripts/paste_to_naver.py \
  .claude/blog-corpus/drafts/{draft-folder}
```

(`--images` 플래그 생략 가능 — meta.json의 `images.source_folder`에서 자동 로드)

매크로 동작:
- script.md를 파싱해서 텍스트/이미지 chunk로 쪼갬
- 각 chunk를 순차적으로 macOS 클립보드에 올리고 Cmd+V 전송
- 텍스트: `public.html` 타입으로 HTML을 `NSPasteboard`에 씀
- 이미지: `NSURL.fileURLWithPath_` + `writeObjects_` — Finder에서 드래그한 파일과 동일하게 Naver가 자동 업로드
- Cmd+V는 `osascript key code 9 using command down` (raw keycode, IME 무관)

**검증된 HTML 스타일 (Naver 파싱 호환)**:
- `# 제목` 라인은 본문에서 제외하고 터미널에 출력 — 사용자가 에디터 상단 제목 입력칸에 직접 붙여넣음
- 섹션 헤딩(`##`): `<p><span style="font-size:24px;background-color:#fff593;"><b>텍스트</b></span></p>` + `<p><br></p>` barrier
- 본문(`<p>`): `<p><span style="font-size:15px;font-weight:normal;background-color:transparent;color:#212529;">텍스트</span></p>` — 명시적 reset으로 헤딩 스타일 상속 차단
- 구분선: `<hr>`
- 인라인 class(`se-fs-fs24` 등) 사용 금지 — Naver sanitizer가 제거함. 반드시 inline `style` 속성만 사용.

**사전 준비 (1회)**:
- `시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용`에 터미널(또는 iTerm) 체크 — Cmd+V 자동 전송 권한
- Chrome 메뉴 바 → 보기 → 개발자 → **"Apple Events의 자바스크립트 허용"** 체크 — osascript in-page JS 주입 권한

### 7-1. osascript 자동 오케스트레이션 (디폴트)

**네이버 블로그에 글을 쓰는 모든 경우, Claude가 osascript로 전 과정을 자동 수행하는 것이 디폴트.** 사용자에게 "창 열고 클릭하세요" 류의 수동 단계를 시키지 말 것. claude-in-chrome 확장은 `blog.naver.com`을 하드블록하므로 쓸 수 없음 — 반드시 osascript 경로.

핵심 기법 (2026-06-11 arnopark.tistory.com/903 마이그레이션으로 전 단계 실증):
- **탭 제어**: AppleScript로 postwrite 탭 탐색/열기·URL 이동. 탭 인덱스는 수시로 바뀌므로 매번 URL로 재탐색.
- **DOM 조작**: `execute tab N of window M javascript "..."`. 페이로드는 base64로 감싸 `eval(decodeURIComponent(escape(atob('...'))))` 형태로 전달 (이스케이프 지옥 회피, UTF-8 안전).
- **임시저장 다이얼로그**: 뜨면 JS로 `취소` 버튼 클릭해 닫음 (`.se-popup button`).
- **포커스·캐럿**: SmartEditor는 합성 이벤트를 isTrusted로 거부 — 실제 입력이 필요한 동작(본문 클릭, 선택, Backspace, Cmd+V)은 Quartz CGEvent로 쏨. 좌표는 JS로 `window.screenX + rect.left`, `window.screenY + (outerHeight - innerHeight) + rect.top` 계산. 클릭 전 `scrollIntoView({block:'center'})`.
- **제목 자동 입력**: 제목을 `pbcopy` → CGEvent로 제목칸 클릭 → Cmd+V. 터미널 출력 복붙 수동 단계 없음.
- **코드블록**: 본문에 placeholder를 남기고 리포 공용 `_lib/inject_code_blocks.py` 방식(툴바 `button[data-name=code]` JS 클릭 + `.se-code-source-editor` textarea native value setter + input 이벤트)으로 native `se-code` 컴포넌트 삽입.

> 새 탭 조준 방식이 리포에 둘 있다. `upload_to_editor.py`는 탭 id를 잡아 그 탭에만 JS를 쏘고,
> `tistory-to-naver/scripts/migrate_fresh_tab.py`는 chrome_js를 "마지막 postwrite 탭" 조준으로
> 바꿔치기한다. 목적은 같고, 탭 id 쪽이 탭 순서·창 이동에 안 흔들린다. 다만 tistory 경로는
> 이미 그 방식으로 검증돼 있어 손대지 않았다. 합칠 때는 실제 업로드로 확인하고 옮길 것.

**한 방에 올리기 (권장)**: 위 1~5단계를 한 프로세스로 묶은 오케스트레이터가 있다.
탭 확보·포커스 검증·제목·본문·여백/스타일 패스·결과 검증을 순서대로 하고, 각 단계에서
실패하면 즉시 멈춘다(사진 0장, 제목 미입력 등). 매번 손으로 조립하지 말 것:
```bash
python3 blog/scripts/upload_to_editor.py .claude/blog-corpus/drafts/<드래프트> [--clear]
```
`--clear`는 에디터에 이미 내용이 있을 때만 붙인다. 없으면 중단하는데, 사용자가 에디터에서
직접 고쳐 둔 원고를 덮어쓰지 않기 위해서다. 실제로 사용자가 도입부를 새로 써 넣은 뒤였다면
다시 올리는 순간 그 작업이 사라진다 — 재업로드 전에 반드시 확인할 것.

**자동 실행 흐름** (사용자 액션 0회):
1. Claude: postwrite 탭 확보 (없으면 열기) + 임시저장 다이얼로그 JS로 취소
2. Claude: CGEvent로 본문 클릭해 포커스 확보 → `paste_to_naver.py` 실행 (3초 카운트다운은 자동으로 지나감)
3. Claude: 코드블록 있으면 inject 패스 실행
4. Claude: 제목 자동 입력 (pbcopy + 제목칸 클릭 + Cmd+V)
5. 사용자: 결과 검토 후 **발행 버튼만 직접 클릭** (발행은 자동화하지 않음)

실행 중 키보드·마우스를 건드리지 말라고 사용자에게 사전 고지할 것. 좌표 기반 실제 클릭이라 다른 창이 덮으면 오작동.

## 하드룰 (재확인)
- **사진 먼저, 설명글은 사진 아래 (2026-06-16 사용자 명시: "난 항상 사진을 먼저 올리고 밑에 사진과 관련된 글을 적는 주의야").** 노트가 "글 → 사진" 순이어도, 옮길 때 **사진을 그 설명글 위로 올려** 사진-먼저로 만들 것 (caption-after). 사진과 바로 아래 설명글은 딱 붙이고, **[사진+설명글] 블록 뒤에 4줄**.
- **여백 규칙 (평소 스타일).** 빽빽하게 붙이지 말 것. 세션 제목(`##`) 위 7줄(구분선이 있으면 그 7줄은 구분선 '위'에, 구분선↔제목은 딱 붙임), 소제목(`###`) 위 3줄(단 세션 제목 바로 밑 첫 소제목은 1줄), 소제목↔바로 밑 사진은 딱 붙임, 사진↔설명글 딱 붙임, [사진+설명글] 뒤 8줄, 연속 본문 문단 사이 1줄. `paste_to_naver.py`가 토큰 기반으로 `<p><br></p>` 자동 삽입(`SPACE_BEFORE_SESSION=7 / SPACE_BEFORE_SUB=3 / SPACE_AFTER_TEXT=8, 2026-09-03 발행 글 실측값으로 조정`). 업로드 전 `preview.html`(로컬 http로 띄워 크롬 스크린샷)로 눈 확인 필수.
- **동영상은 클립보드로 안 붙는다.** 사진과 달리 네이버 자체 업로더를 거쳐야 한다.
  대본에 `[영상 자리 : 파일명.mp4]` 한 줄로 자리를 잡고 meta.json에 `videos_folder`를 넣어 두면
  `upload_to_editor.py`가 본문을 올린 뒤 그 자리를 실제 동영상으로 바꾼다(자리 문단을 통째로
  선택해 지워 빈 문단에 캐럿을 남기고 업로더를 부르는 방식 — 동영상은 캐럿 위치에 들어간다).
  한 개만 따로 넣을 때는 `_lib/upload_video.py <파일> [제목]`.
  제목은 meta.json `videos[].title`에 적으면 그걸 쓰고, 없으면 파일명에서 슬롯 접두어를 뗀다.
- **사진 워터마크**는 `_lib/watermark.py <입력폴더> <출력폴더>` (리포 정본).
  우하단 도현체 워터마크를 이미지 폭 비율로 넣는다. 네이버가 본문 사진을 폭 966px로
  줄여 보여주므로, 원본 크기가 제각각이어도 발행 후 같은 크기로 보인다.
  상수는 사용자 확정값이라 `--scale`은 보통 건드리지 않는다.
  마이그레이션처럼 내려받은 파일을 제자리에서 처리할 때는 `add_watermark(path)`를 부른다.
- **네이버 자동 업로드는 무인으로 돌리지 말 것 (2026-06-16 대형 사고).** 제목 입력이 실패(WARN)하면 즉시 중단. 매 단계 포커스(`document.hasFocus()`)와 컴포넌트 수 증가를 검증하고, 실패 시 계속 쏘지 말 것(포커스 풀린 채 허공/엉뚱한 곳에 붙여넣기 사고). 147장처럼 큰 글은 특히 사용자 입회 하에, 명시적 "올려" 지시가 있을 때만.
- **사용자 노트를 옮기는 작업은 전사다 (위 "전사 모드" 참조).** 노트의 소제목을 그대로 쓰고, 내용은 ~입니다 체 변환만, 사진은 제자리에. 새 소제목 창작·재구성·요약·확장·임의 분할 금지.
- **코퍼스 말투 모방 금지 / 기본 보이스 = 명료한 분석글, 전 문장 `~입니다` 체.** (2026-06-16 사용자 지시: "애매하게 따라하면 안 쓰니만 못하더라.") style-guide의 말투 패턴을 따르지 말 것.
- **이모지 금지**. script.md, post.html, title_candidates, hashtags — 어디에도 단 한 개도 쓰지 말 것.
- **`K-` 접두어 남용 금지.** `K-라노벨`, `K-포켓몬`, `K-게임`, `K-판타지` 같은 표현을 반복해서 쓰지 말 것. 한 포스트에 1번 이하. 대체 표현을 먼저 고민할 것.
- **섹션 제목(`##`)에 작은따옴표/큰따옴표 쓰지 말 것.** 제목은 짧고 명료하게. 예: (X) `## '이 집에? 정말 이사해도 되겠니?'`, (X) `## 텅구리 : 안녕, 만나서 반가워`, (O) `## 모두의 집으로 이사 제안`, (O) `## 탕구리와 텅구리, 나란히`. 대사/인용은 본문 안에서만 쓸 것.
- **섹션 제목 길이 제한**: 15자 내외로 간결하게. "그리고 마지막으로,", "자 그럼 이제" 같은 연결어 사용 금지. 핵심 키워드만.
- **중복 맥락 제거**: 도입부에서 이미 말한 내용을 첫 섹션에서 다시 말하지 말 것. 한 포스트 안에서 같은 펀치라인/관찰을 두 번 반복하지 말 것. 초안을 쓴 뒤 의미적 중복이 있는지 한 번 훑고 제거할 것.
- **원작/시리즈 레퍼런스 활용**: 게임 공략/도감 등록/캐릭터 소개 글에서, 해당 대상이 포켓몬 본가/닌텐도 원작/인터넷 밈 등에서 유명한 배경이 있다면 적극적으로 덧붙일 것 (별도 `##` 섹션 혹은 말미 참고로). 이건 가치 있는 컨텍스트이고 기린님 글에 깊이를 더함. 단, 확실치 않으면 추측하지 말고 생략할 것.
- **포코피아 등 포켓몬 계열 글에서 도감 설명을 다룰 때, 포켓몬 키(`키 1.0m`)와 몸무게(`몸무게 45kg`)는 쓰지 말 것.** 사용자가 키/몸무게엔 관심 없음을 명시. 도감 본문 설명, 타입, 분류(뼈다귀포켓몬 등)는 그대로 인용해도 무방.
- 공략/리뷰 글은 사실 왜곡 금지. 주제 한 줄에 내가 모르는 구체적 수치(스킬 데미지, 스탯값 등)가 포함돼 있으면 꾸며내지 말고 `[확인 필요: ...]`로 남기거나 사용자에게 반문할 것.
- 카테고리는 반드시 `index.json`에 이미 존재하는 것 중 하나. 새 카테고리 만들지 말 것.

## 게임 스토리 연재 (스위치 캡처 사진·영상 파이프라인)

스토리 게임을 미션 단위로 연재할 때 씁니다. 2026-09-03 젤다무쌍 봉인전기 18편 설계에서
확정한 절차이며, 사진 1,100장과 클립 103개를 기준으로 검증했습니다.

규칙 요약:
- 캡션은 상황 서술만 씁니다. 사진에 보이는 대사를 다시 적지 않고 낫표 인용을 쓰지 않습니다.
  클리어 타임 같은 결과 화면 수치도 쓰지 않습니다. 캡션은 반드시 마침표로 끝냅니다.
- 결과 화면, 챕터 메뉴, 배틀 챌린지 사진은 뺍니다. 튜토리얼 팝업은 첫 편에 두세 장만 둡니다.
- 같은 구도에 자막만 바뀌는 연속 컷은 첫 장을 원본으로 두고 나머지 자막 띠를 세로로 이어
  붙인 합성 이미지 한 장으로 줄입니다. 강적에 전투 영상이 있으면 전투 사진은 이름 카드와
  액션 한 장으로 줄입니다.
- 영상은 강적마다 전투 모션 하나를 원칙으로 두고, 편당 1~3개, 60초 안팎입니다.

영상 (`_lib/switch_clips.py`):
1. `switch_clips.py scan <원본 폴더> --out <작업 폴더>`: 클립을 촬영 건으로 묶어 `sessions.json`.
   스위치 30초 제한으로 쪼개진 클립은 틈 3초 이내면 같은 촬영입니다.
2. `switch_clips.py strips <작업 폴더> --session S51`: 1초 간격 프레임 띠. 앞뒤 자를 초를 정합니다.
3. `videos.json`에 `{"episode", "slot", "title", "sessions", "in", "out"}`를 적고
   `switch_clips.py render <작업 폴더> videos.json --out <초안>/images --episode N`.
   자르기가 없으면 무손실 병합, 있으면 재인코딩입니다. `videos_meta.json`이 함께 나옵니다.

사진 (`_lib/story_frames.py`):
1. `story_frames.py scan <편 폴더> --out <작업 폴더> --originals <원본 폴더>`: 유형 추정과
   같은 구도 묶기로 `plan.json`. 손 크롭본은 원본으로 되돌립니다.
   `plan.json`이 이미 있으면 멈추며 `--force`를 줘야 덮어씁니다.
2. `story_frames.py sheet <작업 폴더>`: 콘택트 시트를 눈으로 보고 `plan.json`을 고칩니다.
   틀린 묶음을 풀고, 뺄 사진을 `skip`으로, 팝업을 `crop`으로, 영상 자리를 `video`로,
   장면 전환을 `heading`으로 적습니다. 이 단계를 건너뛰지 않습니다.
3. `story_frames.py render <작업 폴더> --out <초안> --title "<제목>" --category-no N`:
   `images/`, `script.md` 뼈대, `meta.json`. 워터마크까지 들어갑니다.
   초안 폴더에 `script.md`가 이미 있으면 멈추므로 캡션을 쓴 뒤에는 다른 폴더로
   내보내거나 `--force`를 씁니다.
4. `script.md`의 `<!-- 도입 -->`과 `<!-- 캡션 -->`을 채운 뒤
   `story_frames.py check script.md`와 `korean-writing/scripts/lint.py script.md`를 통과시킵니다.
5. 업로드는 평소대로 `blog/scripts/upload_to_editor.py <초안>`입니다. `meta.json`의
   `videos_folder`와 `videos[]`를 이 파이프라인이 미리 채워 둡니다.
