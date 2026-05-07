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

## 실행 절차

1. 사용자에게 네이버 글쓰기 페이지 열고 본문 영역 클릭하라고 안내:
   ```
   https://blog.naver.com/<userid>/postwrite
   ```

2. 사용자 확인 후 다음 명령 실행:
   ```bash
   cd ~/Desktop/Project/personal/tistory-to-naver-blog
   printf "1\n\n" | python3 run_migration.py '<TISTORY_URL>'
   ```
   - `printf "1\n\n"` → Auto 모드 자동 선택 + 종료 시 Enter
   - 3초 카운트다운 후 자동 페이스트 시작

3. 사용자에게 "3초 안에 네이버 창으로 포커스 옮기세요" 라고 안내

4. 페이스트 종료 후 사용자가 에디터에서 결과 확인

## 변환 규칙 (`migrate_from_url.py:split_content_into_chunks`)

`giraffe-skills/blog/scripts/paste_to_naver.py`와 동일한 SmartEditor 호환 HTML을 생성합니다 (시각적으로 `/blog` 스킬 결과물과 일치).

| Tistory 마크업 | 네이버 SmartEditor HTML |
|---|---|
| `<h1>` ~ `<h6>` (속에 `<span style="background-color:...">` 있어도 됨) | **네이버 native 소제목 컴포넌트** — `<div class="se-component se-sectionTitle">…<span class="se-ff-nanumgothic se-fs30" style="font-size:30px;font-family:'Nanum Gothic',나눔고딕,sans-serif;color:#000000;"><b>텍스트</b></span>…</div>` + `<p><br></p>` barrier. 네이버 paste 핸들러가 `se-sectionTitle` class를 인식해 native 컴포넌트로 승격 (실측 확인). 만에 하나 sanitizer가 wrapper를 벗기더라도 inner span의 inline style 덕에 30px 검정 볼드로 시각 fallback. |
| `<hr data-ke-type="horizontalRule">` | `<hr>` (네이버가 자동으로 SmartEditor hr 블록으로 승격) |
| 일반 본문 `<p>`/`<div>` | `<p><span style="font-size:15px;font-weight:normal;background-color:transparent;color:#212529;">텍스트</span></p>` (헤딩 스타일 번짐 차단용 명시적 reset) |
| `<p>&nbsp;</p>` 빈 줄 | `<p><br></p>` barrier |
| `<img>` (Tistory CDN URL) | 로컬로 다운로드 후 별도 청크로 분리 → 클립보드에 파일 URL로 올려 페이스트 (네이버가 자동 업로드) |

핵심 트릭: 본문 청크엔 항상 `font-weight:normal; background-color:transparent;` 를 명시 — 네이버 sanitizer가 이전 헤딩 스타일을 본문 단락에 번지게 하는 버그를 막음.

**`/blog` 스킬과의 차이**: `/blog` 스킬(새 글 자동 작성)은 헤딩에 노란 배경(`#fff593`) + 24px 볼드를 사용 (사용자 시그니처 스타일). 이 스킬(기존 글 마이그레이션)은 native 30px 검정 볼드 소제목을 사용 — Tistory 원문이 이미 native 섹션 헤딩 구조(`<h2>`)를 갖고 있으므로 그 시멘틱을 그대로 보존.

## 자동 footer 첨부

마이그레이션 시 글 맨 밑에 다음 형식의 footer가 자동으로 붙습니다.

```
해당 글은 티스토리 블로그 <원본 URL>의 글을 마이그레이션한 글입니다.

원본 작성일 : YYYY년 MM월 DD일
```

- 원본 URL은 링크(`<a href>`)로 자동 변환
- 작성일은 Tistory `<meta property="article:published_time">` 태그에서 추출 (ISO 8601 → 한국어 날짜 포맷)
- `published_time` 메타가 없으면 작성일 줄은 생략됨
- 구현: `migrate_from_url.py:_build_footer_html`

## 한계

- macOS 전용 (AppKit·NSPasteboard·osascript 의존)
- Tistory 외 다른 블로그 플랫폼은 지원 안 함 (셀렉터가 `.tt_article_useless_p_margin`, `.entry-content`, `<article>` 순)
- 동영상·iframe·코드블록은 평문화될 가능성 (현재 스크립트 미대응)
- 네이버 sanitizer 정책이 바뀌면 본문 스타일 번짐이 재발할 수 있음 — `paste_to_naver.py`의 `BODY_SPAN_STYLE`/`HEADING_SPAN_STYLE`을 같이 갱신할 것

## 의존 도구
- `ParkGiraffe/tistory-to-naver-blog` (외부 리포)
  - `run_migration.py`, `migrate_from_url.py`
  - 패키지: `requests`, `beautifulsoup4`, `pyobjc-framework-Cocoa` (스크립트가 자동 설치)

## 관련 스킬
- `/blog` — 네이버 블로그 새 글 자동 작성 + 페이스트 (`paste_to_naver.py` 정본 보유)
- `/blog-learn` — 네이버 블로그 코퍼스 학습
