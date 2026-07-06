# english-study 스킬 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 게임/자유 토픽 뉴스 큐레이션 + 영어 소감 교정 + Notion 단어장 + Leitner 복습을 하나의 스킬 `english-study`로 구현한다.

**Architecture:** 결정적 작업(Reddit 뉴스 수집)은 표준 라이브러리 Python 스크립트로, 판단 작업(리라이팅·교정·복습 퀴즈)은 SKILL.md 절차로 분리한다. 상태는 전부 Notion(단어장 DB + 방법론 페이지)에 저장해 기기독립을 보장한다.

**Tech Stack:** Python 3 표준 라이브러리(urllib)만 사용, Notion MCP(mcp__notion__*), git.

**Spec:** `docs/superpowers/specs/2026-07-06-english-study-design.md` (승인 완료)

## Global Constraints

- 이모지 금지 — 모든 산출물(코드 주석, SKILL.md, Notion 본문, 커밋 메시지)에 한 글자도 쓰지 않는다.
- 게임명·회사명 등 고유명사 왜곡 금지.
- 커밋 메시지에 `Co-Authored-By` 트레일러 절대 금지. 메시지만 작성한다 (사용자 전역 규칙).
- Notion 변경(DB 생성, 행 생성·수정·삭제)은 반드시 사용자 확인 후 실행. 실패·404·저장 이상 시 무단 진행 금지, 보고 후 지시 대기.
- Notion에 한글 저장 후 반드시 fetch로 재검증 (깨짐 사고 전례: "챕터8"→"챕터엘").
- Python 스크립트는 python3 표준 라이브러리만 사용 (외부 패키지 의존 금지 — 리포 관례).
- SKILL.md 본문은 한국어 (리포 하드룰).
- SKILL.md 작성은 리포 CLAUDE.md 규칙대로 스킬 작성 도구 프로세스를 적용한다. Task 3에 superpowers:writing-skills 체크리스트를 내장했으므로 그 체크리스트 통과가 곧 도구 경유 요건 충족이다.

---

### Task 1: 뉴스 수집 스크립트 fetch_news.py

**Files:**
- Create: `english-study/scripts/fetch_news.py`

**Interfaces:**
- Produces: `python3 english-study/scripts/fetch_news.py` 실행 시 stdout으로 JSON 출력. 실행 시간 약 1~2분 (rate limit 대기 포함) — Bash timeout 180초 이상으로 호출.
  - 형태: `{"ok": bool, "failed": [{"feed": str, "error": str}], "candidates": {"game_news": [POST], "game_fun": [POST], "free_topic": [POST]}}`
  - POST = `{"title": str, "url": str(레딧 코멘트 링크), "external_url": str(원문 기사 링크, 셀프 글이면 빈 문자열), "subreddit": str, "author": str, "published": str}`
  - 각 배열은 top-of-day 순서(피드 상단 = 고득점)라 score 필드 없이도 상위가 인기 글이다.
  - Task 3의 SKILL.md가 이 JSON 키 이름을 그대로 참조한다.
  - 실측(2026-07-06): Reddit 익명 JSON API(www/old/api.reddit.com)는 브라우저 UA로도 전부 403 차단. RSS(Atom)만 열려 있고 익명 RSS는 IP당 분당 1요청 수준 rate limit(x-ratelimit 헤더로 확인) → 멀티레딧(`r/games+gaming`)으로 요청을 2개로 압축하고 사이에 reset 헤더만큼 대기한다.

- [ ] **Step 1: 스크립트 작성**

`english-study/scripts/fetch_news.py`:

