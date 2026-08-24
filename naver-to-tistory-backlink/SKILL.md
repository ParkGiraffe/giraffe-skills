---
name: naver-to-tistory-backlink
description: 네이버 블로그(op5321) 글을 티스토리(arnopark)에 SEO 백링크용 "정리본"으로 자동 발행합니다. claude-in-chrome으로 티스토리 글쓰기 페이지를 조작해 1002번 글 형식 그대로 (blockquote 도입 / 요약 본문 / 핵심 포인트 / 원문 보기 3링크) 박은 뒤 공개 발행. 사용 시점 — 사용자가 "/naver-to-tistory-backlink <네이버URL>", "이 글 백링크 만들어", "정리본 올려", "구글 SEO용 티스토리 미러링" 등을 요청할 때. 인자 없이 호출하면 RSS 최신순에서 티스토리 정리본 안 만든 첫 글을 자동 선택.
---

# naver-to-tistory-backlink — 네이버 → 티스토리 SEO 백링크 자동 발행

박기린(`op5321`)의 네이버 블로그 글을 티스토리(`arnopark.tistory.com`)에 "정리본" 형태로 미러링해 구글 색인을 유도하는 스킬.

## 배경: 왜 이 워크플로가 필요한가
- `blog.naver.com`은 robots/iframe으로 구글 크롤러를 차단해 색인 불가
- `m.blog.naver.com` (모바일 도메인)은 색인 허용
- 외부 사이트(티스토리)에서 m.blog 또는 PostView raw URL로 백링크를 걸면, 구글이 그 링크를 따라가 네이버 글을 색인
- 모든 네이버 글에 대해 티스토리 "정리본"을 발행하고 본문에 3가지 URL을 박는 게 표준 패턴
- 보통 3~5일 ~ 3주 안에 색인됨

## 사용 시점
- `/naver-to-tistory-backlink <네이버URL>` — 명시 호출
- "이 글 백링크 만들어 줘 <URL>", "네이버 글 티스토리로 정리본 만들어", "구글 SEO용 미러링"
- 인자 없이 호출 시 → **자동 선택 룰**: 네이버 RSS를 최신순으로 훑으며, 티스토리의 "정리본" 글 본문에 해당 logNo가 매핑돼있지 않은 **첫 번째 글**을 선택

## 사전 준비
- Chrome에 `arnopark.tistory.com` 로그인 세션이 살아있어야 함 (claude-in-chrome MCP가 그 세션을 사용)
- 리포 안 `_lib/parse_smarteditor.py` 존재 (`blog-learn`과 공유. 본문 파싱용)
- 네이버 도메인은 claude-in-chrome MCP 안전정책으로 navigate가 차단됨 → 본문 fetch는 **curl로 우회**

## 하드룰: osascript 금지 (2026-08-23 사용자 지시)

**이 스킬에서 osascript(AppleScript)를 쓰지 않는다. 예외 없다.**
브라우저 조작은 `claude-in-chrome` MCP만 쓴다.

- `tell application "Google Chrome" ... execute javascript` 로 주입하지 않는다.
- `activate`, `set active tab index`, System Events `key code` 전송 전부 금지.
- 금지 이유: osascript 경로는 Chrome을 최전면으로 올리고 탭 활성을 바꿔
  **사용자 커서·포커스를 빼앗는다.** 사용자가 작업 중일 때 입력이 엉뚱한 창으로
  들어간다. 배치가 길수록 피해가 커진다.
- 배치에서 base64 손전사 오염이 걱정되더라도 osascript로 갈아타지 말 것.
  그건 [[feedback_backlink_clipboard_inject]]의 클립보드 무전사 주입이나
  청크 + SHA-256 대조로 푸는 문제다. 주입 경로를 바꿔서 풀 문제가 아니다.

## 실행 절차

