---
name: instagram-download
description: 공개 인스타그램 게시물의 사진을 로그인 없이 다운로드합니다. instagram.com/p/<코드>/ URL을 받으면 캐러셀 전체 또는 ?img_index=N 으로 지정한 한 장만 ~/Downloads(또는 --out)로 저장합니다. 사용 시점 — 사용자가 인스타 게시물 링크를 주면서 "이미지 받아줘", "다운로드", "사진 저장" 등을 요청할 때. yt-dlp / gallery-dl / instaloader가 모두 로그인 벽에 막힐 때의 우회 경로.
---

# instagram-download — 인스타그램 게시물 사진 다운로드

박기린이 자주 쓰는 패턴: 인스타 게시물 링크를 주면 캐러셀 전체를 `~/Downloads`로 받아오기.
yt-dlp·gallery-dl·instaloader는 2025년 기준 비로그인 상태에서 모두 로그인 페이지로 리다이렉트당해 실패하므로, 이 스킬은 다른 경로를 씁니다.

## 언제 쓰나
- 사용자가 `https://www.instagram.com/p/<shortcode>/` 또는 `?img_index=N` 붙은 링크를 주면서 다운로드 요청할 때
- 캐러셀 게시물 전체 다운로드가 필요할 때
- 다른 다운로드 도구가 `HTTP redirect to login page` 에러로 실패했을 때

## 동작 원리 (핵심 트릭)

인스타그램은 일반 브라우저 UA에는 로그인 페이지를 돌려주지만 **Googlebot UA에는 임베디드 JSON이 박힌 풀 페이지**를 그대로 서빙합니다. 그 안에 `"carousel_media":[…]` 배열이 있고, 각 아이템의 `image_versions2.candidates[0].url`이 실제 CDN 이미지 URL입니다.

1. `User-Agent: Googlebot/2.1`로 게시물 페이지를 `curl`
2. 페이지에는 추천글 캐러셀도 같이 들어있으므로, 대상 shortcode 바로 뒤에 오는 `carousel_media` 배열만 골라냄
3. 균형 괄호 파서로 JSON 배열만 잘라내 `json.loads`
4. 각 아이템의 첫 번째 candidate URL을 일반 Chrome UA로 다운로드

비-캐러셀(단일 이미지) 게시물은 `og:image` 메타태그 폴백이 동작합니다.

## 실행 절차

```bash
python3 ./instagram-download/scripts/download.py <URL> [--index N] [--out DIR]
```

옵션
- `--index N` (생략 시 전체) — 캐러셀에서 N번째(1-base) 한 장만
- `--out DIR` (기본 `~/Downloads`) — 저장 폴더

저장 파일명은 `instagram_<shortcode>_<idx>.jpg` 형태로 고정 — 같은 게시물 재실행 시 idempotent.

### 예시

```bash
# 게시물 전체
python3 scripts/download.py 'https://www.instagram.com/p/DX6ePKqj7Ny/'

# 두 번째 사진만
python3 scripts/download.py 'https://www.instagram.com/p/DX6ePKqj7Ny/?img_index=2' --index 2

# 다른 폴더로
python3 scripts/download.py 'https://www.instagram.com/p/DX6ePKqj7Ny/' --out ~/Pictures
```

## 한계

- 공개 게시물만. 비공개 계정은 Googlebot UA에도 로그인 벽이 떨어집니다.
- 캐러셀 안의 동영상 항목은 정지 이미지(커버)만 받고 `.mp4`는 받지 않습니다 — 이 경로로는 비디오 URL이 노출되지 않음.
- 인스타가 JSON 스키마를 바꾸면 `image_versions2 → candidates[0].url` 필드 이름 확인 필요.
- 받은 이미지의 재배포는 원작자 저작권 문제가 있으니 개인 용도로만 쓸 것.

## 의존성

표준 라이브러리만 사용 (`urllib`, `json`, `re`). 추가 설치 불필요.

## 파일

- `scripts/download.py` — 실행 스크립트 본체
