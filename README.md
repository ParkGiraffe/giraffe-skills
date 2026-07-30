# giraffe-skills

박기린(`op5321` / 박기린의 기린파크)이 직접 쓰는 Claude Code 스킬 모음입니다.

**개인용 리포입니다.** 대부분의 스킬이 특정 네이버 블로그 계정(`op5321`), 개인 Notion
데이터베이스, macOS 로컬 환경에 맞춰져 있어서 클론만 해서는 남이 그대로 쓸 수 없습니다.
`face-anonymizer`, `instagram-download`, `youtube-music-download`, `rebase-on-main` 정도가
계정과 무관하게 동작합니다. 나머지는 포크해서 블로그 ID와 Notion DB ID를 바꿔야 합니다.

## 수록 스킬 (22개)

### 블로그 글쓰기

| 스킬 | 하는 일 |
|---|---|
| [`blog-learn`](./blog-learn/) | 네이버 블로그 전체 아카이브를 `./.claude/blog-corpus/`로 내려받고 스타일 가이드를 만듭니다. `--refresh`로 증분 수집합니다. |
| [`blog`](./blog/) | 초안 대본과 SmartEditor HTML, 제목 후보, 해시태그, 카테고리를 만들고 네이버 에디터에 자동 입력합니다. 문체는 명료한 분석글(`~입니다` 체)이며 사용자 말투 모방이 아닙니다. |
| [`blog-title`](./blog-title/) | 코퍼스의 카테고리별 `[IP/브랜드 + 형태]` 태그 컨벤션을 학습해 제목 후보 5개를 추천합니다. |
| [`blog-topic-brief`](./blog-topic-brief/) | 잘 모르는 주제를 웹 검색으로 사전조사한 뒤 사실관계를 정리하고, `[코퍼스 기반]`과 `[일반 SEO 기반]` 두 갈래로 제목과 태그를 냅니다. |
| [`naver-blog-tags`](./naver-blog-tags/) | 글에서 키워드를 뽑아 네이버 연관검색어와 대조하고, 기존 글의 태그 형식과 공식 표기로 정제해 해시태그를 만듭니다. |

### 블로그 이전과 발행

| 스킬 | 하는 일 |
|---|---|
| [`tistory-to-naver`](./tistory-to-naver/) | Tistory 글을 네이버 SmartEditor로 옮깁니다. 본문·이미지·헤딩·구분선·코드블록을 보존하고, 하단 태그 줄은 새로 뽑아 붙입니다. |
| [`naver-to-naver`](./naver-to-naver/) | 네이버 글을 네이버로 재발행합니다. 서식을 한 줄씩 그대로 옮기고 사진을 원본 화질(GIF 애니메이션·스티커 포함)로 복제한 뒤, 원본 대비 누락 0을 자동 검증합니다. |
| [`notion-to-naver`](./notion-to-naver/) | Notion 페이지를 네이버로 옮깁니다. 창작이 아니라 전사라서 구조와 내용을 유지하고 종결어미만 다듬습니다. |
| [`js-lecture-publish`](./js-lecture-publish/) | 티스토리 JS 강의를 노션 체크리스트 순서대로 4개씩 네이버 `JavaScript 강의실`에 발행하고 제목을 통일한 뒤 체크합니다. |

### 네이버 운영과 진단

| 스킬 | 하는 일 |
|---|---|
| [`naver-search-check`](./naver-search-check/) | 글이 네이버 모바일 블로그탭 검색에 실제로 잡히는지 확인해 서치 블락, 색인 지연, 삭제·비공개를 구분합니다. |
| [`naver-photo-censor`](./naver-photo-censor/) | 살 노출 과다로 검색이 막힌 글의 사진에서 해당 부위만 소형 회색 박스로 가립니다. GIF는 전 프레임에 적용하고 원본을 백업합니다. |
| [`naver-unpublished-photos`](./naver-unpublished-photos/) | 발행된 글의 이미지 파일명과 로컬 폴더를 대조해 미수록 사진만 분류합니다. 파일명이 안 맞으면 dHash로 폴백합니다. |
| [`naver-to-tistory-backlink`](./naver-to-tistory-backlink/) | 네이버 글을 티스토리에 SEO 백링크용 정리본으로 발행합니다. 본문에 원문 링크 3종(m.blog, PC, PostView raw)을 박습니다. |

### 미디어 유틸

| 스킬 | 하는 일 |
|---|---|
| [`face-anonymizer`](./face-anonymizer/) | 폴더 안 사진 속 얼굴을 YuNet으로 검출해 원 또는 모자이크로 일괄 익명화합니다. 원본은 보존하고 별도 폴더에 저장합니다. |
| [`instagram-download`](./instagram-download/) | 공개 인스타그램 게시물 사진을 로그인 없이 받습니다. 캐러셀 전체 또는 `?img_index=N`으로 한 장만 받습니다. |
| [`youtube-music-download`](./youtube-music-download/) | 유튜브 영상을 mp3로 받습니다. 재생목록 파라미터를 무시하고, 403이 뜨면 yt-dlp를 자동 최신화한 뒤 재시도합니다. |