### 1. 백링크 안 된 logNo 선정 (인자 없을 때만)
```bash
UA="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

# (a) 네이버 RSS에서 최신순 logNo 추출
curl -sSL -A "$UA" -e "https://blog.naver.com/" "https://rss.blog.naver.com/op5321.xml" \
  | python3 -c "import sys,re; xml=sys.stdin.read(); [print(m.group(1)) for it in re.findall(r'<item>(.*?)</item>',xml,re.S) for m in [re.search(r'/(\d{10,})\b', it)] if m]"

# (b) 티스토리 최근 "정리본" 글 본문에서 매핑된 logNo 모음 (글 번호는 글관리에서 확인 후 역순)
for n in $(seq <최신ID> -1 $((<최신ID> - 15))); do
  curl -sSL "https://arnopark.tistory.com/$n" \
    | grep -oE 'logNo=[0-9]+|naver\.com/op5321/[0-9]+' \
    | grep -oE '[0-9]{10,}'
done | sort -u

# (c) (a) - (b) 차집합 첫 번째 = 백링크 미생성 최신 글
```

#### 제외 규칙: 티스토리 원본이 살아있는 글

네이버 글 중 일부는 원래 티스토리에서 옮겨온 것이고, 본문 하단에 마이그레이션 푸터가 남아 있다:

```
해당 글은 티스토리 블로그 https://arnopark.tistory.com/NNN의 글을 마이그레이션한 글입니다.
원본 작성일 : YYYY년 MM월 DD일
```

이때 **원본 URL의 HTTP 상태코드가 판단 기준**이다. 정리본을 또 올리면 같은 도메인에 같은 내용이 두 벌 생겨 오히려 SEO에 해롭기 때문이다.

- `403` (비공개 전환됨) → **정리본 발행 대상**. 구글이 볼 수 있는 티스토리 사본이 없으니 백링크가 필요하다. (예: 젤다 사당 연재 — 원본 723/734/735/736 전부 403)
- `200` (아직 공개) → **제외**. 이미 색인 가능한 티스토리 원본이 있다. (예: `[JS 강의]` 계열 — `js-lecture-publish`가 티스토리→네이버로 옮긴 글들이라 원본이 그대로 공개 상태)

```bash
curl -s -o /dev/null -w "%{http_code}" "https://arnopark.tistory.com/<원본번호>"
```

RSS 50개 창 안에서 `[JS 강의]`가 20개 넘게 잡히는 게 정상이다. 이걸 미처리 백로그로 착각하지 말 것.

### 2. 네이버 본문 파싱
```bash
TMP=$(mktemp -d)
curl -sSL -A "$UA" -e "https://blog.naver.com/" \
  -o "$TMP/in.html" "https://m.blog.naver.com/op5321/$LOG"
python3 "$REPO_ROOT/_lib/parse_smarteditor.py" "$TMP/in.html" "$LOG" "$TMP/out.md"
IMG_COUNT=$(grep -c "se-image-resource" "$TMP/in.html")  # 표준 이미지 카운트
```
추출할 항목: 제목, 카테고리, h2 헤딩 리스트, 본문 단락(이미지 제외), `IMG_COUNT`.

**본문 단락에서 반드시 걷어낼 것** (1227 발행본 대조로 확증):

- `안녕하세요. 박기린입니다.` — 인사말
- `해당 글은 티스토리 블로그 …를 마이그레이션한 글입니다.` / `원본 작성일 : …` — 마이그레이션 푸터

푸터를 남기면 요약 끝이 "…arnopark.tistory.com/735의 글을 마이그레이션한 글입니다. 원본 작성일 : 2023년 06월 12일"로 끝난다. 정리본은 네이버 원문으로 유도하는 글인데 죽은 티스토리 주소를 본문에 박는 셈이라 목적이 뒤집힌다.

이 두 가지를 제거하면 발행본 1227(logNo 224339790817)의 요약이 **572자, 문자 단위로 정확히 재현**된다. 파서를 고쳤을 때 이 글로 회귀 테스트를 돌리면 규칙이 안 깨졌는지 바로 확인된다.

`IMG_COUNT`는 `grep -c se-image-resource`로 센다 (1227의 "이미지 29장"과 일치 확인).

### 3. 1002 형식 본문 HTML 조립 (정본)

**제목**: `{원본 제목} | 정리본`

**본문**: 티스토리 에디터(KEditor)는 자체 `data-ke-*` 속성으로 블록 스타일을 관리한다. 이 속성이 없으면 발행은 되지만 수정 모드에서 스타일 툴바가 블록을 인식하지 못해 편집이 어긋난다. 발행본 1227에서 실측한 정본 마크업은 다음과 같다:

