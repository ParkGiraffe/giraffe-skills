#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""날짜 해석과 이름 규칙. 파일을 건드리지 않는 순수 계산입니다.

파일 mtime은 쓰지 않습니다. 복사와 이동으로 이미 오염됐습니다.
"""
import datetime as dt
import os
import pathlib
import re
import unicodedata as ud

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

# 날짜만 있고 시각이 없는 이름. Selfie_20240529_박기린퍼_000
# 시각을 모르므로 00:00:00 으로 둡니다. 날짜 자체는 진짜입니다.
FILENAME_DATE = "filename-date"
_DATE_ONLY = re.compile(r"(?<!\d)(20[0-2]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)")

# 에포크 밀리초. kakaotalk_1545297538011 / 1745920032694_100
# 카카오톡과 몇몇 앱이 받은 시각을 13자리 밀리초로 이름에 박습니다.
# 2001년부터 2035년 사이만 봅니다. 그 밖이면 다른 뜻의 숫자입니다.
_EPOCH_MS = re.compile(r"(?<!\d)(1[0-9]{12})(?!\d)")
_EPOCH_LO = 1_000_000_000_000   # 2001-09-09
_EPOCH_HI = 2_100_000_000_000   # 2036-07-18


def _parse_epoch_ms(stem):
    m = _EPOCH_MS.search(stem)
    if not m:
        return None
    value = int(m.group(1))
    if not _EPOCH_LO <= value <= _EPOCH_HI:
        return None
    try:
        return dt.datetime.fromtimestamp(value / 1000).replace(microsecond=0)
    except (OverflowError, OSError, ValueError):
        return None

# 날짜 출처 이름. 폴더에서 온 것은 정밀도가 달라서 따로 구분합니다.
FOLDER_MONTH = "folder-month"
FOLDER_YEAR = "folder-year"

# 원본 경로가 담은 연/월. 사용자가 손으로 정리해 둔 "2024/7월/포켓몬고페스트"
# 같은 폴더가 EXIF 가 벗겨진 사진의 유일한 단서입니다. mtime 과 달리 복사로
# 오염되지 않습니다. 사람이 적어 둔 것이기 때문입니다.
_YEAR_PART = re.compile(r"^(19|20)\d{2}$")
_MONTH_PART = re.compile(r"^(1[0-2]|0?[1-9])월?$")


def from_origin_path(origin):
    """원본 경로의 폴더 이름에서 (datetime, 출처) 를 찾습니다.

    연 폴더 바로 다음 조각이 월이면 월까지, 아니면 연만 씁니다. 날짜와 시각은
    모르므로 1일 0시로 채우고, 이름을 만들 때 time_stamp 가 00 으로 바꿉니다.
    """
    if not origin:
        return None, "unknown"
    parts = [ud.normalize("NFC", x) for x in pathlib.PurePosixPath(origin).parts]
    for i, part in enumerate(parts):
        if not _YEAR_PART.match(part):
            continue
        year = int(part)
        nxt = parts[i + 1] if i + 1 < len(parts) else ""
        m = _MONTH_PART.match(nxt)
        if m:
            return dt.datetime(year, int(m.group(1)), 1), FOLDER_MONTH
        return dt.datetime(year, 1, 1), FOLDER_YEAR
    return None, "unknown"

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


def resolve_datetime(basename, exif_dt, origin=None):
    """(datetime|None, 출처) 를 돌려줍니다. 출처는 exif / filename / unknown 입니다.

    EXIF 를 파일명보다 먼저 봅니다. 순서를 뒤집으면 안 됩니다. 실측으로 파일명에도
    날짜가 있는 5,232장 중 158장이 EXIF 와 어긋나는데, 어긋나는 쪽은 전부 파일명이
    틀렸습니다. KakaoTalk_Photo_2024-10-03-16-02-03 은 받아서 저장한 시각이고
    실제 촬영은 하루 전입니다(51장). iOS 내보내기는 파일명이 UTC 라 9시간씩
    어긋납니다(107장). EXIF 는 촬영 시각, 파일명은 저장 시각입니다.
    """
    got = _parse_exif(exif_dt)
    if got:
        return got, "exif"

    # 한글을 담은 패턴을 맞추기 전에 NFC 로 모읍니다. exFAT 은 파일명을 NFD 로
    # 돌려주는데 이 파일의 "오전|오후" 는 NFC 라 정규화 없이는 영영 안 맞습니다.
    # 맥 스크린샷 10장이 이것 때문에 통째로 미상날짜로 갔습니다.
    stem = os.path.splitext(ud.normalize("NFC", basename))[0]
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

    got = _parse_epoch_ms(stem)
    if got:
        return got, "filename"

    m = _DATE_ONLY.search(stem)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return dt.datetime(y, mo, d), FILENAME_DATE
        except ValueError:
            pass

    # 파일명에도 없으면 원본이 놓여 있던 폴더를 봅니다.
    return from_origin_path(origin)


def normalize_name(basename, when, src="exif"):
    """YYYYMMDD_HHMMSS_원본명.확장자 로 만듭니다. 이미 정규형이면 그대로 둡니다.

    resolve_datetime 과 같은 이유로 NFC 로 모읍니다. 아래에서 "스크린샷" 을
    글자로 찾기 때문입니다.
    """
    stem, ext = os.path.splitext(ud.normalize("NFC", basename))
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
    stamp = time_stamp(when, src)
    return f"{stamp}_{rest}{ext}" if rest else f"{stamp}{ext}"


def time_stamp(when, src="exif"):
    """이름 앞에 붙일 YYYYMMDD_HHMMSS 입니다.

    원본 폴더에서 연과 월만 알아낸 사진은 날짜 자리를 00 으로 둡니다. 00일은
    있을 수 없는 날짜라 "월까지만 안다"고 분명히 읽히고, 없는 날을 지어내지
    않으면서도 이름만으로 시간순 정렬되는 성질이 유지됩니다.
    """
    if src == FOLDER_MONTH:
        return f"{when.year:04d}{when.month:02d}00_000000"
    if src == FOLDER_YEAR:
        return f"{when.year:04d}0000_000000"
    return when.strftime("%Y%m%d_%H%M%S")


def event_folder_name(when, name):
    """YYYYMMDD_행사명. 여러 날에 걸친 행사는 시작일만 씁니다."""
    safe = name.replace("/", " ").replace("\\", " ").strip()
    return f"{when.strftime('%Y%m%d')}_{safe}"


def destination(kind, when, filename, event_folder=None, src="exif"):
    """갤러리 루트 기준 상대경로를 돌려줍니다.

    연만 알아낸 사진은 월 폴더를 정할 수 없으므로 미상날짜에 남깁니다. 월 폴더는
    항상 01 에서 12 여야 문자 정렬이 유지됩니다.
    """
    if when is None or src == FOLDER_YEAR:
        return f"_시스템/미상날짜/{filename}"
    ym = f"{when.year:04d}/{when.month:02d}"
    if event_folder:
        return f"사진/{ym}/{event_folder}/{filename}"
    if kind == "스크린샷":
        return f"스크린샷/{ym}/{filename}"
    return f"사진/{ym}/{filename}"
