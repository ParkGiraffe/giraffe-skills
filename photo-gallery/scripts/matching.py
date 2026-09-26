#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""블로그 발행 이미지와 로컬 사진을 잇습니다.

네이버가 원본 파일명을 URL에 보존하므로 파일명만으로 사진 한 장 단위 매칭이 됩니다.
로컬은 정규화된 이름이라 양쪽에서 날짜 접두를 떼고 비교합니다.

리네임해 올린 이미지는 파일명이 통째로 어긋납니다. 그때는 발행 이미지를 받아
지각해시로 잇습니다(스펙 9.1절).
"""
import collections
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import probe  # noqa: E402

PREFIX = re.compile(r"^\d{8}_\d{6}_")


def name_key(filename):
    """비교용 키. 날짜 접두를 떼고 소문자로 만듭니다.

    떼고 나서 남는 게 없으면(`20181121_180959.jpg`) 원래 이름을 그대로 씁니다.
    """
    base = os.path.basename(filename)
    stripped = PREFIX.sub("", base)
    stem = os.path.splitext(stripped)[0]
    return (stripped if stem else base).lower()


def build_name_index(rows):
    """[(sha256, path)] -> {키: sha256}. 키가 겹치면 값이 None(모호)입니다."""
    out = {}
    for sha, path in rows:
        key = name_key(path)
        if key in out and out[key] != sha:
            out[key] = None
        elif key not in out:
            out[key] = sha
    return out


def match_by_name(con):
    """blog_image에 sha256과 match를 채웁니다."""
    idx = build_name_index(con.execute("SELECT sha256, path FROM file").fetchall())
    stat = {"맞음": 0, "모호": 0, "없음": 0}
    for log_no, filename in con.execute(
            "SELECT log_no, filename FROM blog_image WHERE sha256 IS NULL").fetchall():
        sha = idx.get(name_key(filename), "MISSING")
        if sha == "MISSING":
            stat["없음"] += 1
            continue
        if sha is None:
            con.execute("UPDATE blog_image SET match='ambiguous'"
                        " WHERE log_no=? AND filename=?", (log_no, filename))
            stat["모호"] += 1
            continue
        con.execute("UPDATE blog_image SET sha256=?, match='name'"
                    " WHERE log_no=? AND filename=?", (sha, log_no, filename))
        stat["맞음"] += 1
    con.commit()
    return stat


def match_by_hash(con, blog_id, threshold=6, fetch_html=None, fetch_bytes=None, limit=0):
    """파일명으로 못 찾은 것을 지각해시로 잇습니다.

    네트워크를 타므로 기본은 꺼져 있습니다. fetcher를 주입하면 네트워크 없이
    검사할 수 있습니다.
    """
    import blog as blogmod
    fetch_html = fetch_html or blogmod.fetch_post_html
    fetch_bytes = fetch_bytes or blogmod.fetch_bytes

    local = [(sha, probe.phash_from_db(v)) for sha, v in con.execute(
        "SELECT sha256, phash FROM photo WHERE phash IS NOT NULL")]
    local = [(sha, h) for sha, h in local if h is not None]
    pending = con.execute(
        "SELECT log_no, filename FROM blog_image"
        " WHERE sha256 IS NULL AND match='none' ORDER BY log_no, filename").fetchall()
    if limit:
        pending = pending[:limit]

    by_post = collections.defaultdict(list)
    for log_no, filename in pending:
        by_post[log_no].append(filename)

    stat = {"맞음": 0, "없음": 0, "실패": 0}
    for log_no, filenames in by_post.items():
        try:
            urls = dict(blogmod.parse_image_urls(fetch_html(blog_id, log_no)))
        except Exception:
            stat["실패"] += len(filenames)
            continue
        for filename in filenames:
            url = urls.get(filename)
            if not url:
                stat["없음"] += 1
                continue
            try:
                digest = probe.dhash_bytes(fetch_bytes(url))
            except Exception:
                stat["실패"] += 1
                continue
            if digest is None:
                stat["실패"] += 1
                continue
            best, dist = None, threshold + 1
            for sha, local_hash in local:
                d = probe.hamming(digest, local_hash)
                if d < dist:
                    best, dist = sha, d
            if best is None:
                stat["없음"] += 1
                continue
            con.execute("UPDATE blog_image SET sha256=?, match='dhash'"
                        " WHERE log_no=? AND filename=?", (best, log_no, filename))
            stat["맞음"] += 1
    con.commit()
    return stat
