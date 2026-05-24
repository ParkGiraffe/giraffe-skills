#!/usr/bin/env python3
"""사진 속 사람 얼굴을 자동으로 가려 익명화한다 (프라이버시 보호).

OpenCV YuNet 얼굴검출로 얼굴 위치를 찾아 채운 원 또는 모자이크로 가린다.
원본은 절대 덮어쓰지 않고 별도 출력 폴더에만 저장하며, 얼굴이 검출되지
않은 사진도 그대로 출력 폴더에 복제해 폴더 단위 일괄 처리를 보장한다.

핵심 처리:
- EXIF Orientation 반영(휴대폰 사진 회전) 후 검출/저장 → 표시 일관성
- 긴 변 기준 다운스케일에서 검출 후 좌표를 원본 해상도로 환원 → 속도
- 검출 임계값을 낮춰 리콜 우선(놓침 < 과덮음) → 프라이버시 안전쪽
- YuNet ONNX 모델은 없으면 자동 다운로드(~/.cache/face_anon)

사용법:
    anonymize.py <SRC_DIR> [--out DIR] [--style circle|mosaic]
                 [--color gray|black|white|R,G,B] [--radius-k 0.75]
                 [--score 0.5] [--passes 1]

예시:
    anonymize.py "/path/사진폴더"
    anonymize.py "/path/사진폴더" --out "/path/사진폴더/complete" --color gray
    anonymize.py "/path/사진폴더" --style mosaic --score 0.4
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import urllib.request

MODEL_DIR = os.path.expanduser("~/.cache/face_anon")
MODEL_PATH = os.path.join(MODEL_DIR, "face_detection_yunet_2023mar.onnx")
MODEL_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
EXTS = ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG")
COLOR_PRESETS = {  # BGR
    "gray": (150, 150, 150),
    "grey": (150, 150, 150),
    "black": (0, 0, 0),
    "white": (255, 255, 255),
}


def ensure_model() -> str:
    if not os.path.exists(MODEL_PATH):
        os.makedirs(MODEL_DIR, exist_ok=True)
        print(f"YuNet 모델 다운로드 중 → {MODEL_PATH}")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


def parse_color(spec: str):
    spec = spec.strip().lower()
    if spec in COLOR_PRESETS:
        return COLOR_PRESETS[spec]
    parts = spec.split(",")
    if len(parts) == 3:
        try:
            r, g, b = (int(p) for p in parts)
            return (b, g, r)  # BGR
        except ValueError:
            pass
    sys.exit(f"색상 형식 오류: {spec} (gray/black/white 또는 'R,G,B')")


def load_oriented(path, cv2, np, Image, ImageOps):
    """PIL로 EXIF 회전 반영 후 BGR ndarray 반환."""
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    im = im.convert("RGB")
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def detect_faces(bgr, model, det_long, score, nms, topk, cv2):
    h, w = bgr.shape[:2]
    scale = min(1.0, det_long / max(h, w))
    small = (
        cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else bgr
    )
    sh, sw = small.shape[:2]
    det = cv2.FaceDetectorYN.create(model, "", (sw, sh), score, nms, topk)
    det.setInputSize((sw, sh))
    _, faces = det.detect(small)
    out = []
    if faces is not None:
        for f in faces:
            x, y, fw, fh = f[:4]
            out.append((x / scale, y / scale, fw / scale, fh / scale))
    return out


def cover_circle(bgr, faces, color, radius_k, cv2):
    for (x, y, fw, fh) in faces:
        cx, cy = int(x + fw / 2), int(y + fh / 2)
        r = int(max(fw, fh) * radius_k)
        cv2.circle(bgr, (cx, cy), r, color, thickness=-1, lineType=cv2.LINE_AA)
    return bgr


def cover_mosaic(bgr, faces, radius_k, cv2):
    h, w = bgr.shape[:2]
    for (x, y, fw, fh) in faces:
        r = int(max(fw, fh) * radius_k)
        cx, cy = int(x + fw / 2), int(y + fh / 2)
        x0, y0 = max(0, cx - r), max(0, cy - r)
        x1, y1 = min(w, cx + r), min(h, cy + r)
        roi = bgr[y0:y1, x0:x1]
        if roi.size == 0:
            continue
        small = cv2.resize(roi, (max(1, (x1 - x0) // 12), max(1, (y1 - y0) // 12)),
                           interpolation=cv2.INTER_LINEAR)
        bgr[y0:y1, x0:x1] = cv2.resize(small, (x1 - x0, y1 - y0),
                                       interpolation=cv2.INTER_NEAREST)
    return bgr


def list_images(src):
    files = []
    for pat in EXTS:
        files += glob.glob(os.path.join(src, pat))
    # 같은 파일이 대/소문자 패턴에 중복 매칭될 수 있어 정규화 후 중복 제거
    seen, uniq = set(), []
    for f in sorted(files):
        key = os.path.normcase(os.path.abspath(f))
        if key in seen:
            continue
        if os.path.dirname(f) != src:  # 하위 폴더 제외
            continue
        seen.add(key)
        uniq.append(f)
    return uniq


def main():
    ap = argparse.ArgumentParser(description="폴더 안 사진의 얼굴을 일괄 익명화")
    ap.add_argument("src", help="입력 폴더 (이 폴더의 이미지만, 하위폴더 제외)")
    ap.add_argument("--out", help="출력 폴더 (기본: <src>/tmp). 원본은 보존")
    ap.add_argument("--style", choices=["circle", "mosaic"], default="circle")
    ap.add_argument("--color", default="gray", help="circle 색 (gray/black/white 또는 R,G,B)")
    ap.add_argument("--radius-k", type=float, default=0.75, help="가림 크기 = max(w,h)*K")
    ap.add_argument("--score", type=float, default=0.5, help="검출 임계값(낮을수록 많이 잡음)")
    ap.add_argument("--det-long", type=int, default=1024, help="검출용 다운스케일 긴 변")
    ap.add_argument("--nms", type=float, default=0.3)
    ap.add_argument("--topk", type=int, default=5000)
    ap.add_argument("--quality", type=int, default=90, help="JPEG 저장 품질")
    ap.add_argument("--limit", type=int, default=0, help="앞 N장만 처리(테스트용, 0=전체)")
    args = ap.parse_args()

    try:
        import numpy as np
        import cv2
        from PIL import Image, ImageOps
    except ModuleNotFoundError as e:
        sys.exit(f"의존성 누락: {e}. 먼저: pip install --user opencv-python-headless numpy pillow")

    src = os.path.abspath(os.path.expanduser(args.src))
    if not os.path.isdir(src):
        sys.exit(f"입력 폴더가 없음: {src}")
    out = os.path.abspath(os.path.expanduser(args.out)) if args.out else os.path.join(src, "tmp")
    if os.path.normcase(out) == os.path.normcase(src):
        sys.exit("출력 폴더가 입력 폴더와 같으면 원본을 덮어씀 — 다른 --out 지정")
    os.makedirs(out, exist_ok=True)

    model = ensure_model()
    color = parse_color(args.color)

    files = list_images(src)
    if args.limit:
        files = files[: args.limit]
    print(f"대상 {len(files)}장 · 스타일 {args.style} · 출력 → {out}")

    total_faces, no_face = 0, []
    for i, path in enumerate(files, 1):
        name = os.path.basename(path)
        try:
            bgr = load_oriented(path, cv2, np, Image, ImageOps)
        except Exception as e:
            print(f"[{i}/{len(files)}] {name}  읽기실패: {e}")
            continue
        faces = detect_faces(bgr, model, args.det_long, args.score, args.nms, args.topk, cv2)
        total_faces += len(faces)
        if not faces:
            no_face.append(name)
        if args.style == "mosaic":
            cover_mosaic(bgr, faces, args.radius_k, cv2)
        else:
            cover_circle(bgr, faces, color, args.radius_k, cv2)
        stem = os.path.splitext(name)[0]
        out_path = os.path.join(out, stem + ".jpg")
        cv2.imwrite(out_path, bgr, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
        print(f"[{i}/{len(files)}] {name}  얼굴 {len(faces)}개")

    print("=" * 40)
    print(f"처리 {len(files)}장 / 얼굴 총 {total_faces}개 / 얼굴 미검출 {len(no_face)}장")
    if no_face:
        shown = ", ".join(no_face[:40])
        print("미검출:", shown, ("..." if len(no_face) > 40 else ""))


if __name__ == "__main__":
    main()
