#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계획대로 파일을 복사합니다. 원본을 지우지 않습니다.

모든 작업을 작업기록 JSON에 남깁니다. 인덱스가 망가져도 그 파일만 있으면
되돌릴 수 있습니다.
"""
import datetime as dt
import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import probe  # noqa: E402


FLUSH_EVERY = 100


def _write_journal(path, gallery, base, done, failed, skipped):
    path.write_text(json.dumps(
        {"시각": dt.datetime.now().isoformat(timespec="seconds"),
         "갤러리": str(gallery), "기준": str(base),
         "건너뜀": skipped, "항목": done, "실패": failed},
        ensure_ascii=False, indent=1), encoding="utf-8")


def _remove_partial(dst):
    """복사가 끊겼을 때 남은 조각 파일을 치웁니다.

    조각을 남기면 다음 실행이 dst.exists() 만 보고 완성본으로 여겨
    "이미있음" 으로 건너뜁니다. 그러면 잘린 사진이 갤러리에 영영 남습니다.
    """
    try:
        if dst.exists():
            dst.unlink()
    except OSError:
        pass


def _unique_journal(journal_dir, stem):
    """아직 안 쓰인 작업기록 경로를 고릅니다.

    이름이 초 단위라 같은 초에 두 번 돌리면 앞 기록을 덮어씁니다. 덮어쓴
    기록으로는 앞 실행이 복사한 파일을 되돌릴 수 없습니다.
    """
    path = journal_dir / f"{stem}.json"
    n = 2
    while path.exists():
        path = journal_dir / f"{stem}_{n}.json"
        n += 1
    return path


def run(rows, base, gallery, journal_dir):
    """복사하고 작업기록 경로를 돌려줍니다.

    작업기록을 중간중간 저장합니다. 12,693개 52GB 를 복사하는 도중에 죽으면
    (잠들기, 케이블 빠짐, Ctrl+C, 디스크 꽉 참) 끝에 한 번만 쓰는 방식으로는
    그때까지 복사된 파일이 어떤 기록에도 안 남아 영영 되돌릴 수 없습니다.

    이미 있는 목적지도 항목에 넣습니다. 그래야 앞선 실행이 남긴 복사본이
    이번 실행의 기록에 잡혀 되돌리기가 닿습니다.
    """
    base = pathlib.Path(base)
    gallery = pathlib.Path(gallery)
    journal_dir = pathlib.Path(journal_dir)
    journal_dir.mkdir(parents=True, exist_ok=True)
    path = _unique_journal(journal_dir, f"{dt.datetime.now():%Y%m%d_%H%M%S}")

    done, failed, skipped = [], [], 0
    for row in rows:
        src = base / row["src"]
        dst = gallery / row["dst"]
        entry = {"src": row["src"], "dst": row["dst"],
                 "sha256": row.get("sha256"), "action": row.get("action")}
        if not _inside(dst, gallery):
            # 나가는 쪽에서 막으면 늦습니다. 이미 갤러리 밖에 쓴 뒤라
            # undo 가 기록 전체를 거부하게 되고, 정상 항목까지 못 되돌립니다.
            failed.append({**row, "이유": "갤러리 밖을 가리키는 목적지"})
        elif dst.exists():
            skipped += 1
            done.append({**entry, "이미있음": True})
        elif not src.exists():
            failed.append({**row, "이유": "출처 없음"})
        else:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                # copy2 를 쓰면 안 됩니다. 메타데이터까지 복사하는데 T7 은
                # exFAT 이라 확장속성을 담을 자리가 없어서, macOS 가 파일마다
                # "._이름" 짝꿍 파일을 만듭니다. 12,693개면 짝꿍도 그만큼 생기고
                # 이 디스크를 윈도우에 꽂으면 전부 보입니다.
                #
                # 잃는 것은 원본 mtime 뿐인데, 이 프로젝트는 mtime 을 날짜
                # 출처로 쓰지 않습니다. 촬영시각은 EXIF 와 파일명에서만 옵니다.
                shutil.copy(src, dst)
            except BaseException as exc:
                # 반쯤 쓰다 만 파일을 남기면 다음 실행이 완성본으로 착각해
                # 영영 건너뜁니다.
                #
                # OSError 만 잡으면 안 됩니다. 복사 도중 Ctrl+C 는 이 함수가
                # 대비하겠다고 적어 둔 바로 그 경우인데 KeyboardInterrupt 는
                # OSError 가 아닙니다. 잘린 파일을 치우고 나서 다시 던집니다.
                _remove_partial(dst)
                if isinstance(exc, OSError):
                    failed.append({**row, "이유": str(exc)})
                else:
                    _write_journal(path, gallery, base, done, failed, skipped)
                    raise
            else:
                done.append(entry)

        if (len(done) + len(failed)) % FLUSH_EVERY == 0:
            _write_journal(path, gallery, base, done, failed, skipped)

    _write_journal(path, gallery, base, done, failed, skipped)
    return path


def verify(journal_path, base, gallery):
    """복사본이 원본과 같은 내용인지 해시로 대조합니다."""
    base = pathlib.Path(base)
    gallery = pathlib.Path(gallery)
    rec = json.loads(pathlib.Path(journal_path).read_text(encoding="utf-8"))
    problems = []
    for item in rec["항목"]:
        src = base / item["src"]
        dst = gallery / item["dst"]
        if not dst.exists():
            problems.append(f"복사본 없음: {item['dst']}")
            continue
        if not src.exists():
            continue
        if probe.sha256_of(src) != probe.sha256_of(dst):
            problems.append(f"내용 불일치: {item['dst']}")
    return problems


def _inside(path, root):
    """path 가 root 안에 있는지 확인합니다.

    작업기록은 사람이 고칠 수 있게 일부러 평문 JSON 입니다. 그래서 손으로
    고치다 ".." 나 절대경로가 들어갈 수 있고, 그대로 지우면 갤러리 밖 파일이
    사라집니다. 지우기 전에 반드시 통과시킵니다.
    """
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def _is_our_copy(dst, src, recorded):
    """dst 에 있는 파일이 우리가 넣은 그 파일인지 내용으로 확인합니다.

    기록된 해시와 맞거나, 출처 파일과 내용이 같으면 우리 복사본입니다.
    """
    try:
        digest = probe.sha256_of(dst)
    except OSError:
        return False
    if recorded and digest == recorded:
        return True
    try:
        return src.exists() and digest == probe.sha256_of(src)
    except OSError:
        return False


def undo(journal_path, gallery):
    """복사본을 지우고 빈 폴더를 정리합니다. 원본은 건드리지 않습니다.

    지운 수와 남겨 둔 항목 목록을 돌려줍니다.
    """
    gallery = pathlib.Path(gallery)
    rec = json.loads(pathlib.Path(journal_path).read_text(encoding="utf-8"))
    base = pathlib.Path(rec.get("기준", ""))
    # 하나라도 지우기 전에 전 항목을 먼저 검사합니다. 중간에 예외를 던지면
    # 앞쪽 수천 개는 이미 지워진 채로 멈춰서, 되돌리기가 반만 된 상태가 됩니다.
    bad = [i["dst"] for i in rec["항목"] if not _inside(gallery / i["dst"], gallery)]
    if bad:
        raise RuntimeError(
            f"갤러리 밖을 가리키는 기록이 {len(bad)}개 있어 아무것도 지우지 않았습니다: {bad[:3]}")

    # "이미있음" 은 이번 실행이 복사한 것이 아니라 그 자리에 이미 있던 파일입니다.
    # 사용자가 손으로 넣어 둔 사진일 수 있으므로 내용을 확인하고 지웁니다.
    # 우리가 넣은 복사본은 여기서 확인할 필요가 없습니다. 방금 우리가 썼습니다.
    kept = [i["dst"] for i in rec["항목"]
            if i.get("이미있음")
            and (gallery / i["dst"]).exists()
            and not _is_our_copy(gallery / i["dst"], base / i["src"], i.get("sha256"))]
    keep = set(kept)

    removed = 0
    folders = set()
    for item in rec["항목"]:
        dst = gallery / item["dst"]
        if dst.exists() and item["dst"] not in keep:
            dst.unlink()
            removed += 1
        folders.add(dst.parent)
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        p = folder
        while p != gallery and p.is_dir() and _inside(p, gallery):
            try:
                p.rmdir()
            except OSError:
                break
            p = p.parent
    return removed, kept