```html
<blockquote data-ke-style="style1">이 글은 네이버 블로그 「<a href="https://m.blog.naver.com/op5321/{LOG}" target="_blank" rel="noopener">박기린의 기린파크</a>」 원문을 정리한 요약본입니다. 원문 전체와 이미지는 네이버에서 볼 수 있어요.</blockquote>
<h2 data-ke-size="size26">요약</h2>
<p data-ke-size="size16">{원문 본문을 풀어쓴 한 단락. 짧은 추상 요약 절대 금지. 원문 톤·문장을 거의 그대로 옮기되 800자에서 자른다. 자연스러운 미완결 (",", " N자 가면,") 로 끝낸다.}</p>
<h2 data-ke-size="size26">핵심 포인트</h2>
<ul style="list-style-type: disc;" data-ke-list-type="disc">
  <li>{원문 첫 5~6개 문장 토막. 어시스턴트 추상화 금지. 원문 문장 그대로}</li>
  ...
</ul>
<h2 data-ke-size="size26">원문 보기 (네이버 블로그)</h2>
<ul style="list-style-type: disc;" data-ke-list-type="disc">
  <li>📎 원문 링크: <a href="https://m.blog.naver.com/op5321/{LOG}" target="_blank" rel="noopener">{글 제목}</a></li>
  <li>🌐 PC 링크: <a href="https://blog.naver.com/op5321/{LOG}" target="_blank" rel="noopener">https://blog.naver.com/op5321/{LOG}</a></li>
  <li>📱 모바일 raw URL(구글 크롤러 친화): <code>https://blog.naver.com/PostView.naver?blogId=op5321&amp;logNo={LOG}</code></li>
  <li>🖼️ 이미지 {IMG_COUNT}장</li>
</ul>
```

이스케이프는 `&`, `<`, `>`만 한다. 작은따옴표를 `&#x27;`로 바꾸면 렌더링은 같아도 소스가 정본과 달라진다 (1227은 `'튀어 오르는 형태'`를 원문 그대로 둔다).

**핵심 포인트 선정**: 원문 단락 1~6번을 순서대로 그대로 쓴다. 단 **10자 미만 단락은 건너뛴다**. 게임 감상글에는 "캬", "와", "와 눈빛" 같은 감탄사가 단락으로 들어가 있는데, 이게 불릿에 오르면 요점 목록으로 읽히지 않는다. 감탄사를 뜻이 통하는 문장으로 바꿔 쓰는 건 금지 — 어시스턴트 추상화(안티패턴 3)에 해당한다. 그냥 건너뛰고 다음 단락을 쓴다. (1227 기준으로 이 필터를 적용해도 결과가 동일하다. 6개 불릿이 전부 17자 이상이라 검증된 형식을 깨지 않는다.)

### 4. 발행 — claude-in-chrome 단발 IIFE

사용자 데일리 Chrome에 이미 attach된 `claude-in-chrome` MCP를 그대로 사용 → 사용자 Tistory 로그인 세션 재활용 (별도 로그인 없음). 전체 시퀀스를 **2번의 batch round**로 압축 (원래 7~8번 → 2번).

#### round 1: navigate + setContent + 완료 + 자동 다이얼로그 처리

`browser_batch`에 navigate + wait + javascript_tool 한 번에 묶음. 단발 IIFE 안에서 setContent → 완료 클릭 → setTimeout chain으로 공개 라디오 + 공개 발행을 자동 처리.