```python
#!/usr/bin/env python3
"""Reddit 인기 글 수집 - english-study 스킬용 (RSS 기반).

Reddit은 익명 JSON API(www/old/api.reddit.com)를 브라우저 UA로도 403 차단한다
(2026-07-06 실측). RSS(Atom)만 열려 있고, 익명 RSS는 IP당 분당 1요청 수준의
rate limit이 있어 요청을 2개로 압축했다:
  1) r/games+gaming 멀티레딧 top-of-day (게임 뉴스+소식, limit=25)
  2) r/popular top-of-day (자유 토픽, limit=10)
요청 사이에는 x-ratelimit-reset 헤더만큼 대기한다. 총 실행 약 1~2분.

사용: python3 english-study/scripts/fetch_news.py   (Bash timeout 180초 이상)
출력: {"ok": bool, "failed": [{"feed", "error"}],
       "candidates": {"game_news": [...], "game_fun": [...], "free_topic": [...]}}
각 배열은 top-of-day 순서(상단 = 고득점)다.
"""
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
ATOM = "{http://www.w3.org/2005/Atom}"
FEEDS = [
    ("games+gaming", "https://www.reddit.com/r/games+gaming/top/.rss?t=day&limit=25"),
    ("popular", "https://www.reddit.com/r/popular/top/.rss?t=day&limit=10"),
]
MAX_WAIT = 90


def reset_seconds(headers):
    try:
        return int(float(headers.get("x-ratelimit-reset", "60")))
    except (TypeError, ValueError):
        return 60


def fetch(url):
    """(xml_text, 다음 요청까지 대기초) 반환. 429면 reset만큼 기다렸다 1회 재시도."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8"), reset_seconds(resp.headers)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                time.sleep(min(reset_seconds(e.headers) + 5, MAX_WAIT))
                continue
            raise


def parse_entries(xml_text):
    posts = []
    for entry in ET.fromstring(xml_text).iter(f"{ATOM}entry"):
        link = entry.find(f"{ATOM}link")
        cat = entry.find(f"{ATOM}category")
        author = entry.findtext(f"{ATOM}author/{ATOM}name") or ""
        content = html.unescape(entry.findtext(f"{ATOM}content") or "")
        m = re.search(r'href="([^"]+)">\s*\[link\]', content)
        external = m.group(1) if m else ""
        if external.startswith("https://www.reddit.com"):
            external = ""  # 셀프 포스트는 원문 링크가 곧 레딧 글
        posts.append({
            "title": entry.findtext(f"{ATOM}title") or "",
            "url": link.get("href") if link is not None else "",
            "external_url": external,
            "subreddit": cat.get("term") if cat is not None else "",
            "author": author.removeprefix("/u/"),
            "published": entry.findtext(f"{ATOM}updated") or "",
        })
    return posts


def main():
    result = {"ok": True, "failed": [], "candidates": {}}
    wait = 0
    for i, (name, url) in enumerate(FEEDS):
        if i > 0:
            time.sleep(min(wait + 5, MAX_WAIT))
        try:
            xml_text, wait = fetch(url)
            posts = parse_entries(xml_text)
        except Exception as e:
            result["failed"].append({"feed": name, "error": str(e)})
            wait = 60
            continue
        if name == "games+gaming":
            result["candidates"]["game_news"] = [p for p in posts if p["subreddit"].lower() == "games"]
            result["candidates"]["game_fun"] = [p for p in posts if p["subreddit"].lower() == "gaming"]
        else:
            result["candidates"]["free_topic"] = posts
    if not result["candidates"]:
        result["ok"] = False
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행 검증 (실패 케이스 포함 구조 검증)**

Run:

Run (Bash timeout 240초 이상, 실행에 약 1~2분 소요):

```bash
python3 english-study/scripts/fetch_news.py | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert isinstance(d['ok'], bool), 'ok 필드 없음'
assert isinstance(d['failed'], list), 'failed 필드 없음'
assert isinstance(d['candidates'], dict), 'candidates 필드 없음'
for key in ('game_news', 'game_fun', 'free_topic'):
    assert key in d['candidates'], f'{key} 없음'
    posts = d['candidates'][key]
    assert len(posts) >= 1, f'{key} 비어 있음'
    for field in ('title', 'url', 'external_url', 'subreddit', 'author', 'published'):
        assert field in posts[0], f'{key}[0]에 {field} 없음'
