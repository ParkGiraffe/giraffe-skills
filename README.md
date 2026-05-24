# giraffe-skills

박기린(`op5321` / 박기린의 기린파크)이 직접 사용하는 Claude Code용 개인 스킬 모음.

> 스킬은 Claude Code에서 `~/.claude/skills/<name>/SKILL.md` 형태로 설치하면 자동 인식됩니다.
## 수록 스킬

| 스킬 | 한 줄 요약 |
|---|---|
| [`blog-learn`](./blog-learn/) | 네이버 블로그 전체 글을 긁어와 `./.claude/blog-corpus/`에 캐시하고 스타일 가이드를 생성 |
| [`blog`](./blog/) | 코퍼스를 근거로 박기린 말투의 블로그 초안 + SmartEditor HTML + 제목 후보를 생성하고, 네이버 에디터에 자동 paste |
| [`blog-title`](./blog-title/) | 코퍼스의 카테고리별 `[]` 태그 컨벤션을 학습해 새 글의 제목 후보 5개를 추천 |
| [`blog-topic-brief`](./blog-topic-brief/) | 잘 모르는 주제를 웹 검색으로 사전조사한 뒤 팩트 정리 + 코퍼스/일반 SEO 두 갈래 제목 + 태그 10~12개 브리프 |
| [`instagram-download`](./instagram-download/) | 공개 인스타그램 게시물의 사진을 로그인 없이 캐러셀 통째로 또는 N번째 한 장만 `~/Downloads`로 저장 |
| [`tistory-to-naver`](./tistory-to-naver/) | Tistory 게시물을 네이버 블로그 에디터로 자동 마이그레이션 (헤딩·구분선·이미지 보존, `/blog`와 동일한 SmartEditor 스타일) |
| [`naver-to-tistory-backlink`](./naver-to-tistory-backlink/) | 네이버 블로그 글을 티스토리에 SEO 백링크용 "정리본"으로 자동 발행 (claude-in-chrome으로 티스토리 글쓰기 페이지 조작, 본문에 m.blog + PC + PostView raw 3개 백링크 박음) |
| [`face-anonymizer`](./face-anonymizer/) | 폴더 안 사진 속 얼굴을 YuNet으로 자동 검출해 회색/검정/흰색 원 또는 모자이크로 일괄 익명화 (원본 보존, 별도 출력 폴더, 얼굴 없는 사진도 포함) |

블로그 스킬 세 개(`blog-learn` / `blog` / `blog-title`)는 함께 쓰도록 설계됐습니다: `blog-learn`이 코퍼스를 만들고, `blog`/`blog-title`이 그 코퍼스를 읽어 결과를 만듭니다. `instagram-download`와 `tistory-to-naver`, `naver-to-tistory-backlink`, `face-anonymizer`는 독립 유틸리티 — 블로그 글에 인스타 게시물 이미지를 가져오거나, 기존 Tistory 글을 네이버로 옮기거나, 네이버 글을 티스토리에 미러링해 구글 검색 노출을 노리거나, 행사 사진을 올리기 전 행인 얼굴을 가릴 때 단발적으로 씁니다.

리포 상위 `_lib/` 폴더에는 여러 스킬이 공유하는 모듈이 있습니다 (현재: `parse_smarteditor.py` — 네이버 SmartEditor HTML을 마크다운으로 변환. `blog-learn`과 `naver-to-tistory-backlink`가 공유).

## 설치

```bash
# 1) 클론
git clone https://github.com/ParkGiraffe/giraffe-skills.git
cd giraffe-skills

# 2) 사용할 스킬을 ~/.claude/skills/ 로 심볼릭 링크
mkdir -p ~/.claude/skills
ln -s "$(pwd)/blog"                ~/.claude/skills/blog
ln -s "$(pwd)/blog-learn"          ~/.claude/skills/blog-learn
ln -s "$(pwd)/blog-title"          ~/.claude/skills/blog-title
ln -s "$(pwd)/blog-topic-brief"    ~/.claude/skills/blog-topic-brief
ln -s "$(pwd)/instagram-download"  ~/.claude/skills/instagram-download
ln -s "$(pwd)/tistory-to-naver"    ~/.claude/skills/tistory-to-naver
ln -s "$(pwd)/naver-to-tistory-backlink" ~/.claude/skills/naver-to-tistory-backlink
ln -s "$(pwd)/face-anonymizer"     ~/.claude/skills/face-anonymizer
```

심링크 대신 복사도 가능 (`cp -R blog ~/.claude/skills/`). 단 심링크가 git pull 한 번으로 업데이트되어 편합니다.

설치 후 Claude Code 새 세션에서 `/blog-learn` 입력으로 코퍼스 빌드부터 시작하면 됩니다.

## 워크플로

```
/blog-learn             →  ./.claude/blog-corpus/ 생성 (한 번만 또는 --refresh로 증분)
/blog-title "<주제>"     →  카테고리 컨벤션 기반 제목 후보 5개
/blog "<주제>"           →  대본 + SmartEditor HTML + 제목 후보 5개 + 자동 paste
```

`/blog`는 본문 자동 작성까지 가는 풀파이프라인, `/blog-title`은 제목만 빠르게 뽑는 가벼운 진입점입니다.

## 종속성

- Python 3.10+
- 표준 라이브러리만 사용 (외부 패키지 없음)
- macOS의 자동 paste 매크로(`paste_to_naver.py`)는 `osascript` + `시스템 설정 → 손쉬운 사용` 권한 필요

## 하드룰 (모든 스킬 공통)

- **이모지 절대 금지**. 산출물 어디에도 단 한 글자도 쓰지 않음.
- **고유명사 왜곡 금지**. 행사명·브랜드명을 임의로 줄이거나 변형하지 않음 (예: "서울 키보드 박람회"를 "키보드 쇼"로 바꾸지 않음).
- **카테고리는 코퍼스에 실제 존재하는 것만**. 새 카테고리 임의 생성 금지.

## 라이선스

[MIT](./LICENSE)
