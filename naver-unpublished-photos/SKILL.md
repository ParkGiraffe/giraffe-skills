---
name: naver-unpublished-photos
description: 네이버 블로그 글에 올라가지 않은 로컬 사진을 찾아 '미수록' 폴더로 자동 분류합니다. 발행 글의 이미지 파일명과 로컬 폴더 파일명을 대조해 미수록분만 추려 이동(또는 복사)합니다. 사용 시점 — 사용자가 네이버 블로그 글 URL과 로컬 사진 폴더를 함께 주면서 "여기 안 올라온 사진 찾아줘", "미수록 사진 분류", "발행 안 된 것만 빼줘" 등을 요청할 때.
---

# naver-unpublished-photos — 네이버 글 미수록 사진 분류

행사 사진을 잔뜩 찍어 폴더에 두고, 그중 일부만 블로그에 올린 뒤
"안 올린 것만 따로 모으고 싶다"는 상황에서 씁니다.

## 언제 쓰나
- 로컬 폴더의 사진 중 특정 네이버 글에 발행된 것 / 안 된 것을 가르고 싶을 때
- 미수록분만 `미수록` 하위 폴더로 모아 재활용(다른 글·다른 SNS)하려 할 때

## 동작 원리 (핵심 트릭)
네이버 블로그 발행 이미지 URL 경로에는 **업로드 당시의 원본 파일명이 그대로 보존**됩니다.
예: `https://postfiles.pstatic.net/…/20260524_124423.jpg?type=w80_blur` → `20260524_124423.jpg`

1. `PostView.naver?blogId=&logNo=` 로 글 HTML을 받음
2. `<img class="se-image-resource" src=...>` 태그에서 src basename(파일명) 집합 추출 (URL 디코딩)
3. 로컬 폴더 파일명 집합과 **차집합** → 로컬에만 있는 것이 미수록
4. 미수록분을 `<폴더>/미수록` 으로 이동(기본) 또는 복사

파일명이 하나도 안 겹치면(업로드 시 리네임된 글) 자동으로 `--hash` 폴백:
발행 이미지를 받아 dHash를 구하고 로컬과 해밍거리로 매칭해 미수록을 판별합니다.

## 실행 절차

```bash
python3 ./naver-unpublished-photos/scripts/classify.py <BLOG_URL> <LOCAL_DIR> [옵션]
```

옵션
- `--dry-run` — 실제 이동 없이 미수록 목록·개수만 출력 (먼저 이걸로 확인 권장)
- `--copy` — 이동 대신 복사(원본 폴더 그대로 유지)
- `--dest 미수록` — 만들 하위 폴더명(기본 `미수록`)
- `--hash` — 파일명 대신 dHash 내용 매칭 강제
- `--threshold 8` — dHash 해밍거리 매칭 임계(작을수록 엄격)

### 예시

```bash
# 먼저 미수록 목록만 확인
python3 naver-unpublished-photos/scripts/classify.py \
  "https://blog.naver.com/op5321/224295471965" "/Volumes/T7/.../output" --dry-run

# 확정: 미수록분을 output/미수록 으로 이동
python3 naver-unpublished-photos/scripts/classify.py \
  "https://blog.naver.com/op5321/224295471965" "/Volumes/T7/.../output"

# 원본 보존하며 복사만
python3 naver-unpublished-photos/scripts/classify.py "<URL>" "/path/output" --copy
```

## 권장 워크플로
1. `--dry-run`으로 미수록 개수와 발행 파일명 일치 수를 먼저 확인.
2. "발행 파일명 N개 (로컬과 일치 M개)" 출력에서 M이 0이 아니면 파일명 매칭 신뢰 가능.
3. 확정 시 옵션 없이(이동) 또는 `--copy`로 실행.

## 한계
- 파일명 매칭은 네이버가 이름을 보존할 때만 정확. 외부에서 받은/리네임된 이미지는 `--hash` 폴백 필요.
- 발행글에 폴더 외부 이미지(밈·스티커 등)가 섞여 있으면 발행 집합에 잡히지만 로컬에 없어 무시됨(미수록 판정에는 영향 없음).
- `--hash` 모드는 발행 이미지를 모두 받아야 해 느리고, 심하게 크롭/보정된 사진은 놓칠 수 있음.
- 입력 폴더 바로 아래 이미지만 대상(하위 폴더 제외), `._` macOS 메타파일은 동반 이동.

## 의존성
- 기본(파일명) 모드: 표준 라이브러리만 (`urllib`, `re`). 추가 설치 불필요.
- `--hash` 모드: `pillow` (`pip install --user pillow`)

## 파일
- `scripts/classify.py` — 실행 스크립트 본체