print('OK:', {k: len(v) for k, v in d['candidates'].items()}, '/ failed =', d['failed'])
"
```

Expected: `OK: {'game_news': N, 'game_fun': M, 'free_topic': 10} / failed = []` (N+M = 25 내외, N·M 모두 1 이상)

직전 1분 안에 Reddit RSS를 조회한 적이 있으면 첫 요청이 429를 맞고 스크립트가 자동으로 한 번 재시도한다(그만큼 더 걸림). `failed`에 항목이 남으면 rate limit 쿨다운 후 1회 재실행해 보고, 그래도 실패면 그 사실을 보고한다.

- [ ] **Step 3: 커밋**

```bash
git add english-study/scripts/fetch_news.py
git commit -m "english-study: fetch_news.py를 RSS 기반으로 전환 (Reddit JSON API 403 차단 대응)"
```

(참고: 최초 JSON API 버전은 ef9f9bb로 커밋됨. 이 커밋은 RSS 전환분.)

---

### Task 2: Notion 단어장 DB + 방법론 페이지 생성 (사용자 확인 필수)

**Files:** 리포 파일 변경 없음 (Notion만). 산출된 ID 3개는 Task 3에 전달.

**Interfaces:**
- Produces: 다음 3개 ID (Task 3의 SKILL.md 좌표 섹션에 그대로 기입)
  - `{METHOD_PAGE_ID}` — "영어 공부" 방법론 페이지 ID
  - `{DB_PAGE_ID}` — "영어 단어장" DB 페이지 ID
  - `{DATA_SOURCE_ID}` — 단어장 데이터소스(collection) ID. 행 생성 시 parent로 사용.

- [ ] **Step 1: 위치 확인 및 생성 승인 (AskUserQuestion)**

사용자에게 묻는다: "영어 공부 페이지를 개인 워크스페이스 어디에 만들까요?" 선택지: (a) 업무관리 페이지(`389c6f40-e87e-80c9-bdc0-d7b176c0efe3`) 아래, (b) 워크스페이스 최상위, (c) 사용자 지정 위치. 응답을 받기 전에는 어떤 Notion 쓰기도 하지 않는다.

- [ ] **Step 2: "영어 공부" 방법론 페이지 생성**

`mcp__notion__notion-create-pages`로 Step 1에서 정한 parent 아래 페이지 생성. 제목: `영어 공부`. 본문(그대로, 이모지 없음):

```markdown
# 영어 공부 방법론

이 페이지는 english-study 스킬(giraffe-skills 리포)의 기기독립 요약본이다. 리포가 없는 컴퓨터나 모바일에서도 이 페이지와 아래 영어 단어장 DB만으로 복습을 재현할 수 있다. 규칙이 바뀌면 SKILL.md와 이 페이지를 같이 갱신한다.

## 현재 리라이팅 난이도: 1단계

- 1단계: 전면 리라이팅 (B1, 회화체 쉬운 문장)
- 2단계: 부분 리라이팅 (어려운 문장만 풀어쓰고 원문 표현을 점점 살림)
- 3단계: 원문 그대로 + 어려운 단어에만 괄호 힌트
- 4단계: 원문 그대로 (힌트 없음)

승급은 자동이 아니라 제안 후 동의로만 한다. 신호: 소감에서 내용 오해 없음, 복습 정답률 높음, 사용자의 "요즘 쉽다" 체감. 오해가 잦으면 하향을 제안한다. 단계가 바뀌면 위의 "현재 리라이팅 난이도" 줄을 갱신한다.

## Leitner 복습 규칙

- 간격: 단계1=1일, 단계2=3일, 단계3=7일, 단계4=14일, 단계5=30일
- 신규 단어: 단계 0, 다음 복습일 = 등록 다음날
- 복습 대상: 다음 복습일이 오늘이거나 그 이전(당일 포함)이고 상태가 학습 중인 단어, 오래된 것부터 최대 10개
- 맞히면 단계 +1, 다음 복습일 = 오늘 + 새 단계의 간격. 틀리면 단계 0, 다음 복습일 = 내일
- 단계 5 복습(30일 간격)까지 맞히면 상태 = 졸업, 복습 대상에서 제외
- 퀴즈 형식: 단계 0~1 = 한→영 회상, 단계 2~3 = 문장 빈칸, 단계 4~5 = 직접 문장 만들기(영작 후 교정)

## 세션 절차 요약

