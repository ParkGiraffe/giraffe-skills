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
- (이하 단계 번호는 기존 4~8을 그대로 따른다. SmartEditor HTML/메타/업로드 절차는 변경 없음.)
- 이미지 자리는 `[스크린샷: 설명]` 또는 `![](경로)`로 마킹. `--images` 폴더가 있으면 파일명 힌트를 주고, 없으면 placeholder만.
- `--length`: short ≈ 600~800자, normal ≈ 1200~1800자, long ≈ 2500자+

결과를 `./.claude/blog-corpus/drafts/{YYYY-MM-DD}-{slug}/script.md`에 frontmatter(`title`, `category`, `date`) + 본문으로 저장.

### 4. SmartEditor HTML 생성
```bash
python3 ~/.claude/skills/blog/scripts/md_to_smarteditor.py \
  .claude/blog-corpus/drafts/.../script.md \
  .claude/blog-corpus/drafts/.../post.html \
  [--images <폴더>]
```
`md_to_smarteditor.py`는 이모지가 포함되면 exit 3으로 실패함. 실패하면 대본을 재생성하고 재시도.

### 5. 메타 생성
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

### 6. 자체 검수
```bash
grep -rP '[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]' .claude/blog-corpus/drafts/<dir>/
```
결과가 비어야 함. 비어있지 않으면 해당 파일을 수정하고 재검수.

### 7. 사용자 보고 (필수 템플릿)

드래프트 작성을 마치면 **반드시** 아래 4가지를 사용자에게 출력해야 한다. 하나라도 빼먹지 말 것.

**(a) 산출 파일 경로** — `script.md`, `post.html`, `meta.json` 절대경로

**(b) 제목 후보 5개** — 추천 1개 굵게 + 나머지 4개

**(c) 해시태그 + 카테고리**

**(d) 네이버 업로드 안내** — **디폴트는 Claude가 직접 자동 업로드** (아래 8-1 osascript 오케스트레이션). "업로드해줘" 한 마디면 탭 열기부터 제목 입력까지 Claude가 전부 수행한다고 안내. 수동 실행을 원하는 경우를 위해 드래프트 경로를 박은 명령 한 줄도 같이 출력:
```bash
python3 ~/.claude/skills/blog/scripts/paste_to_naver.py \
  .claude/blog-corpus/drafts/2026-04-14-pokopia-46-cubone-marowak
```

**(e) 수정 가이드** — 수정 요청은 "수정: XX" 또는 "제목 다시 뽑아줘" 등 자연어로 받으면 drafts/ 같은 폴더에서 in-place 갱신한다고 안내

### 8. 네이버 업로드 매크로 (검증된 최종 워크플로)

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

### 8-1. osascript 자동 오케스트레이션 (디폴트)

**네이버 블로그에 글을 쓰는 모든 경우, Claude가 osascript로 전 과정을 자동 수행하는 것이 디폴트.** 사용자에게 "창 열고 클릭하세요" 류의 수동 단계를 시키지 말 것. claude-in-chrome 확장은 `blog.naver.com`을 하드블록하므로 쓸 수 없음 — 반드시 osascript 경로.

핵심 기법 (2026-06-11 arnopark.tistory.com/903 마이그레이션으로 전 단계 실증):
- **탭 제어**: AppleScript로 postwrite 탭 탐색/열기·URL 이동. 탭 인덱스는 수시로 바뀌므로 매번 URL로 재탐색.
- **DOM 조작**: `execute tab N of window M javascript "..."`. 페이로드는 base64로 감싸 `eval(decodeURIComponent(escape(atob('...'))))` 형태로 전달 (이스케이프 지옥 회피, UTF-8 안전).
- **임시저장 다이얼로그**: 뜨면 JS로 `취소` 버튼 클릭해 닫음 (`.se-popup button`).
- **포커스·캐럿**: SmartEditor는 합성 이벤트를 isTrusted로 거부 — 실제 입력이 필요한 동작(본문 클릭, 선택, Backspace, Cmd+V)은 Quartz CGEvent로 쏨. 좌표는 JS로 `window.screenX + rect.left`, `window.screenY + (outerHeight - innerHeight) + rect.top` 계산. 클릭 전 `scrollIntoView({block:'center'})`.
- **제목 자동 입력**: 제목을 `pbcopy` → CGEvent로 제목칸 클릭 → Cmd+V. 터미널 출력 복붙 수동 단계 없음.
- **코드블록**: 본문에 placeholder를 남기고 `~/Desktop/Project/personal/tistory-to-naver-blog/inject_code_blocks.py` 방식(툴바 `button[data-name=code]` JS 클릭 + `.se-code-source-editor` textarea native value setter + input 이벤트)으로 native `se-code` 컴포넌트 삽입.

**자동 실행 흐름** (사용자 액션 0회):
1. Claude: postwrite 탭 확보 (없으면 열기) + 임시저장 다이얼로그 JS로 취소
2. Claude: CGEvent로 본문 클릭해 포커스 확보 → `paste_to_naver.py` 실행 (3초 카운트다운은 자동으로 지나감)
3. Claude: 코드블록 있으면 inject 패스 실행
4. Claude: 제목 자동 입력 (pbcopy + 제목칸 클릭 + Cmd+V)
5. 사용자: 결과 검토 후 **발행 버튼만 직접 클릭** (발행은 자동화하지 않음)

실행 중 키보드·마우스를 건드리지 말라고 사용자에게 사전 고지할 것. 좌표 기반 실제 클릭이라 다른 창이 덮으면 오작동.

## 하드룰 (재확인)
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
