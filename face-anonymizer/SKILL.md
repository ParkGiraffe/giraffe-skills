---
name: face-anonymizer
description: 폴더 안 사진 속 사람 얼굴을 자동으로 찾아 회색/검정/흰색 원 또는 모자이크로 가려 익명화합니다. 원본은 보존하고 별도 출력 폴더에 일괄 저장하며, 얼굴이 없는 사진도 그대로 포함해 폴더 전체를 한 번에 처리합니다. 사용 시점 — 사용자가 사진 폴더 경로를 주면서 "얼굴 가려줘", "얼굴 익명화", "모자이크", "얼굴 제거", "blur faces" 등을 블로그 업로드 전처리로 요청할 때.
---

# face-anonymizer — 사진 속 얼굴 일괄 익명화

블로그(스포츠데이·행사 사진 등)에 사람 얼굴이 그대로 나오면 프라이버시 문제가 생깁니다.
이 스킬은 폴더 안 모든 사진에서 얼굴을 자동 검출해 가린 뒤, 원본은 두고 출력 폴더에만 저장합니다.

이 스킬이 하는 일은 얼굴 정보를 **가려 없애는 것**(익명화)이지, 얼굴을 인식·수집·식별하는 것이 아닙니다.

## 언제 쓰나
- 행사·여행·일상 사진을 블로그에 올리기 전, 행인/관객 얼굴을 일괄로 가려야 할 때
- 폴더 하나를 통째로 처리하고 싶을 때 (얼굴 없는 사진도 출력에 포함되길 원할 때)
- 가림 모양(원/모자이크)·색·크기를 바꿔가며 여러 번 시도할 때

## 동작 원리
- **YuNet**(OpenCV `FaceDetectorYN`) ONNX 모델로 얼굴 박스 검출. 모델이 없으면 `~/.cache/face_anon`에 자동 다운로드.
- **EXIF Orientation 반영**: 휴대폰 사진은 회전 태그가 있는데 cv2는 무시하므로, PIL `exif_transpose`로 픽셀을 먼저 바로 세운 뒤 검출·저장.
- **다운스케일 검출**: 긴 변 1024로 줄여 검출하고 좌표를 원본 해상도로 환원 → 고해상도에서도 빠름.
- **리콜 우선**: 임계값을 낮게(기본 0.5) 둬서 "놓치는 것보다 살짝 과하게 덮는" 쪽으로. 프라이버시 안전쪽.
- **원본 보존**: 출력 폴더가 입력과 같으면 거부. 얼굴 미검출 사진도 그대로 출력에 복제.

## 실행 절차

```bash
python3 ./face-anonymizer/scripts/anonymize.py <SRC_DIR> [옵션]
```

옵션
- `--out DIR` — 출력 폴더 (기본 `<SRC>/tmp`). 원본과 같으면 에러.
- `--style circle|mosaic` — 가림 방식 (기본 `circle`)
- `--color gray|black|white|R,G,B` — circle 색 (기본 `gray` = 150,150,150)
- `--radius-k 0.75` — 가림 크기 = 얼굴 긴 변 × K. 키우면 더 넓게 덮음.
- `--score 0.5` — 검출 임계값. 낮추면 더 많이 잡음(작은/측면 얼굴), 너무 낮으면 오검출.
- `--limit N` — 앞 N장만 (전체 적용 전 테스트용)

### 예시

```bash
# 폴더 전체를 회색 원으로, <SRC>/tmp 에 저장
python3 face-anonymizer/scripts/anonymize.py "/Volumes/T7/블로그/임시/스포츠데이"

# 먼저 6장만 테스트
python3 face-anonymizer/scripts/anonymize.py "/path/사진" --limit 6

# 모자이크로, 더 공격적으로 검출
python3 face-anonymizer/scripts/anonymize.py "/path/사진" --style mosaic --score 0.4

# 추려둔 최종본만 다시 → complete 폴더
python3 face-anonymizer/scripts/anonymize.py "/path/사진/tmp" --out "/path/사진/complete"
```

## 권장 워크플로
1. `--limit 6`으로 먼저 돌려 검출 품질·색·크기를 눈으로 확인.
2. 색(`--color`)·크기(`--radius-k`)를 조정해 만족스러우면 전체 실행.
3. 블로그에 올릴 사진만 출력 폴더에서 추려, 그 추린 폴더를 다시 입력으로 한 번 더 돌리면(2차 패스) 1차에서 놓친 얼굴까지 잡힘.

## 한계
- 정면으로 또렷한 얼굴은 잘 잡지만, 아주 멀거나 옆/뒤로 돌아간 작은 얼굴은 놓칠 수 있음. `--score`를 낮추거나 2차 패스로 보완.
- `--score`를 너무 낮추면 얼굴 아닌 곳을 덮는 오검출이 늘어 사진을 해침.
- 출력은 항상 `.jpg`로 저장(품질 `--quality`, 기본 90). PNG 투명도는 보존되지 않음.
- 입력 폴더 바로 아래 이미지만 처리(하위 폴더 제외), `._`로 시작하는 macOS 메타데이터 파일은 자동 제외.

## 의존성
- `opencv-python-headless`, `numpy`, `pillow`
- 없으면: `pip install --user opencv-python-headless numpy pillow`
- YuNet 모델은 첫 실행 시 자동 다운로드(약 230KB).

## 파일
- `scripts/anonymize.py` — 실행 스크립트 본체
