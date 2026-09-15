#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""날짜 해석과 이름 규칙. 파일을 건드리지 않는 순수 계산입니다.

파일 mtime은 쓰지 않습니다. 복사와 이동으로 이미 오염됐습니다.
"""
import datetime as dt
import os
import re

# 이미 정규형인가: 20240108_072733_IMG_1027.PNG / 20181121_180959.jpg
NORMALIZED = re.compile(r"^(\d{8})_(\d{6})(?:_(.*))?$")

# 파일명에서 날짜를 뽑는 규칙. 위에서부터 먼저 맞는 것을 씁니다.
_PATTERNS = [
    # Screenshot_20260501_155542_앱 / Screenshot_20181127-151357_앱
    (re.compile(r"^Screenshot_(\d{4})(\d{2})(\d{2})[-_](\d{2})(\d{2})(\d{2})"), "ymdhms"),
    # 20201115_072644083_iOS (밀리초 3자리)
    # 끝을 \b 로 막으면 안 됩니다. 밀리초 뒤에 오는 "_" 도 단어문자라 경계가
    # 생기지 않아 493개가 통째로 안 잡힙니다. 형제 패턴들과 같이 (?!\d) 를 씁니다.
    (re.compile(r"^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\d{3}(?!\d)"), "ymdhms"),
    # 20240108_072733 / 20181216-135720
    (re.compile(r"^(\d{4})(\d{2})(\d{2})[-_](\d{2})(\d{2})(\d{2})(?!\d)"), "ymdhms"),
    # 별이되어라_2018-12-20-00-13-57
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})"), "ymdhms"),
    # 2024.11.29 - 00.42.30.13  (언리얼 Shipping 스크린샷)
    (re.compile(r"(\d{4})\.(\d{2})\.(\d{2})\s*-\s*(\d{2})\.(\d{2})\.(\d{2})"), "ymdhms"),
    # 스크린샷 2024-12-21 145611
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2})(\d{2})(\d{2})(?!\d)"), "ymdhms"),
]

# 스크린샷 2024-12-26 오후 5.22.13
_AMPM = re.compile(r"(\d{4})-(\d{2})-(\d{2})\s+(오전|오후)\s+(\d{1,2})\.(\d{2})\.(\d{2})")

# 정규화할 때 떼어낼 날짜 접두. (정규식, 나머지를 담은 그룹 번호)
_STRIP = [
    (re.compile(r"^Screenshot_\d{8}[-_]\d{6}_(.+)$"), 1),
    (re.compile(r"^Screenshot_\d{8}[-_]\d{6}$"), None),          # 나머지 = "Screenshot"
    (re.compile(r"^\d{8}_\d{6}\d{3}_(.+)$"), 1),                  # iOS 밀리초
    (re.compile(r"^(.+?)_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$"), 1),
    (re.compile(r"^(.+?)\s+Screenshot \d{4}\.\d{2}\.\d{2}.*$"), 1),
    (re.compile(r"^\d{8}[-_]\d{6}$"), None),                      # 나머지 = ""
]


def _parse_ampm(stem):
    m = _AMPM.search(stem)
    if not m:
        return None
    y, mo, d, ap, h, mi, s = m.groups()
    h = int(h) % 12
    if ap == "오후":
        h += 12
    try:
        return dt.datetime(int(y), int(mo), int(d), h, int(mi), int(s))
    except ValueError:
        return None


def _parse_exif(value):
    if not value:
        return None
    v = str(value).strip()
    if not v or v.startswith("0000"):
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S%z"):
        try:
            return dt.datetime.strptime(v[:19], fmt[:19] if "%z" not in fmt else fmt)
        except ValueError:
            continue
    return None


def resolve_datetime(basename, exif_dt):
    """(datetime|None, 출처) 를 돌려줍니다. 출처는 exif / filename / unknown 입니다."""
    got = _parse_exif(exif_dt)
    if got:
        return got, "exif"

    stem = os.path.splitext(basename)[0]
    got = _parse_ampm(stem)
    if got:
        return got, "filename"
    for rx, _kind in _PATTERNS:
        m = rx.search(stem)
        if not m:
            continue
        y, mo, d, h, mi, s = (int(x) for x in m.groups()[:6])
        try:
            return dt.datetime(y, mo, d, h, mi, s), "filename"
        except ValueError:
            continue
    return None, "unknown"


def normalize_name(basename, when):
    """YYYYMMDD_HHMMSS_원본명.확장자 로 만듭니다. 이미 정규형이면 그대로 둡니다."""
    stem, ext = os.path.splitext(basename)
    if NORMALIZED.match(stem):
        return basename

    rest = None
    for rx, group in _STRIP:
        m = rx.match(stem)
        if not m:
            continue
        if group is None:
            rest = "Screenshot" if stem.startswith("Screenshot_") else ""
        else:
            rest = m.group(group)
        break
    if rest is None:
        if _AMPM.search(stem) or re.search(r"\d{4}-\d{2}-\d{2}\s+\d{6}", stem):
            rest = "스크린샷" if "스크린샷" in stem else "Screenshot"
        else:
            rest = stem

    rest = rest.strip()
    stamp = when.strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{rest}{ext}" if rest else f"{stamp}{ext}"


def event_folder_name(when, name):
    """YYYYMMDD_행사명. 여러 날에 걸친 행사는 시작일만 씁니다."""
    safe = name.replace("/", " ").replace("\\", " ").strip()
    return f"{when.strftime('%Y%m%d')}_{safe}"


def destination(kind, when, filename, event_folder=None):
    """갤러리 루트 기준 상대경로를 돌려줍니다."""
    if when is None:
        return f"_시스템/미상날짜/{filename}"
    ym = f"{when.year:04d}/{when.month:02d}"
    if event_folder:
        return f"사진/{ym}/{event_folder}/{filename}"
    if kind == "스크린샷":
        return f"스크린샷/{ym}/{filename}"
    return f"사진/{ym}/{filename}"