1. 뉴스 수집: 게임 2건 + 자유 토픽 1건 (Reddit top-of-day)
2. 건마다: 현재 난이도로 리라이팅 제시 → 사용자가 영어로 소감 1~3문장 → 3단계 교정(뜻 전달 / 문법·표현 / 원어민식) → 단어·숙어 2~4개 확정
3. 확정 단어를 아래 영어 단어장 DB에 저장 (신규 = 단계 0, 다음 복습일 = 내일)
4. 마지막에 Leitner 복습. "복습만 해줘"로 복습만 따로 실행 가능
```

- [ ] **Step 3: "영어 단어장" DB 생성**

`mcp__notion__notion-create-database`로 Step 2 페이지 아래 생성. 제목: `영어 단어장`. 속성:

| 속성 | 타입 | 옵션 |
|---|---|---|
| 표현 | title | - |
| 뜻 | rich_text | - |
| 예문 | rich_text | - |
| 유형 | select | `단어`, `숙어·구동사`, `회화 표현` |
| 출처 | rich_text | - |
| 등록일 | date | - |
| 복습 단계 | select | `0`, `1`, `2`, `3`, `4`, `5` |
| 다음 복습일 | date | - |
| 상태 | select | `학습 중`, `졸업` |

- [ ] **Step 4: 생성 결과 재조회 검증**

`mcp__notion__notion-fetch`로 데이터소스를 조회해 확인:
- 속성명 9개가 위 표와 글자 단위로 일치 (한글 깨짐 검사)
- select 옵션 문자열 일치 (`숙어·구동사`의 가운뎃점, `학습 중`의 공백 포함)
- 방법론 페이지 본문에서 "현재 리라이팅 난이도: 1단계" 문자열이 온전한지 확인

깨진 글자가 있으면 update로 즉시 교정하고 재검증. 교정이 안 되면 중단하고 사용자에게 보고 (무단 재생성 금지).

- [ ] **Step 5: 테스트 행 왕복 검증**

1. `notion-create-pages`(parent = `{DATA_SOURCE_ID}`)로 1행 생성: 표현=`hold up`, 뜻=`기다려 / 버티다`, 예문=`Hold up, the patch notes just dropped.`, 유형=`회화 표현`, 출처=`셋업 테스트`, 등록일=오늘(YYYY-MM-DD), 복습 단계=`0`, 다음 복습일=내일, 상태=`학습 중`
2. fetch로 재조회 — 한글(`기다려 / 버티다`, `셋업 테스트`)이 온전한지 확인
3. 검증 후 그 행을 삭제(archive). 삭제가 도구로 안 되면 행을 남겨두고 사용자에게 수동 삭제를 요청 (임의 우회 금지)
4. 날짜 계산은 `python3 -c "import datetime; t=datetime.date.today(); print(t, t+datetime.timedelta(days=1))"`로 한다 (기억으로 계산 금지)

- [ ] **Step 6: ID 3개 기록**

`{METHOD_PAGE_ID}`, `{DB_PAGE_ID}`, `{DATA_SOURCE_ID}`를 대화에 명시적으로 남긴다. Task 3이 이 값을 소비한다.

---

### Task 3: SKILL.md 작성

**Files:**
- Create: `english-study/SKILL.md`

**Interfaces:**
- Consumes: Task 2의 `{METHOD_PAGE_ID}`, `{DB_PAGE_ID}`, `{DATA_SOURCE_ID}` (아래 본문의 토큰 3곳을 실제 ID로 치환), Task 1의 JSON 키 이름.

- [ ] **Step 1: SKILL.md 작성 (아래 내용 그대로, 토큰 3곳만 치환)**

````markdown
---
name: english-study
description: 박기린님의 영어 공부 세션을 진행한다. Reddit에서 게임 뉴스 2건 + 자유 토픽 1건을 수집해 현재 난이도 단계에 맞는 쉬운 영어(실제 회화체)로 제시하고, 사용자가 영어로 쓴 소감을 3단계(뜻 전달 / 문법·표현 / 원어민식)로 교정하며, 나온 단어·숙어를 Notion "영어 단어장" DB에 저장하고, 세션 말미에 Leitner 간격 반복으로 복습 퀴즈를 낸다. 사용 시점 — 사용자가 "/english-study", "영어 공부하자", "영어 공부", "오늘의 영어 뉴스", "영어 뉴스 브리핑"이라고 할 때(전체 세션), 또는 "복습만 해줘", "단어 복습", "영어 복습"이라고 할 때(복습만 모드) 반드시 사용. 이모지 절대 금지, 게임명·회사명 등 고유명사 왜곡 금지, Notion 실패 시 무단 진행 금지.
---

# english-study — 뉴스 영어 공부 + Notion 단어장 + Leitner 복습

출근길·틈새 시간용 10~20분 세션. 뉴스 3건(게임 2 + 자유 1)을 쉬운 영어로 읽고, 영어 소감을 쓰고, 교정받고, 단어를 쌓고, 세션 끝에 복습한다.

## 원칙

- **이모지 금지, 고유명사 왜곡 금지** (리포 공통 하드룰)
- **Notion 실패 시 무단 진행 금지.** MCP 무응답, 좌표 404, 저장 결과 이상(한글 깨짐 등)이면 임의로 우회·대체·재생성하지 않는다. 상황을 보고하고 허락받은 뒤에만 진행한다. `notion-search` 재탐색까지는 허용하되, 찾은 좌표로 실제 쓰기 전에 확인받는다. 저장 못 한 단어는 "저장 대기 목록"으로 대화에 남기고 지시를 기다린다.
- **날짜 계산은 기억 금지.** `python3 -c "import datetime; ..."`로 currentDate 기준 계산 (요일 포함).
- **방법론 이중화.** 복습 규칙·난이도 단계가 바뀌면 이 파일과 Notion 방법론 페이지를 같이 갱신한다. 리포 없는 기기에서는 방법론 페이지만으로 복습을 재현할 수 있어야 한다.
- **무인 진행 금지.** 사용자 응답 없이 다음 뉴스로 넘어가거나 퀴즈 정답을 스스로 판정해 버리지 않는다.

## 모드

- **전체 세션** (기본): 아래 절차 1~5 전부. 트리거: "영어 공부하자", "오늘의 영어 뉴스" 등
- **복습만**: 절차 5만 단독 실행. 트리거: "복습만 해줘", "단어 복습"

## Notion 좌표 (개인 WS pos000830, 2026-07-06 생성)

- 방법론 페이지 `영어 공부`: `{METHOD_PAGE_ID}` — 현재 리라이팅 난이도 단계가 여기 있다
- 단어장 DB 페이지 `영어 단어장`: `{DB_PAGE_ID}`
- 데이터소스(collection): `{DATA_SOURCE_ID}` — 행 생성 시 parent로 사용

좌표가 404면 `notion-search`로 "영어 단어장"을 재탐색하고, **사용자 확인 후** 이 섹션을 갱신한다.

속성: 표현(title) · 뜻(text) · 예문(text) · 유형(select: 단어/숙어·구동사/회화 표현) · 출처(text) · 등록일(date) · 복습 단계(select: 0~5) · 다음 복습일(date) · 상태(select: 학습 중/졸업)

행 조회는 `query-data-sources`(SQL 또는 view)로 한다 (2026-07-06 실측: 이 WS에서 정상 동작. 첫 호출이 429 rate_limited면 retry_after만큼 기다렸다 재시도). 데이터소스 fetch는 스키마·좌표 확인용이며 행을 반환하지 않는다. query가 권한 오류로 막히면 무단 우회하지 말고 보고 후 지시를 기다린다.

## 절차 (전체 세션, 약 15~20분)

### 1. 난이도 확인

방법론 페이지(`{METHOD_PAGE_ID}`)를 fetch해 "현재 리라이팅 난이도: N단계"를 읽는다. 이 값이 오늘 제시문의 난이도다.

### 2. 뉴스 수집

```bash
python3 english-study/scripts/fetch_news.py   # 약 1~2분 소요 (rate limit 대기 포함), Bash timeout 180초 이상
```

출력 JSON의 `candidates.game_news`(r/games) / `candidates.game_fun`(r/gaming)에서 게임 2건, `candidates.free_topic`(r/popular)에서 1건을 고른다. 각 배열은 top-of-day 순서라 위쪽일수록 인기 글이다. 기준: 인기(배열 순서)와 재미(사용자는 게임 취미). RSS에는 성인물 플래그가 없으므로 부적절한 글은 큐레이션 단계에서 직접 거른다.

- **중복 확인**: 단어장 DB 최근 행들의 "출처"에 같은 뉴스 제목이 있으면 다음 후보로 넘긴다.
- 사용자가 "오늘은 1건만"이라고 하면 분량을 줄인다.

**폴백 체인** (스크립트 실패 시, 네이버 수집 관례와 동일). Reddit 익명 JSON API(www/old/api.reddit.com)는 403 차단이므로(2026-07-06 실측) 폴백도 RSS다:

1. `curl -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36" "https://www.reddit.com/r/games+gaming/top/.rss?t=day&limit=25"` → 60~70초 대기 → 같은 UA로 `https://www.reddit.com/r/popular/top/.rss?t=day&limit=10` (익명 RSS는 분당 1요청 수준 rate limit)
2. 그것도 막히면 그날만 WebSearch로 대체하고, 세션 후 스크립트를 점검한다.

