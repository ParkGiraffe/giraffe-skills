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


def run(rows, base, gallery, journal_dir):
    """복사하고 작업기록 경로를 돌려줍니다."""
    base = pathlib.Path(base)
    gallery = pathlib.Path(gallery)
    journal_dir = pathlib.Path(journal_dir)
    journal_dir.mkdir(parents=True, exist_ok=True)

    done, failed, skipped = [], [], 0
    for row in rows:
        src = base / row["src"]
        dst = gallery / row["dst"]
        if dst.exists():
            skipped += 1
            continue
        if not src.exists():
            failed.append({**row, "이유": "출처 없음"})
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        except OSError as exc:
            failed.append({**row, "이유": str(exc)})
            continue
        done.append({"src": row["src"], "dst": row["dst"],
                     "sha256": row.get("sha256"), "action": row.get("action")})

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = journal_dir / f"{stamp}.json"
    path.write_text(json.dumps(
        {"시각": dt.datetime.now().isoformat(timespec="seconds"),
         "갤러리": str(gallery), "기준": str(base),
         "건너뜀": skipped, "항목": done, "실패": failed},
        ensure_ascii=False, indent=1), encoding="utf-8")
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


def undo(journal_path, gallery):
    """복사본을 지우고 빈 폴더를 정리합니다. 원본은 건드리지 않습니다."""
    gallery = pathlib.Path(gallery)
    rec = json.loads(pathlib.Path(journal_path).read_text(encoding="utf-8"))
    removed = 0
    folders = set()
    for item in rec["항목"]:
        dst = gallery / item["dst"]
        if dst.exists():
            dst.unlink()
            removed += 1
        folders.add(dst.parent)
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        p = folder
        while p != gallery and p.is_dir():
            try:
                p.rmdir()
            except OSError:
                break
            p = p.parent
    return removed
