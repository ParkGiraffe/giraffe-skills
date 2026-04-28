---
name: blog
description: Generate a Naver blog draft (script + SmartEditor-compatible HTML + title candidates + hashtags + category) for the user's blog "박기린의 기린파크" (op5321), in the user's learned voice. Use when the user says "/blog <topic>", "블로그 글 써줘", "네이버 블로그 초안 만들어줘", or asks to draft/write a new blog post. Requires that /blog-learn has already populated ./.claude/blog-corpus/. NEVER use emojis anywhere in the output — the user explicitly forbids them in their writing.
---

# blog — 대본 + SmartEditor HTML 생성

주제 한 줄을 받아 박기린님의 학습된 말투로 블로그 초안을 만듭니다.

## 전제
- `./.claude/blog-corpus/posts/*.md`와 `style-guide.md`가 이미 존재해야 함. 없으면 먼저 `/blog-learn`을 돌리라고 안내.

## 입력
```
/blog "<주제>" [--category <이름>] [--images <폴더>] [--length short|normal|long]
```

예: `/blog "붉은사막 30화 루드빅 2차전 공략" --images ./shots/`

## 절차

### 1. 유사글 검색
```bash
python3 ~/.claude/skills/blog/scripts/find_similar.py .claude/blog-corpus "<주제>" [--category ...] --n 3
```
출력 JSON에서 상위 3편의 `path`를 읽어 few-shot 샘플로 사용.

### 2. 컨텍스트 수집
- `./.claude/blog-corpus/style-guide.md` 전체
- 위에서 찾은 유사글 3편의 `posts/*.md` 파일 내용
- 주제 문자열

### 3. 대본 작성
이 세 가지를 근거로 대본을 직접 작성. 작성 시:
- **이모지 절대 금지** (한 개도 쓰지 말 것)
- 블로그 정체성 유지: "닌텐도, 스팀, 모바일가챠 게임을 두루두루 사랑하는 개발자" 관점
- 스타일 가이드에 기록된 종결어미·호흡·단락 패턴을 그대로 따를 것
- 유사글 3편의 구성(도입-소제목-본론-마무리 흐름)을 참고하되 주제에 맞게 재구성
- 구조: `# {제목}` → 도입 1~2단락 → `---` 또는 `## {소제목}` 반복 → 마무리
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

**(d) 네이버 업로드 명령어 블록** — 사용자가 바로 복사해서 실행할 수 있도록 **실제 드래프트 경로를 박은 완전한 한 줄 명령**을 반드시 출력. 예:
```bash
python3 ~/.claude/skills/blog/scripts/paste_to_naver.py \
  .claude/blog-corpus/drafts/2026-04-14-pokopia-46-cubone-marowak
```
그리고 간단한 실행 절차 4줄:
1. 네이버 블로그 새글쓰기 창 열고 **본문 영역** 클릭
2. 위 명령어 실행 → 터미널에 제목 출력됨
3. 터미널의 제목을 복사해서 에디터 **제목칸**에 Cmd+V
4. 본문 영역 포커스 유지하면 3초 후 자동으로 본문 paste 시작

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

**실행 흐름**:
1. 네이버 블로그 새글쓰기 창 열기
2. 터미널에 출력된 제목을 **에디터 상단 제목칸**에 직접 Cmd+V
3. 본문 영역 클릭해서 커서 두기
4. 터미널에서 위 명령 실행 → 3초 카운트다운 → 네이버 창 포커스 유지 → 자동 paste
5. 완료 후 에디터에서 결과 확인

## 하드룰 (재확인)
- **이모지 금지**. script.md, post.html, title_candidates, hashtags — 어디에도 단 한 개도 쓰지 말 것.
- **`K-` 접두어 남용 금지.** `K-라노벨`, `K-포켓몬`, `K-게임`, `K-판타지` 같은 표현을 반복해서 쓰지 말 것. 한 포스트에 1번 이하. 대체 표현을 먼저 고민할 것.
- **섹션 제목(`##`)에 작은따옴표/큰따옴표 쓰지 말 것.** 제목은 짧고 명료하게. 예: (X) `## '이 집에? 정말 이사해도 되겠니?'`, (X) `## 텅구리 : 안녕, 만나서 반가워`, (O) `## 모두의 집으로 이사 제안`, (O) `## 탕구리와 텅구리, 나란히`. 대사/인용은 본문 안에서만 쓸 것.
- **섹션 제목 길이 제한**: 15자 내외로 간결하게. "그리고 마지막으로,", "자 그럼 이제" 같은 연결어 사용 금지. 핵심 키워드만.
- **중복 맥락 제거**: 도입부에서 이미 말한 내용을 첫 섹션에서 다시 말하지 말 것. 한 포스트 안에서 같은 펀치라인/관찰을 두 번 반복하지 말 것. 초안을 쓴 뒤 의미적 중복이 있는지 한 번 훑고 제거할 것.
- **원작/시리즈 레퍼런스 활용**: 게임 공략/도감 등록/캐릭터 소개 글에서, 해당 대상이 포켓몬 본가/닌텐도 원작/인터넷 밈 등에서 유명한 배경이 있다면 적극적으로 덧붙일 것 (별도 `##` 섹션 혹은 말미 참고로). 이건 가치 있는 컨텍스트이고 기린님 글에 깊이를 더함. 단, 확실치 않으면 추측하지 말고 생략할 것.
- **포코피아 등 포켓몬 계열 글에서 도감 설명을 다룰 때, 포켓몬 키(`키 1.0m`)와 몸무게(`몸무게 45kg`)는 쓰지 말 것.** 사용자가 키/몸무게엔 관심 없음을 명시. 도감 본문 설명, 타입, 분류(뼈다귀포켓몬 등)는 그대로 인용해도 무방.
- 공략/리뷰 글은 사실 왜곡 금지. 주제 한 줄에 내가 모르는 구체적 수치(스킬 데미지, 스탯값 등)가 포함돼 있으면 꾸며내지 말고 `[확인 필요: ...]`로 남기거나 사용자에게 반문할 것.
- 카테고리는 반드시 `index.json`에 이미 존재하는 것 중 하나. 새 카테고리 만들지 말 것.
