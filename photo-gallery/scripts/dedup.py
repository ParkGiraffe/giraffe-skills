#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""중복 그룹을 만듭니다. 파일을 옮기지 않습니다.

합집합(union-find)을 쓰지 않습니다. A와 B가 닮고 B와 C가 닮아도 A와 C는 다를 수
있는데, 합집합은 셋을 한 그룹으로 만듭니다. 실측에서 이 방식으로 거리 6을 돌렸을 때
2018년과 2020년 사진이 뒤섞인 221장짜리 가짜 그룹이 나왔습니다.

그래서 그룹 안의 **모든 쌍**이 임계값 안에 들어야 채택합니다(완전그래프).
"""
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import probe  # noqa: E402

MAX_GROUP = 8

# 남길 쪽 고르는 순서 (스펙 8.2절)
_SRC_RANK = {"exif": 0, "filename": 1, "unknown": 2}


def exact_groups(con):
    """같은 sha256을 가진 파일 경로 묶음. 2개 이상인 것만 돌려줍니다."""
    by = collections.defaultdict(list)
    for path, sha in con.execute("SELECT path, sha256 FROM file ORDER BY path"):
        by[sha].append(path)
    return [paths for paths in by.values() if len(paths) > 1]


def near_groups(rows, threshold, max_size=MAX_GROUP):
    """[(sha256, phash)] -> 완전그래프를 이루는 sha 묶음 목록입니다.

    phash가 None인 행은 무시합니다. 크기가 max_size를 넘는 그룹은 버리고
    사용자 검토로 돌립니다.
    """
    items = [(sha, h) for sha, h in rows if h is not None]
    n = len(items)
    neighbors = collections.defaultdict(set)
    for i in range(n):
        for j in range(i + 1, n):
            if probe.hamming(items[i][1], items[j][1]) <= threshold:
                neighbors[i].add(j)
                neighbors[j].add(i)

    out, used = [], set()
    for i in range(n):
        if i in used or not neighbors[i]:
            continue
        group = [i]
        for j in sorted(neighbors[i]):
            if j in used:
                continue
            if all(probe.hamming(items[j][1], items[k][1]) <= threshold for k in group):
                group.append(j)
        if len(group) < 2:
            continue
        if len(group) > max_size:
            used.update(group)
            continue
        used.update(group)
        out.append([items[k][0] for k in group])
    return out


def pick_keeper(con, shas):
    """남길 sha 하나를 고릅니다. 해상도 > 크기 > EXIF > 이른 촬영시각 순입니다."""
    rows = con.execute(
        "SELECT sha256, width, height, bytes, shot_at_src, shot_at, path FROM photo"
        f" WHERE sha256 IN ({','.join('?' * len(shas))})", shas).fetchall()

    def rank(r):
        sha, w, h, b, src, shot, path = r
        pixels = (w or 0) * (h or 0)
        return (-pixels, -(b or 0), _SRC_RANK.get(src, 9), shot or "9999", len(path or ""), sha)

    return sorted(rows, key=rank)[0][0]