### 3. 건별 루프 (건당 4~5분)

각 뉴스에 대해:

1. **제시** — 현재 난이도 단계에 맞춰 뉴스를 영어로 제시한다. 실제 회화에서 쓰는 자연스러운 문장으로 쓰고 교과서체는 금지. 배울 만한 표현 2~3개를 굵게 표시하고 짧은 한국어 힌트를 붙인다. 원문 링크(`external_url` 없으면 `url`)를 병기한다.
2. **소감 대기** — 사용자가 영어로 1~3문장 소감을 쓴다. 짧아도 된다.
3. **3단계 피드백** — ① 뜻이 통했는지 ② 문법·표현 교정 ③ "원어민이라면 이렇게" 버전. 교정에서 나온 좋은 표현도 저장 후보에 추가한다.
4. **단어 확정** — 그 건에서 저장할 단어·숙어 2~4개를 제안하고 사용자가 가감해 확정한다.

### 4. Notion 저장

- 확정 단어를 **한 건씩 순차** `create-pages` (parent = 데이터소스). batch 금지 — 인코딩 사고 예방.
- 신규 값: 복습 단계=`0`, 다음 복습일=내일, 상태=`학습 중`, 등록일=오늘, 예문=그 표현이 나온 실제 문장, 출처=뉴스 제목 또는 `내 소감 교정`.
- 저장 직후 fetch로 한글 깨짐을 검증하고, 깨졌으면 즉시 update로 교정한다.
- 실패하면 원칙(무단 진행 금지)대로 보고하고 지시를 기다린다.

