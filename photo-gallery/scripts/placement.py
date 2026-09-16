#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""배치 계획을 만듭니다. 파일을 건드리지 않는 마지막 단계입니다.

디스크의 파일 하나가 계획 한 줄이 됩니다. 같은 내용이 여러 곳에 있으면
대표 하나만 갤러리로 가고 나머지는 격리함으로 갑니다.
"""
import collections
import datetime as dt
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import dedup  # noqa: E402
import naming  # noqa: E402
import probe  # noqa: E402

QUARANTINE = "_시스템/중복격리"


def _parse(value):
    return dt.datetime.fromisoformat(value) if value else None


def build(con, threshold=4):
    """계획 줄 목록을 돌려줍니다. src 기준으로 정렬돼 있습니다."""
    photos = {}
    for row in con.execute(
            "SELECT p.sha256, p.kind, p.shot_at, p.shot_at_src, p.phash, e.folder"
            " FROM photo p LEFT JOIN event e ON e.id = p.event_id"):
        sha, kind, shot, shot_src, phash, folder = row
        photos[sha] = {"kind": kind, "shot": _parse(shot), "src": shot_src or "exif",
                       "phash": probe.phash_from_db(phash), "event": folder}

    files = collections.defaultdict(list)
    for path, sha in con.execute("SELECT path, sha256 FROM file ORDER BY path"):
        files[sha].append(path)

    # 지각해시로 묶인 무리에서는 대표 하나만 갤러리로 보냅니다.
    near_keeper = {}
    for group in dedup.near_groups(
            [(sha, meta["phash"]) for sha, meta in photos.items()], threshold):
        keeper = dedup.pick_keeper(con, group)
        for sha in group:
            near_keeper[sha] = keeper

    orphans = [path for sha, paths in files.items() if sha not in photos
               for path in paths]
    if orphans:
        # 조용히 건너뛰면 안 됩니다. 이 함수는 파일을 옮기기 직전의 마지막 관문이고,
        # 빠진 파일은 갤러리에 영영 도착하지 않는데 아무도 모릅니다.
        # 지금은 file.sha256 의 외래키가 막아 주지만, 그 보장이 코드 밖에 있습니다.
        raise RuntimeError(
            f"photo 행이 없는 file 행이 {len(orphans)}개 있습니다. "
            f"인덱스가 깨졌으니 계획을 만들지 않습니다. 예: {orphans[:3]}")

    rows = []
    for sha, paths in files.items():
        meta = photos[sha]
        keeper = near_keeper.get(sha, sha)
        for i, path in enumerate(paths):
            name = os.path.basename(path)
            if i == 0 and keeper == sha:
                filename = (naming.normalize_name(name, meta["shot"], meta["src"])
                            if meta["shot"] else name)
                dst = naming.destination(meta["kind"], meta["shot"], filename,
                                         meta["event"], meta["src"],
                                         naming.subject_folder(path))
                action = "복사"
            else:
                dst = f"{QUARANTINE}/{sha[:12]}_{name}"
                action = "격리"
            rows.append({"src": path, "dst": dst, "sha256": sha,
                         "action": action, "kind": meta["kind"],
                         "event": meta["event"]})

    rows.sort(key=lambda r: r["src"])
    return resolve_collisions(rows)


def resolve_collisions(rows):
    """같은 목적지에 서로 다른 내용이 오면 _2, _3을 붙입니다."""
    taken = {}
    for row in rows:
        dst = row["dst"]
        if dst not in taken:
            taken[dst] = row["sha256"]
            continue
        if taken[dst] == row["sha256"]:
            continue
        stem, ext = os.path.splitext(dst)
        n = 2
        while f"{stem}_{n}{ext}" in taken:
            n += 1
        row["dst"] = f"{stem}_{n}{ext}"
        taken[row["dst"]] = row["sha256"]
    return rows


def escapes(rel):
    """갤러리 밖으로 나가는 상대경로인지 봅니다.

    계획 CSV 는 사람이 열어 검토하라고 만든 문서입니다. 손으로 고치다
    "../" 나 절대경로가 들어가면 갤러리 밖에 파일이 쓰입니다. 나가는 쪽에서
    막으면 이미 늦습니다. 여기서 막습니다.
    """
    p = pathlib.PurePosixPath(str(rel).replace("\\", "/"))
    return p.is_absolute() or ".." in p.parts


def validate(rows):
    """남은 문제 목록입니다. 비어야 적용 단계로 갈 수 있습니다."""
    problems = []
    by_dst = collections.defaultdict(set)
    seen_src = collections.Counter()
    for row in rows:
        if escapes(row["dst"]):
            problems.append(f"갤러리 밖을 가리키는 목적지: {row['dst']}")
        by_dst[row["dst"]].add(row["sha256"])
        seen_src[row["src"]] += 1
    for dst, shas in by_dst.items():
        if len(shas) > 1:
            problems.append(f"목적지 충돌: {dst} 에 서로 다른 내용 {len(shas)}개")
    for src, n in seen_src.items():
        if n > 1:
            problems.append(f"출처 중복: {src} 가 {n}번 나옵니다")
    return problems