### 개인 기록과 조사

| 스킬 | 하는 일 |
|---|---|
| [`english-study`](./english-study/) | 복습 중심 영어 세션입니다. Leitner 간격 반복 단어 퀴즈와 과거 콩글리시 리라이팅을 먼저 하고, Reddit 뉴스 1건을 읽고 쓴 소감을 4단계로 교정합니다. Notion 단어장에 기록합니다. |
| [`job-application-tracker`](./job-application-tracker/) | 채용 공고 URL이나 JD를 읽어 Notion `지원 현황` DB에 회사·직무·기술스택·요구경력·근무지·적합도를 채우고 본문을 일관된 형식으로 씁니다. |
| [`game-progress-tracker`](./game-progress-tracker/) | 블로그 연재글로 게임 진행상황을 파악하고, 전체 구조와 대조해 남은 분량과 앞으로 나올 글 개수를 예측합니다. 노션 태스크보드에 할 일로 넣습니다. |
| [`stock-analysis`](./stock-analysis/) | 종목의 실시간 주가와 최신 실적, 공시, 뉴스를 모아 현황을 정리합니다. |
| [`naver-cafe-archive`](./naver-cafe-archive/) | 과거 네이버 카페에 쓴 글을 memberKey 기반으로 전수 발굴해 markdown으로 보관합니다. 닉네임이 카페마다 달라도 누락되지 않습니다. |

### 개발 보조

| 스킬 | 하는 일 |
|---|---|
| [`rebase-on-main`](./rebase-on-main/) | 현재 브랜치를 `origin/main` 위로 리베이스합니다. main을 진실로 보고 충돌 시 main을 채택하며, 백업 브랜치를 만들고 `force-with-lease`만 허용합니다. |

## 스킬 조합

스킬 대부분은 단독으로도 쓰지만 아래 순서로 이어 붙일 때 제 값을 합니다.

**새 글 쓰기**

```
/blog-learn                 코퍼스 생성 (최초 1회, 이후 --refresh)
/blog-topic-brief "<주제>"   모르는 주제면 사전조사부터
/blog-title "<주제>"         제목만 빠르게 뽑고 싶을 때
/blog "<주제>"               대본 + SmartEditor HTML + 자동 입력
/naver-blog-tags            발행 직전 태그 확정
```

**기존 글 옮기기**

플랫폼에 따라 진입점이 갈립니다. `tistory-to-naver`, `notion-to-naver`, `naver-to-naver`
셋 다 최종적으로 같은 SmartEditor 매크로를 씁니다.

**검색에 안 잡힐 때**

```
/naver-search-check         서치 블락인지 색인 지연인지 판별
/naver-photo-censor         노출 사유면 해당 부위만 가림
/naver-to-naver             가린 사진으로 재발행
/naver-search-check         색인 회복 확인
```

**사진 준비**

`face-anonymizer`로 행인 얼굴을 가리고 업로드한 뒤, `naver-unpublished-photos`로 빠뜨린
사진이 없는지 대조합니다.

## 저장소 구조

```
giraffe-skills/
├── <skill>/SKILL.md      스킬 정의 22개
├── <skill>/scripts/      그 스킬 전용 스크립트
├── _lib/                 여러 스킬이 공유하는 모듈
├── docs/                 설계 문서 (plans, specs)
└── scripts/              스킬에 속하지 않는 일회성 유틸
```

`_lib/`에 들어 있는 것입니다.

| 모듈 | 하는 일 | 쓰는 스킬 |
|---|---|---|
| `parse_smarteditor.py` | 네이버 SmartEditor HTML을 마크다운으로 변환 | `blog-learn`, `naver-to-tistory-backlink` |
| `inject_code_blocks.py` | 툴바 JS 클릭과 CGEvent 입력으로 native `se-code` 컴포넌트 주입 | `blog`, `notion-to-naver`, `tistory-to-naver` |
| `publish_with_category.py` | 발행 레이어를 열어 카테고리를 지정하고 공개 발행 | `tistory-to-naver`, `js-lecture-publish` |
| `naver_inspect.py` | 열려 있는 에디터 탭 상태 조회 (디버깅용) | 공통 |

`inject_code_blocks.py`, `publish_with_category.py`, `naver_inspect.py`와
`tistory-to-naver/scripts/`의 변환 엔진 6종은 2026-07-30에 외부 리포
`ParkGiraffe/tistory-to-naver-blog`에서 흡수했습니다. 그 리포는 더 쓰지 않습니다.

## 설치