### 5. 복습 (Leitner) — "복습만" 모드는 여기부터

1. `query-data-sources`로 **다음 복습일 <= 오늘(당일 포함)이고 상태=학습 중**인 행을 다음 복습일 오래된 순으로 최대 10개 뽑는다 (429면 retry_after 후 재시도). 0개면 "오늘은 복습할 단어가 없다"고 알리고 끝낸다 (억지로 만들지 않는다).
2. 단계별 퀴즈 형식:
   - 단계 0~1: **한→영 회상** — 뜻을 주고 영어 표현을 떠올리게 한다
   - 단계 2~3: **문장 빈칸** — 그 표현이 나온 뉴스와 비슷한 문맥의 새 문장에서 빈칸 채우기
   - 단계 4~5: **직접 문장 만들기** — 그 표현으로 짧은 영작, 제출받아 교정
3. 판정 후 갱신 (한 건씩 update, 날짜는 python3로 계산):
   - 맞힘: 단계 +1, 다음 복습일 = 오늘 + 새 단계 간격 (단계1=1일, 2=3일, 3=7일, 4=14일, 5=30일)
   - 틀림: 단계 `0`, 다음 복습일 = 내일
   - 단계 5 복습까지 맞히면 상태=`졸업`
4. 마지막에 요약 보고: 오늘 새 단어 N개 저장, 복습 M개 중 K개 정답, 졸업 J개.

## 리라이팅 난이도 4단계 (승급 규칙)

| 단계 | 제시 방식 |
|---|---|
| 1 | 전면 리라이팅 (B1, 회화체 쉬운 문장) |
| 2 | 부분 리라이팅 (어려운 문장만 풀어쓰고 원문 표현을 점점 살림) |
| 3 | 원문 그대로 + 어려운 단어에만 괄호 힌트 |
| 4 | 원문 그대로 (힌트 없음) |

- **자동 상향 금지.** 신호(소감에서 내용 오해 없음, 복습 정답률 높음, "요즘 쉽다" 체감 발언)가 쌓이면 상향을 **제안**하고 동의 시 적용. 오해가 잦으면 하향을 제안.
- 특정 뉴스만 유난히 어려우면 그 건만 일시적으로 쉽게 쓴다 (단계 변경 아님).
- 단계가 바뀌면 방법론 페이지의 "현재 리라이팅 난이도" 줄을 갱신한다.

## 함정 / 주의