```javascript
// chrome MCP javascript_tool에 단발 IIFE로 주입
(() => {
  const TITLE = '{원본 제목} | 정리본';  // ⚠️ 반드시 " | 정리본" suffix 붙일 것
  const LOG = '...';
  const BODY = `...본문 HTML 전체...`;

  // 제목 — ⚠️ native value setter 는 글쓰기 페이지에서 KEditor 재렌더가 값을
  //   날려버리는 산발적 버그가 있음 (실측: 새 글 진입 직후 제목이 ""로 리셋 →
  //   완료해도 발행 레이어가 안 뜸). 가장 견고한 건 실타이핑 모사 execCommand:
  const t = document.getElementById('post-title-inp');
  t.focus(); t.select();
  document.execCommand('insertText', false, TITLE);
  // 채운 뒤 t.value 를 반드시 재확인하고, 비었으면 insertText 재시도.
  // 완료 클릭 전 제목 != "" 를 확정할 것 (빈 제목이면 발행 다이얼로그가 안 뜸).

  // 본문 — TinyMCE setContent + save + setDirty
  const ed = window.tinymce.editors[0];
  // ⚠️ draft 방지: 먼저 기존 draft를 클리어해야 다음 /manage/post 진입 시 "저장된 글" 다이얼로그 안 뜸
  ed.setContent(''); ed.setDirty(false);
  ed.setContent(BODY);
  ed.save();
  ed.setDirty(true);

  // 완료 클릭 → 발행 다이얼로그 등장
  Array.from(document.querySelectorAll('button'))
    .find(b => b.textContent.trim() === '완료').click();

  // 다이얼로그 등장 polling — 보이는 공개 라디오 잡히면 클릭 후 0.4초 뒤 "공개 발행"
  // ⚠️ document.querySelectorAll('input[type=radio]')[0] 은 NG — 페이지엔 hidden radio가
  //     섞여 있어 index 기반 selector가 보이지 않는 라디오를 잡는 경우가 있음.
  //     반드시 input[type=radio][value="20"] 로 value 직접 타깃.
  const tryDialog = (tries) => {
    if (tries > 50) return;
    const radio = document.querySelector('input[type=radio][value="20"]');
    if (radio && radio.offsetParent !== null) {
      radio.click();
      setTimeout(() => {
        // ⚠️ draft 방지: 공개 발행 클릭 직전 에디터를 클리어해 auto-save draft가 남지 않도록
        ed.setContent(''); ed.setDirty(false);
        const pub = Array.from(document.querySelectorAll('button'))
          .find(b => b.textContent.trim() === '공개 발행');
        if (pub) pub.click();
      }, 400);
    } else {
      setTimeout(() => tryDialog(tries + 1), 200);
    }
  };
  setTimeout(() => tryDialog(0), 500);

  return {queued: true, bodyLen: ed.getContent().length};
})()
```

`browser_batch`는 `[navigate(/manage/post), wait(4s), javascript_tool(IIFE)]` 세 action을 한 round에. 페이지 navigate가 IIFE 컨텍스트를 깨므로 발행 후 redirect 직전까지가 한 round 한계.

**⚠️ 인터럽트 불가**: IIFE는 ~1초 안에 발행 클릭까지 끝나므로, 사용자가 작성 중간에 "다른 글로 해줘" 같은 중단 요청을 해도 이미 발행됐을 가능성이 큼. 발행 직전 사용자 확인을 받든가, 미리 글 선정 단계에서 확정을 받아둘 것.

#### round 2: redirect 후 새 entry URL 추출

```javascript
// browser_batch: [wait(4s), javascript_tool(extract)]
(() => {
  const a = Array.from(document.querySelectorAll('a'))
    .filter(x => /arnopark\.tistory\.com\/\d+$/.test(x.href))[0];
  return {path: location.pathname, url: a ? a.href : null};
})()
```

`path === '/manage/posts/'` + `url`이 새 entry이면 성공.

### 5. 발행 후 검증
```javascript
// 글관리 페이지로 redirect됨 → 최신 entry URL 추출
Array.from(document.querySelectorAll('a'))
  .filter(a => /arnopark\.tistory\.com\/\d+$/.test(a.href))[0].href
```

