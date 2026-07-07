---
name: notion-to-naver
description: Notion 페이지(지식창고 문서 등)를 네이버 블로그 "박기린의 기린파크"(op5321)로 전사·업로드한다. notion-fetch로 본문·이미지를 확보하고(S3 서명 URL 5분 만료라 즉시 다운로드), 창작 없이 ~입니다 체로만 변환하는 전사 모드로 script.md를 만든 뒤, blog 스킬의 검증된 파이프라인(md_to_smarteditor.py, paste_to_naver.py, inject_code_blocks.py)으로 SmartEditor에 자동 입력한다. 사용 시점 — 사용자가 Notion 페이지 URL을 주면서 "블로그로 옮겨줘", "네이버로 마이그레이션", "이 글 발행하고 싶어", "/notion-to-naver <URL>" 등을 말할 때 반드시 사용. 하드룰: 이모지 절대 금지, 고유명사 왜곡 금지, 개발 관련 글은 무조건 비공개로 발행, 무인 업로드 금지.
---

# notion-to-naver — Notion 글을 네이버 기린파크로 전사·업로드

Notion에 정리해 둔 글(버그수정 일지, 지식창고 문서 등)을 네이버 블로그로 옮기는 스킬.
창작이 아니라 **전사(transcription)**다 — 노트 구조·내용·이미지 위치를 그대로 유지하고 문장만 ~입니다 체로 다듬는다.

## 하드룰

- **개발 관련 글은 무조건 '비공개'로 발행한다** (2026-07-07 사용자 지시, 상시 규칙). 발행 직전 공개 범위가 비공개인지 사용자와 함께 확인. 개발 글 여부가 애매하면 물어본다.
- **전사 모드** (blog/SKILL.md와 동일): 새 소제목 창작·재구성·요약·확장 금지. 본문은 ~입니다 체 변환만. 이미지는 노트에 있던 위치 그대로. 노트에 없는 내용은 쓰지 않는다.
- **이모지 금지, 고유명사 왜곡 금지** (리포 공통).
- **무인 업로드 금지** (2026-06-16 사고 교훈). 사용자 입회 하에만 실행하고, 시작 전 "1~2분간 키보드·마우스를 건드리지 마세요" 고지. 매 단계 포커스(`document.hasFocus()`)·컴포넌트 수 증가를 검증하고 WARN이면 즉시 중단.
- **발행 버튼은 사용자가 직접 클릭** — 발행 자동화하지 않는다.
- **회사 정보 노출 점검**: 원문에 사내 프로젝트명·내부 UI 스크린샷이 있으면 발행 전 사용자에게 노출 여부를 확인시킨다 (비공개 발행이어도 고지).

## 사전 준비 (1회, blog 스킬과 동일)

- 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용에 터미널(또는 iTerm) 체크 (Cmd+V 자동 전송)
- Chrome 메뉴 바 → 보기 → 개발자 → "Apple Events의 자바스크립트 허용" 체크 (코드블록 inject용)
- 매크로 도구: `~/Desktop/Project/personal/tistory-to-naver-blog/` (inject_code_blocks.py)

## 절차

### 1. 소스 확보 — 이미지 만료 주의

1. `notion-fetch`로 페이지 조회 (Notion MCP). 본문 마크다운과 이미지 URL을 얻는다.
2. **이미지의 S3 서명 URL은 약 5분 만료** — fetch한 그 턴에서 즉시 curl로 전부 다운로드한다:
   ```bash
   curl -sL -o .claude/blog-corpus/drafts/<YYYY-MM-DD>-<slug>/images/01.png '<서명 URL>'
   ```
   시간이 지나 403이 나오면 notion-fetch를 다시 해서 새 URL로 재시도.

### 2. 전사 — script.md 작성

`.claude/blog-corpus/drafts/<YYYY-MM-DD>-<slug>/script.md`:

- frontmatter: `title`(가제), `category`(보류 가능), `date`
- 노트 구조·순서 그대로. 소제목은 노트에 있는 것만 (`##`).
- 본문은 ~입니다 체 변환만. 링크는 마크다운 링크로 유지.
- 이미지: `![](images/NN.png)` — 노트에 있던 위치 그대로.
- **코드블록**: 본문에는 `[[CODE-n]]` 한 줄짜리 placeholder 단락으로 넣고 (n은 1부터),
  코드 원문은 사이드카 `/tmp/naver_code_blocks.json`에 저장:
  ```json
  [{"index": 1, "code": "..."}, {"index": 2, "code": "..."}]
  ```
  코드는 5,000자 초과 시 잘리므로 (textarea maxlength) 분할한다.

### 3. HTML 생성·검수

```bash
python3 blog/scripts/md_to_smarteditor.py <drafts>/script.md <drafts>/post.html
grep -rP '[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]' <drafts>/   # 결과 비어야 함
```

md_to_smarteditor.py는 이모지가 있으면 exit 3 — 대본을 수정하고 재시도. preview를 로컬로 띄워 이미지 위치·여백을 눈으로 확인.

### 4. 메타 + 카테고리