```bash
git clone https://github.com/ParkGiraffe/giraffe-skills.git
cd giraffe-skills

mkdir -p ~/.claude/skills
for d in */SKILL.md; do
  name="$(dirname "$d")"
  target="$HOME/.claude/skills/$name"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "건너뜀 (실제 폴더가 이미 있음): $name"
    continue
  fi
  ln -sfn "$(pwd -P)/$name" "$target"
done
```

**심링크로 설치해야 합니다. 복사하면 안 됩니다.** 여러 스킬이 리포 루트의 `_lib/`을
참조하는데, 그 경로를 자기 파일 위치에서 거슬러 올라가 계산하기 때문입니다. 예를 들어
`blog-learn/scripts/fetch.py`는 이렇게 찾습니다.

```python
HERE = pathlib.Path(__file__).resolve().parent
PARSER = HERE.parent.parent / "_lib" / "parse_smarteditor.py"
```

`resolve()`가 심링크를 실제 리포 경로로 풀어주므로 심링크 설치에서는 `_lib`을 찾습니다.
반면 스킬 폴더만 `cp -R`로 복사하면 `_lib`이 따라가지 않아 `~/.claude/skills/_lib`을
찾다가 실패합니다.

`tistory-to-naver`와 `js-lecture-publish`는 `scripts/`와 `_lib/`을 함께 쓰므로 명령을
**리포 루트에서** 실행합니다. 각 SKILL.md에 적어두었습니다.

설치 후 새 세션에서 `/blog-learn`으로 코퍼스를 만드는 것부터 시작하면 됩니다.

## 종속성

Python 3.10+, macOS입니다. 스킬 상당수는 표준 라이브러리만 쓰지만 아래는 추가 설치가 필요합니다.

| 대상 | 필요한 것 |
|---|---|
| `tistory-to-naver` | `requests`, `beautifulsoup4`, `pyobjc-framework-Cocoa`, `pyobjc-framework-Quartz` |
| `_lib` 에디터 매크로 | `pyobjc-framework-Quartz` |
| `face-anonymizer` | `opencv-python-headless`, `numpy`, `pillow` |
| `naver-photo-censor`, `naver-unpublished-photos --hash` | `pillow` |
| `youtube-music-download` | `yt-dlp`, `ffmpeg` |

```bash
pip install --user requests beautifulsoup4 pyobjc-framework-Cocoa pyobjc-framework-Quartz \
                   opencv-python-headless numpy pillow yt-dlp
brew install ffmpeg
```

**macOS 권한.** 네이버 에디터에 자동 입력하는 스킬은 osascript와 CGEvent를 쓰므로 두 가지를
켜야 합니다.

- 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용에 터미널(또는 iTerm) 체크
- Chrome 메뉴 바 → 보기 → 개발자 → `Apple Events의 자바스크립트 허용` 체크

**Notion MCP.** `english-study`, `job-application-tracker`, `game-progress-tracker`,
`notion-to-naver`, `js-lecture-publish`는 Notion MCP 연결이 있어야 동작합니다.

## 하드룰

전체 규칙은 [`CLAUDE.md`](./CLAUDE.md)에 있습니다. 자주 걸리는 것만 옮깁니다.

- **이모지 금지.** 산출물 어디에도 한 글자도 쓰지 않습니다. Notion callout 아이콘도 포함합니다.
- **em dash(`—`) 금지.** 콜론이나 쉼표로 바꾸거나 문장을 나눕니다.
- **말투 모방 금지.** 코퍼스로 사용자 말투를 흉내내는 방식은 2026-06-16 피드백으로 폐기했습니다.
  기본 보이스는 군더더기 없는 분석글이고 모든 문장을 `~입니다` / `~합니다` 체로 씁니다.
- **고유명사 왜곡 금지.** 행사명, 브랜드명, 표준명을 임의로 줄이거나 바꾸지 않습니다.
- **카테고리는 실재하는 것만.** 코퍼스에 없는 카테고리를 새로 만들지 않습니다.
- **한글은 리터럴로 입력.** `\u` 이스케이프를 손으로 계산해 넣으면 글자가 어긋납니다.
  저장 후 다시 읽어 고유명사와 조사를 확인합니다.
- **무인 네이버 업로드 금지.** 발행은 사용자가 명시할 때만 하고 포커스 검증을 거칩니다
  (2026-06-16 사고 교훈).

## 스킬을 추가하거나 고칠 때

임의로 짜지 말고 스킬 작성 도구를 거칩니다. frontmatter 규칙과 trigger description,
디렉토리 구조를 도구가 강제하므로 trigger가 약한 스킬이나 `scripts` 없는 반쪽 스킬을 막아줍니다.
우선순위와 상세는 [`CLAUDE.md`](./CLAUDE.md)에 있습니다.

## 라이선스

[MIT](./LICENSE)
