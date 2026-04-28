---
name: blog-learn
description: Download and learn the user's entire Naver blog archive (op5321 / 박기린의 기린파크) into ./.claude/blog-corpus/, then generate a style guide. Use when the user says "/blog-learn", wants to (re)train the blog writer, asks to refresh the blog corpus, or starts a new blog-writing session in a fresh project. Also use with "--refresh" to pull only new posts since last run.
---

# blog-learn — 네이버 블로그 전체 학습

박기린님의 네이버 블로그 `op5321`를 통째로 긁어와 `./.claude/blog-corpus/`에 캐시하고 스타일 가이드를 생성합니다.

## 언제 쓰나
- 사용자가 `/blog-learn` 명령을 입력했을 때
- 새 프로젝트 디렉토리에서 블로그 작업을 처음 시작할 때 (캐시 없음)
- `/blog-learn --refresh` — 신규 글만 증분 수집

## 실행 절차

### 1. 수집
현재 작업 디렉토리에서 다음을 실행:

```bash
python3 ~/.claude/skills/blog-learn/scripts/fetch.py op5321 .claude/blog-corpus
```

`--refresh`가 붙으면 그대로 전달. `--limit N`은 디버깅용.

이 스크립트가 하는 일:
- RSS 시드 (`rss.blog.naver.com/op5321.xml`)
- `PostTitleListAsync.naver`로 전체 아카이브 logNo 열거
- `m.blog.naver.com/op5321/{logNo}`로 각 포스트 HTML 다운로드 (iPhone UA, 병렬 4)
- `parse_smarteditor.py`로 SmartEditor DOM → 마크다운 변환
- 결과: `raw/html/*.html`, `posts/*.md`, `index.json`

### 2. 스타일 가이드 생성
수집이 끝나면 `./.claude/blog-corpus/posts/`에서 무작위 샘플 20~30편(다양한 카테고리 섞어서)을 읽고 `./.claude/blog-corpus/style-guide.md`를 작성. 포함해야 하는 항목:

- **말투/어조**: 종결 패턴 (`~습니다`/`~해요`/`~네요` 등 분포), 1인칭 사용, 독자 호칭
- **문장/단락 길이**: 평균 문장 길이, 짧은 문장 비율, 단락당 문장 수 (대체로 한 문장 = 한 단락인 경향 관찰되는지)
- **구성 패턴**: 도입부(훅) 방식, 본론 전개(소제목 사용 빈도/간격), 마무리 패턴
- **자주 쓰는 어휘/관용구**: Top 20
- **섹션 구조**: `## 소제목` 개수 분포, `---` 구분선 사용 빈도
- **이미지 사용**: 단락당 이미지 비율, 이미지 그룹핑 패턴
- **해시태그**: 본문 내 해시태그 사용 여부, 포스트당 평균 개수
- **이모지**: 관측 결과 "사용 안 함" 명시 — 이건 하드룰이므로 스타일 가이드에 굵게 박아둘 것
- **카테고리 패턴**: 주요 카테고리별 특징 (예: "붉은사막"류는 공략 중심, "외식"류는 리뷰 중심 등)
- **제목 패턴**: `[시리즈] N. 부제 / vs 보스` 같은 포맷 예시 5~10개

작성 원칙: 추측하지 말고 실제 샘플에서 관찰된 것만 기록. 애매하면 "관찰된 경향"으로 hedged statement.

### 3. 보고
완료 후 사용자에게:
- 수집한 포스트 수 / 에러 수
- 카테고리 분포 상위 5개
- `style-guide.md` 경로
- 다음 단계: `/blog "주제"`

## 하드룰
- 생성되는 스타일 가이드를 포함한 모든 산출물에 **이모지 금지**.
- 네트워크 요청은 반드시 iPhone UA + `blog.naver.com` referer로 (fetch.py가 알아서 처리).
- 429/503 받으면 exponential backoff (fetch.py가 처리).

## 디렉토리 (최종)
```
./.claude/blog-corpus/
├── index.json
├── style-guide.md
├── raw/rss.xml, raw/html/{logNo}.html
├── posts/{logNo}.md
└── drafts/              # /blog 스킬이 사용
```