- meta.json: 제목 후보 5개(기린파크 제목 컨벤션, blog-title 스킬 연계 가능) + 해시태그 + `images.source_folder`
- 카테고리는 실제 목록을 보고 결정: postwrite 발행 레이어의 카테고리 셀렉트박스를 열어 `data-testid^=categoryItem` 덤프로 확인 (tistory-to-naver/SKILL.md의 셀렉터 참조), 후보를 사용자에게 제시해 확정받는다.

### 5. 업로드 — osascript 오케스트레이션 (사용자 입회)

blog/SKILL.md 7-1 자동 흐름 그대로:

1. postwrite 탭 확보 (없으면 열기) + 임시저장 다이얼로그 JS로 취소
2. CGEvent로 본문 클릭해 포커스 확보 → 실행:
   ```bash
   python3 blog/scripts/paste_to_naver.py .claude/blog-corpus/drafts/<드래프트 폴더>
   ```
   (이미지는 meta.json `images.source_folder`에서 자동 로드, 파일 URL 클립보드 방식이라 네이버가 자동 업로드)
3. 코드블록 inject:
   ```bash
   python3 ~/Desktop/Project/personal/tistory-to-naver-blog/inject_code_blocks.py
   ```
   (기본 사이드카 경로 `/tmp/naver_code_blocks.json` 사용. 언어 표기는 기본 javascript — 다르면 에디터에서 수동 변경)
4. 제목 자동 입력 (pbcopy → 제목칸 클릭 → Cmd+V)

### 6. 발행 — 개발 글은 비공개

- 에디터 상태를 사용자와 함께 검토 (이미지 전부 업로드, 코드블록 se-code 렌더링, 제목)
- 발행 레이어에서 카테고리 지정 + **개발 글이면 공개 범위 '비공개' 선택 확인**
- **발행 버튼은 사용자가 직접 클릭**

### 7. 발행 후 검증

발행된 글을 모바일 UA로 받아 본문·이미지 누락을 확인한다:

```bash
curl -s -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)" "https://m.blog.naver.com/op5321/<logNo>" | grep -c "se-image"
```

(비공개 글은 로그인 세션이 없으면 안 보일 수 있음 — 그 경우 에디터/브라우저에서 눈 검수로 대체)

## 함정 / 주의

- **`document.hasFocus()`는 앱 전면 여부를 보장하지 않는다 (2026-07-07 카카오톡 사고).** 다른 앱이 전면이어도 true가 나올 수 있어, CGEvent 클릭·Cmd+V가 전부 그 앱(카카오톡 채팅창 등)으로 들어가는 사고가 났다. 입력을 쏘기 전 반드시 System Events로 전면 앱을 확인한다: `tell application "System Events" to get name of first application process whose frontmost is true` == "Google Chrome". 아니면 activate 후 재확인, 그래도 아니면 중단. 실행 후 카카오톡 등에 오염된 입력이 없는지 확인.
- **본문 클릭 성공을 `isContentEditable`로 판정하지 말 것.** SmartEditor는 자체 캐럿 모델이라 activeElement가 일반 contenteditable로 안 잡힌다. 검증된 프로토콜(migrate.py)은 "클릭 → paste → 컴포넌트 수 증가로 검증"이다. paste 후 `se-image` 수(=이미지 장수)와 `.se-text p` 수 증가를 확인하고, 0이면 중단.
- **탭 활성화·창 raise·좌표 측정·클릭은 한 프로세스에서 원자적으로.** 셸 호출을 쪼개면 사이에 창 순서가 바뀌어 좌표가 다른 창에 떨어진다.
- **마크다운 인라인 문법은 전체 라인 볼드(`**...**` 단독 라인)만 지원.** 문장 중간 부분 볼드·마크다운 링크(`[텍스트](URL)`)는 파서가 몰라 별표/대괄호가 그대로 찍힌다. 링크는 순수 URL 텍스트로 넣고 필요 시 에디터에서 수동으로 걸 것.
- **claude-in-chrome은 blog.naver.com을 하드블록** — 네이버 자동화는 osascript 경로만 ([[naver-automation-osascript-route]]).
- Notion S3 서명 URL 만료(5분) — fetch와 다운로드는 반드시 같은 턴에.
- 외부 클립보드로는 어떤 SmartEditor 마크업을 붙여도 본문 컴포넌트로 normalize됨 — 소제목은 시각 스타일(노란 배경 24px 볼드)로 충분, 코드블록만 inject_code_blocks.py로 native 주입 (원리는 tistory-to-naver/SKILL.md 참조).
- Pass 2(코드블록)는 좌표 기반 실제 클릭 — 실행 중 다른 창을 띄우면 오작동.
- 네이버 sanitizer 정책 변경 시 본문 스타일 번짐 재발 가능 — `paste_to_naver.py`의 스타일 상수와 함께 갱신.
- Notion 페이지에 데이터베이스·토글 등 복잡한 블록이 있으면 fetch 마크다운에서 뭉개질 수 있음 — 전사 전에 원문과 대조.

## 관련 스킬 / 의존

- `blog` — paste_to_naver.py·md_to_smarteditor.py 정본, 전사 모드·여백 규칙·osascript 오케스트레이션 상세
- `tistory-to-naver` — 코드블록 inject 원리, 발행 레이어 DOM 셀렉터, migrate 파이프라인
- `blog-title` — 제목 후보 뽑기
- 외부: `~/Desktop/Project/personal/tistory-to-naver-blog/` (inject_code_blocks.py)