- Reddit 익명 JSON API는 브라우저 UA로도 403 차단(2026-07-06 실측) — 스크립트는 RSS(Atom)를 쓴다. 익명 RSS는 분당 1요청 수준 rate limit이라 요청 2개(멀티레딧 games+gaming, popular)로 압축하고 사이에 대기한다. 스크립트 실행은 Bash timeout 180초 이상으로.
- WebFetch는 reddit/naver 등에서 막힐 수 있다 — curl + 브라우저 UA 경로를 쓴다.
- 한글 리터럴 깨짐 사고 전례("챕터8"→"챕터엘") — Notion 저장 후 재검증 필수.
- 복습 판정을 후하게 주지 않는다 — 애매하면 사용자에게 "이 정도면 맞힌 걸로 할까요?"라고 묻는다.
- 관련 메모리: [[naver-cafe-archive-limits]](curl UA 패턴), [[notion-korean-literal-no-escape]], [[feedback-device-independent-solutions]].
````

- [ ] **Step 2: writing-skills 체크리스트 검증**

아래를 모두 확인 (하나라도 실패면 수정 후 재확인):

1. frontmatter가 `name`, `description` 2필드이고 YAML 파싱이 되는가: `python3 -c "import pathlib, re; t = pathlib.Path('english-study/SKILL.md').read_text(); m = re.match(r'^---\n(.*?)\n---\n', t, re.S); assert m, 'frontmatter 없음'; assert 'name: english-study' in m.group(1); assert 'description:' in m.group(1); print('frontmatter OK')"`
2. description에 전체 세션 트리거("영어 공부하자", "오늘의 영어 뉴스")와 복습만 트리거("복습만 해줘", "단어 복습")가 모두 들어 있는가
3. `{METHOD_PAGE_ID}` 등 미치환 토큰이 남아 있지 않은가: `grep -c '{.*_ID}' english-study/SKILL.md` → Expected: `0` (grep exit 1)
4. 이모지가 없는가: `python3 -c "import pathlib; t = pathlib.Path('english-study/SKILL.md').read_text(); bad = [c for c in t if 0x1F000 <= ord(c) <= 0x1FFFF or 0x2600 <= ord(c) <= 0x27BF or 0x2B00 <= ord(c) <= 0x2BFF or ord(c) == 0xFE0F]; assert not bad, bad; print('no emoji')"` (한글·CJK는 이 범위 밖이라 안 걸림)
5. Task 1의 JSON 키(`candidates.game_news`, `game_fun`, `free_topic`, `external_url`)가 스크립트 출력과 일치하는가 (Task 1 Interfaces 참조)

- [ ] **Step 3: 커밋**

```bash
git add english-study/SKILL.md
git commit -m "english-study 스킬 추가: 뉴스 영어 공부 + 소감 교정 + Notion 단어장 + Leitner 복습"
```

---

### Task 4: E2E 스모크 (새 세션 관점 검증)

**Files:** 수정 발생 시에만 해당 파일. 기본은 검증만.

**Interfaces:**
- Consumes: Task 1~3의 전체 산출물.

- [ ] **Step 1: 새 세션 시뮬레이션으로 절차 1~2 실행**

대화 기억에 의존하지 말고 `english-study/SKILL.md`만 읽고 그대로 따라 한다:

1. 방법론 페이지 fetch → "현재 리라이팅 난이도: 1단계" 읽힘 확인
2. `python3 english-study/scripts/fetch_news.py` 실행 (약 1~2분, Bash timeout 180초 이상) → 게임 2건 + 자유 1건을 실제로 선정해 제목을 사용자에게 보여줌

Expected: SKILL.md에 적힌 좌표·명령만으로 두 단계가 완주됨. 막히는 지점이 있으면 그것이 곧 SKILL.md의 결함이므로 해당 부분을 수정한다.

- [ ] **Step 2: 복습 쿼리 경로 확인**

데이터소스 fetch로 행 조회가 되는지 확인 (Task 2 Step 5에서 테스트 행을 지웠으므로 0행이어도 정상 — "복습 대상 0개면 생략" 경로가 동작하는지만 본다).

- [ ] **Step 3: 수정이 있었으면 커밋, 사용자에게 완료 보고**

```bash
git add -A english-study/
git commit -m "english-study: E2E 스모크에서 발견된 결함 수정"
```

(수정이 없으면 커밋 생략.) 보고 내용: 스크립트 동작, Notion 좌표 유효, SKILL.md 단독 완주 가능 여부. 이후 첫 실전 세션("영어 공부하자")을 제안한다.
