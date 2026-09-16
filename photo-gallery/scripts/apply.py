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
    path = journal_dir / f"{dt.datetime.now():%Y%m%d_%H%M%S}.json"

    done, failed, skipped = [], [], 0
    for row in rows:
        src = base / row["src"]
        dst = gallery / row["dst"]
        entry = {"src": row["src"], "dst": row["dst"],
                 "sha256": row.get("sha256"), "action": row.get("action")}
        if dst.exists():
            skipped += 1
            done.append({**entry, "이미있음": True})
        elif not src.exists():
            failed.append({**row, "이유": "출처 없음"})
        else:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            except OSError as exc:
                # 반쯤 쓰다 만 파일을 남기면 다음 실행이 완성본으로 착각해
                # 영영 건너뜁니다.
                try:
                    if dst.exists():
                        dst.unlink()
                except OSError:
                    pass
                failed.append({**row, "이유": str(exc)})
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


def undo(journal_path, gallery):
    """복사본을 지우고 빈 폴더를 정리합니다. 원본은 건드리지 않습니다."""
    gallery = pathlib.Path(gallery)
    rec = json.loads(pathlib.Path(journal_path).read_text(encoding="utf-8"))
    removed = 0
    folders = set()
    for item in rec["항목"]:
        dst = gallery / item["dst"]
        if not _inside(dst, gallery):
            raise RuntimeError(f"갤러리 밖을 가리키는 기록이 있습니다: {item['dst']}")
        if dst.exists():
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
    return removed