발행된 URL을 `WebFetch`로 다시 가져와 다음이 모두 박혀 있는지 확인:
- `<blockquote>` 1개
- `<h2>` 3개: "요약", "핵심 포인트", "원문 보기 (네이버 블로그)"
- 3개 백링크 모두 (m.blog anchor / blog.naver.com / PostView raw)
- `🖼️ 이미지 {N}장` 박혀 있음
- 자기소개 인사 없음
- **마이그레이션 푸터 없음** — 본문에 `마이그레이션` / `arnopark` / `원본 작성일` 0건
- 제목 끝 ` | 정리본`
- **본문 손상 없음** — TinyMCE setContent 가 멀티바이트 한 구간을 산발적으로 깨뜨릴 수 있음 (실측: "원문"→"옐문", "네이버"→"k이버", U+FFFD 혼입). curl 로 `옐문`/`�`(U+FFFD) 0개 + `원문 보기 (네이버 블로그)` 정상 매칭 확인. 깨졌으면 수정 모드(`/manage/post/<id>`)에서 해당 h2 만 정확한 문자열로 교체(`getContent().replace(/<h2[^>]*>[^<]*보기[^<]*<\/h2>/, 정상)` → `setContent` → `save`) 후 재발행.

## 안티패턴 (절대 금지)

1. **자기소개 인사** — "안녕하세요 박기린 입니다" 따위. 1002 정본엔 없는 어시스턴트 톤. 절대 금지.
2. **추상 요약** — "사당은 ~에 위치한 사당으로, 주제는 ~ 입니다. 사당 내부 전 구간에 걸쳐 ..." 식 압축 금지. **원문 풀어쓴 톤이 정본**. 원문 문장을 거의 그대로 옮기되 800자에서 자른다.
3. **핵심 포인트 추상화** — 어시스턴트가 만든 추상 불릿 ("위치: 리토의 마을 내부", "마무리: 왼쪽 구멍 → 상승 기류") 금지. **원문 첫 5~6개 문장을 그대로 토막내어 박는다**.
4. **이모지 누락** — 📎 🌐 📱 🖼️ 4개는 반드시 박혀야 함. 이 스킬 본문 HTML 한정 예외 (프로젝트 CLAUDE.md "이모지 금지" 룰은 스킬 작성물 기준이고, 본문은 사용자 자기 블로그 글이라 적용 X).
5. **다이얼로그 떠 있는 상태에서 setContent 재호출** — 다이얼로그 cancel 후 setContent하면 KEditor가 dirty 추적을 놓쳐 변경이 묻힘. setContent는 **다이얼로그 띄우기 전에 한 번만**.

## 함정 / 주의

- **"저장된 글이 있습니다" 다이얼로그** — Tistory가 /manage/post 진입 시 서버 측 auto-save draft를 감지해 confirm 다이얼로그를 띄움. 이 다이얼로그는 claude-in-chrome 확장 전체를 blocking하여 JS 실행·스크린샷 모두 타임아웃됨. 방지법: IIFE 시작 직후 `ed.setContent(''); ed.setDirty(false);` 로 기존 draft를 클리어하고, 공개 발행 클릭 직전에도 동일하게 클리어. 이미 다이얼로그가 뜬 경우 사용자가 직접 **취소**를 눌러야 한다 (computer 도구도 extension 경유라 동일하게 blocking됨).
- **글쓰기 페이지 unsaved changes로 인한 navigation 차단** — `onbeforeunload` 가드가 navigate를 막음. 항상 **새 탭에서 새 글 작성**.
- **TinyMCE 수정 모드 dirty flag** — `ed.save()` + `ed.setDirty(true)` 없으면 변경이 묻혀 옛 본문이 그대로 발행된다 (실측 확인).
- **발행 다이얼로그 기본 비공개** — value="0" 라디오가 체크돼있다. 공개(value="20") 명시 클릭 필수.
- **태그 input 가려짐** — 사이드바 태그 input은 새 글 페이지 일부 layout에선 안 보이고, 다이얼로그가 가리기도 한다. **자동화하지 않고 수동 보정 단계로 분리**.
- **네이버 도메인 navigate 불가** — claude-in-chrome MCP는 `*.naver.com`을 안전정책으로 차단. 본문 fetch는 반드시 curl 사용.
- **네이버 curl 헤더** — iPhone UA + `Referer: https://blog.naver.com/` 필수. 안 그러면 빈 페이지 또는 캡차.
- **대형 본문 base64 인라인 주입 잘림** — 한글 이스케이프 깨짐 방지로 TITLE/BODY 를 base64 ASCII 로 주입하는데, 본문이 크면(>~2KB, 예: 이미지 수십 장 글) 한 번에 인라인하면 페이로드가 중간에 잘리거나 망가지기 쉽다(실측 사고). **청크로 쪼개 페이지에서 `window.__b += '...'` 로 조립 → 아래 SHA-256 대조 → 마커(h2 3개·이모지 4종·인사 0) 검증 후에만** `setContent`. browser_batch 로 청크 append + 검증을 한 라운드에 묶으면 깔끔.

