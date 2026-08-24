#!/usr/bin/env python3
"""검출 v2 - 옆얼굴·작은 얼굴 리콜 강화.

기존 파이프라인이 놓친 원인:
  1) det_long=1024 다운스케일 → 멀리 있는 얼굴이 십수 픽셀로 뭉개짐
  2) YuNet은 정면 위주라 옆얼굴(프로필)을 자주 놓침

보강:
  - det_long 2048로 검출 (작은 얼굴)
  - score 0.35로 하향 (놓치는 것보다 과검출을 시트 검수로 거르는 쪽)
  - 좌우반전 이미지에서 한 번 더 검출 (반대편 프로필 회수)
  - Haar profileface 캐스케이드 양방향 (옆얼굴 전용 보조)
  - IoU 0.4로 union 병합
"""
import sys, os, json
sys.path.insert(0, "/Users/yosep/Desktop/Coding/giraffe-skills/face-anonymizer/scripts")
import cv2, numpy as np
from PIL import Image, ImageOps
import anonymize as A

SRC = sys.argv[1]
OUT = sys.argv[2]
model = A.ensure_model()
profile_xml = cv2.data.haarcascades + "haarcascade_profileface.xml"
profile = cv2.CascadeClassifier(profile_xml)


def iou(a, b):
    ax0, ay0, ax1, ay1 = a[0], a[1], a[0]+a[2], a[1]+a[3]
    bx0, by0, bx1, by1 = b[0], b[1], b[0]+b[2], b[1]+b[3]
    ix = max(0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    if inter <= 0: return 0.0
    return inter / (a[2]*a[3] + b[2]*b[3] - inter)


def merge(boxes, thr=0.4):
    out = []
    for b in boxes:
        for i, o in enumerate(out):
            if iou(b, o) > thr:
                # 더 큰 박스 유지
                if b[2]*b[3] > o[2]*o[3]:
                    out[i] = b
                break
        else:
            out.append(b)
    return out


def detect_all(bgr):
    H, W = bgr.shape[:2]
    boxes = []
    # 1) YuNet 고해상 + 저임계
    boxes += A.detect_faces(bgr, model, 2048, 0.35, 0.3, 5000, cv2)
    # 2) 좌우반전 YuNet (프로필 회수)
    flip = cv2.flip(bgr, 1)
    for (x, y, w, h) in A.detect_faces(flip, model, 2048, 0.35, 0.3, 5000, cv2):
        boxes.append((W - x - w, y, w, h))
    # 3) Haar 옆얼굴 (양방향) - 다운스케일에서
    scale = min(1.0, 1600 / max(H, W))
    small = cv2.resize(bgr, (int(W*scale), int(H*scale))) if scale < 1.0 else bgr
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    for g in (gray, cv2.flip(gray, 1)):
        det = profile.detectMultiScale(g, 1.1, 5, minSize=(28, 28))
        for (x, y, w, h) in det:
            if g is not gray:
                x = g.shape[1] - x - w
            boxes.append((x/scale, y/scale, w/scale, h/scale))
    return merge([tuple(float(v) for v in b) for b in boxes])


files = A.list_images(SRC)
res = {}
for p in files:
    name = os.path.basename(p)
    bgr = A.load_oriented(p, cv2, np, Image, ImageOps)
    res[name] = [[round(v, 1) for v in b] for b in detect_all(bgr)]

total = sum(len(v) for v in res.values())
print(f"총 {len(res)}장 / 박스 {total}개 / 검출 있는 사진 {sum(1 for v in res.values() if v)}장")
json.dump(res, open(OUT, "w"), ensure_ascii=False)
print("저장:", OUT)
