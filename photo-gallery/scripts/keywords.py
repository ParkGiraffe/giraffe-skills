#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XMP dc:subject 에 주제 키워드를 씁니다.

파일 자체에 박으므로 윈도우 탐색기, digiKam, Lightroom, Immich가 그대로 읽습니다.
확장속성(xattr)을 쓰지 않습니다. T7이 exFAT이라 파일마다 `._` 짝꿍이 생깁니다.

앱 이름은 references/vocab.md 를 정본으로 옮깁니다. 임의 음차와 직역을 하지 않습니다.
"""
import os
import pathlib
import re
import shutil
import subprocess

SS_APP = re.compile(r"^Screenshot_\d{8}[-_]\d{6}_(.+)$")


_HEADERS = {"앱 내부명", "표기", "잎", "계층"}


def _table_rows(path):
    """vocab.md 안의 모든 표 행을 (왼쪽, 오른쪽)으로 돌려줍니다.

    정규식으로 칸을 집으면 안 됩니다. 계층 표의 값에 `\\|` 가 들어 있어서
    `[^|]` 류의 패턴이 백슬래시에서 잘립니다. 이스케이프 안 된 파이프로 나눕니다.
    """
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if len(cells) < 2:
            continue
        left, right = cells[0], cells[1]
        if left in _HEADERS or not right:
            continue
        if set(left) <= set("-: ") or set(right) <= set("-: "):
            continue
        yield left, right


def load_vocab(path):
    """{앱 내부명: 표기}를 읽습니다.

    계층 표(오른쪽에 `|`가 있는 행)는 건너뜁니다. 같은 파일에 두 표가 있어서
    거르지 않으면 어휘가 오염됩니다.
    """
    return {left: right for left, right in _table_rows(path)
            if "|" not in right.replace("\\|", "|")}


def app_name(filename):
    """삼성 스크린샷 파일명에서 앱 내부명을 뽑습니다. 없으면 None입니다."""
    stem = pathlib.Path(filename).stem
    m = SS_APP.match(stem)
    return m.group(1).strip() if m else None


def collect(con, sha256, vocab):
    """그 사진에 붙일 키워드 목록입니다. 중복 없이 정렬해 돌려줍니다."""
    words = set()

    row = con.execute(
        "SELECT p.origin, p.kind, e.name FROM photo p"
        " LEFT JOIN event e ON e.id = p.event_id WHERE p.sha256=?", (sha256,)).fetchone()
    if row is None:
        return []
    origin, kind, event_name = row

    app = app_name(pathlib.Path(origin).name) if origin else None
    if app and app in vocab:
        words.add(vocab[app])

    for (tag,) in con.execute(
            "SELECT DISTINCT p.tag FROM blog_image i JOIN blog_post p ON p.log_no = i.log_no"
            " WHERE i.sha256=? AND p.tag IS NOT NULL", (sha256,)):
        words.add(tag)
    if con.execute("SELECT 1 FROM blog_image WHERE sha256=? LIMIT 1", (sha256,)).fetchone():
        words.add("블로그")

    if event_name:
        words.add(event_name)
    if kind == "스크린샷":
        words.add("스크린샷")

    for (word,) in con.execute("SELECT word FROM keyword WHERE sha256=?", (sha256,)):
        words.add(word)

    return sorted(words)


def load_hierarchy(path):
    """{잎: 상위|잎}을 읽습니다. 오른쪽에 `|`가 있는 행만 씁니다."""
    out = {}
    for leaf, full in _table_rows(path):
        full = full.replace("\\|", "|")
        if "|" in full:
            out[leaf] = full
    return out


def hierarchical(words, hier):
    """평평한 키워드 중 계층이 있는 것만 계층형으로 바꿉니다."""
    return sorted({hier[w] for w in words if w in hier})


def write(path, words, hier_words=None):
    """dc:Subject 에는 잎만, lr:HierarchicalSubject 에는 계층을 씁니다.

    둘을 나누는 이유는 윈도우 탐색기가 dc:Subject 만 읽기 때문입니다. 계층만 쓰면
    윈도우에 `포켓몬|포켓몬 GO` 라는 이상한 태그가 보입니다.
    원본 백업 파일(`_original`)을 남기지 않습니다.

    `+=`(추가)가 아니라 평범한 `=`를 단어마다 반복합니다. `+=`를 쓰면 "더하는
    거니까 맞다"고 되돌리기 쉬운데, 같은 명령에서 `=`(비우기) 뒤에 `+=`를 붙이면
    이미 값이 있던 파일에서는 비우기가 먹지 않고 옛 값에 새 값이 그냥 덧붙습니다
    (설치된 exiftool 13.55에서 실측). 리스트 태그에 평범한 `=`를 반복하면 앞의
    빈 대입이 기존 값을 제대로 지우면서 쌓이므로, 이 방식으로만 재기록이 안전합니다.
    """
    args = ["exiftool", "-overwrite_original", "-charset", "filename=utf8",
            "-codedcharacterset=utf8", "-XMP-dc:Subject=", "-XMP-lr:HierarchicalSubject="]
    for word in words:
        args.append(f"-XMP-dc:Subject={word}")
    for word in (hier_words or []):
        args.append(f"-XMP-lr:HierarchicalSubject={word}")
    args.append(str(path))
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode != 0:
        suffix = _real_suffix(res.stderr)
        if suffix is None:
            raise RuntimeError(f"exiftool 실패: {res.stderr.strip()}")
        _write_through_temp(pathlib.Path(path), suffix, args)
    remove_appledouble(path)


# "Not a valid PNG (looks more like a JPEG)" 처럼 내용과 확장자가 어긋난다는 말입니다.
_WRONG_TYPE = re.compile(r"looks more like an? (\w+)")
_SUFFIX = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "TIFF": ".tif",
           "HEIF": ".heic", "WEBP": ".webp", "MP4": ".mp4", "MOV": ".mov"}


def _real_suffix(stderr):
    """exiftool 이 말한 진짜 형식의 확장자입니다. 다른 오류면 None 입니다."""
    m = _WRONG_TYPE.search(stderr)
    return _SUFFIX.get(m.group(1).upper()) if m else None


def _write_through_temp(path, suffix, args):
    """확장자가 내용과 다른 파일에 키워드를 씁니다.

    exiftool 은 확장자와 내용이 어긋나면 쓰기를 거부합니다. -m 으로도 안 됩니다
    (13.55 실측). T7 에 이름만 .PNG 인 JPEG 가 5장 있어 실제로 부딪혔습니다.
    제대로 된 확장자를 붙인 사본에 쓰고 원본 자리에 되돌려 놓습니다.

    임시 파일을 같은 폴더에 둡니다. os.replace 는 같은 파일시스템 안에서만
    원자적이라, 다른 곳에 두고 베껴 오면 되돌리는 도중에 죽었을 때 사진이
    잘립니다. 이름을 점으로 시작해 scan 의 훑기에서 빠지게 합니다.
    """
    tmp = path.parent / f".{path.stem}_키워드작업{suffix}"
    try:
        shutil.copy(path, tmp)
        res = subprocess.run(args[:-1] + [str(tmp)], capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"exiftool 실패: {res.stderr.strip()}")
        os.replace(tmp, path)
    finally:
        remove_appledouble(tmp)
        try:
            tmp.unlink()
        except OSError:
            pass


def remove_appledouble(path):
    """exiftool 이 남긴 "._이름" 짝꿍 파일을 지웁니다.

    macOS 는 파일을 쓴 프로세스를 기록하려고 com.apple.provenance 확장속성을
    붙입니다. T7 은 exFAT 이라 확장속성을 담을 자리가 없어서 파일마다 4KB 짜리
    짝꿍이 생기고, 이 디스크를 윈도우에 꽂으면 전부 보입니다. 이 프로젝트가
    shutil.copy2 를 금지한 것과 같은 이유입니다.

    -overwrite_original 도 -overwrite_original_in_place 도 이것을 막지
    못합니다(exiftool 13.55 실측). 그래서 쓰고 나서 치웁니다. 방금 우리가 건드린
    그 파일의 짝꿍만 지웁니다. 폴더를 쓸어 담지 않습니다.
    """
    path = pathlib.Path(path)
    for name in (f"._{path.name}", f"._{path.name}_exiftool_tmp"):
        try:
            (path.parent / name).unlink()
        except OSError:
            pass


def _read_field(path, field):
    """설치된 exiftool(13.55)은 -sep 인자의 `\\n`을 실제 줄바꿈으로 바꾸지 않고
    글자 그대로(`\\`, `n`) 돌려준다. splitlines()가 아니라 그 리터럴 문자열로 나눈다."""
    res = subprocess.run(
        ["exiftool", "-charset", "filename=utf8", "-s3", "-sep", "\\n",
         field, str(path)],
        capture_output=True, text=True)
    if res.returncode != 0:
        return []
    out = res.stdout.strip()
    if not out:
        return []
    return [v for v in out.split("\\n") if v]


def read(path):
    """검증용. dc:Subject 를 읽습니다."""
    return _read_field(path, "-XMP-dc:Subject")


def read_hierarchy(path):
    """검증용. lr:HierarchicalSubject 를 읽습니다."""
    return _read_field(path, "-XMP-lr:HierarchicalSubject")