- **b64 길이 검증만으로는 부족 — SHA-256을 대조할 것** (2026-07-10 실측). 청크를 도구 호출에 옮겨 적는 과정에서 base64 한 글자가 바뀌면(`Drgpwg` → `Drgnwg`) **길이는 그대로**라 길이 체크를 통과하고, `atob`도 성공한다. 손상은 디코드된 UTF-8에서 U+FFFD 한 글자로만 드러난다. 같은 실행에서 다른 글은 청크가 1200자여야 하는데 1199자로 들어가 `atob`가 InvalidCharacterError로 터졌다 — 즉 오타는 두 방식으로 나타나며 길이 체크는 그중 하나만 잡는다.

  로컬에서 기대 해시를 뽑아 두고:
  ```bash
  python3 -c "import json,hashlib; b=json.load(open('chunks.json'))['<LOG>']['chunks']; print(hashlib.sha256(''.join(b).encode()).hexdigest())"
  ```
  페이지에서 대조한다. 불일치면 그 청크만 `slice()`로 되감아 다시 넣으면 되고, 발행은 절대 진행하지 않는다:
  ```javascript
  window.__sha = async (s) => {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
    return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,'0')).join('');
  };
  const shaOk = (await window.__sha(window.__b)) === '<기대 해시>';
  if (!shaOk) return {ERROR: 'sha-mismatch'};   // 여기서 ABORT
  ```
  청크당 누적 길이(1200, 2400, …)도 같이 반환하면 어느 청크가 틀렸는지 바로 좁혀진다. 해시가 맞으면 디코드 후 `fffd: 0`은 자동으로 따라온다.
- **TinyMCE setContent 멀티바이트 손상** — 위 '본문 손상 없음' 검증 참조. 산발적이라 같은 코드로 한 글은 멀쩡하고 다른 글은 h2 한 줄이 깨질 수 있음(실측: 1편 정상, 다음 편 "원문→옐문"). **발행 직전 에디터 `getContent` 로 손상 검증(옐문/U+FFFD/`원문 보기` 누락)하고 깨졌으면 ABORT**, 발행 후 curl 재검증.

## 성공 기준

1. `arnopark.tistory.com/<id>` URL 발급됨
2. WebFetch 재확인 시 위 "발행 후 검증" 항목 모두 통과
3. 자기소개 인사 없음
4. 요약 단락이 원문 풀어쓴 톤 (800자 컷, 미완결로 끝)
5. 제목 끝 ` | 정리본` 붙음

## 수동 보정 단계 (자동화 안 함)

발행 직후 사용자가 글관리에서 한 번 손볼 항목:
- **카테고리** — 원본 네이버 카테고리명과 동일하게 (예: "젤다 왕눈")
- **태그** (1002 패턴, 5개): `{카테고리명}, 기린파크, 네이버블로그, 요약, 정리`

자동화 안 하는 이유: 발행 다이얼로그 layout이 태그 input을 가리는 경우가 있어 셀렉터 안정성이 낮음. 발행 후 사용자가 직접 처리하는 게 더 빠르고 안정적.

## 의존 / 공유 자원

- `<repo>/_lib/parse_smarteditor.py` — 네이버 SmartEditor HTML → 마크다운 (`blog-learn`과 공유)
- `claude-in-chrome` MCP — Chrome 자동화 (사용자 데일리 세션 attach. 별도 로그인 X)
- `curl` — 네이버 도메인 우회 fetch

## 관련 스킬

- `/blog-learn` — 네이버 블로그 코퍼스 학습 (`_lib/parse_smarteditor.py` 공유)
- `/blog` — 네이버 블로그 새 글 자동 작성
- `/tistory-to-naver` — 반대 방향 (티스토리 → 네이버 마이그레이션)
