#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""블로그 매칭 결과에서 이벤트 후보와 시간창을 뽑습니다.

발행일을 행사일로 쓰지 않습니다. 실측에서 성수 메가페스타 1차는 방문이 5월 1일,
발행이 5월 2일이었습니다. 날짜는 매칭된 사진의 EXIF에서 가져오고 블로그는 이름만 줍니다.
"""
import datetime as dt
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import blog  # noqa: E402


def _parse(value):
    return dt.datetime.fromisoformat(value) if value else None


def window(shots, margin_minutes=30):
    """사진들을 감싸는 시간창. 앞뒤로 여유를 둡니다."""
    margin = dt.timedelta(minutes=margin_minutes)
    return min(shots) - margin, max(shots) + margin


def candidates(con, max_span_days=3, min_photos=3):
    """매칭된 사진이 시간적으로 뭉친 글만 행사 후보로 봅니다.

    게임 공략글은 스크린샷이 몇 달에 걸쳐 있어 여기서 걸러집니다.
    """
    rows = con.execute(
        "SELECT i.log_no, p.title, i.sha256, ph.shot_at"
        " FROM blog_image i"
        " JOIN blog_post p ON p.log_no = i.log_no"
        " JOIN photo ph ON ph.sha256 = i.sha256"
        " WHERE i.sha256 IS NOT NULL AND ph.shot_at IS NOT NULL"
        " ORDER BY i.log_no, ph.shot_at").fetchall()

    grouped = {}
    for log_no, title, sha, shot in rows:
        entry = grouped.setdefault(log_no, {"title": title, "shas": [], "shots": []})
        entry["shas"].append(sha)
        entry["shots"].append(_parse(shot))

    out = []
    for log_no, entry in grouped.items():
        shots = [s for s in entry["shots"] if s]
        if len(shots) < min_photos:
            continue
        if (max(shots) - min(shots)) > dt.timedelta(days=max_span_days):
            continue
        start, end = window(shots)
        out.append({"log_no": log_no,
                    "title": entry["title"],
                    "name": blog.event_name(entry["title"]),
                    "shas": entry["shas"],
                    "start": start,
                    "end": end,
                    "day": min(shots)})
    out.sort(key=lambda c: c["day"])
    return out


def screenshots_in_window(con, start, end):
    """시간창 안의 스크린샷. 사람이 눈으로 보고 행사 소속을 정할 대상입니다."""
    return con.execute(
        "SELECT sha256, path, shot_at FROM photo"
        " WHERE kind='스크린샷' AND shot_at IS NOT NULL"
        " AND shot_at >= ? AND shot_at <= ? ORDER BY shot_at",
        (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"))).fetchall()


def save(con, cand, folder):
    """event 행을 만들고 딸린 사진의 event_id를 채웁니다."""
    cur = con.execute(
        "INSERT OR REPLACE INTO event(folder, name, start_at, end_at, log_no)"
        " VALUES(?,?,?,?,?)",
        (folder, cand["name"],
         cand["start"].isoformat(timespec="seconds"),
         cand["end"].isoformat(timespec="seconds"),
         cand["log_no"]))
    eid = cur.lastrowid
    con.executemany("UPDATE photo SET event_id=? WHERE sha256=?",
                    [(eid, sha) for sha in cand["shas"]])
    con.commit()
    return eid


def assign(con, event_id, shas):
    """사람이 판정한 사진(주로 스크린샷)을 이벤트에 붙입니다.

    앱 이름으로 자동 판정하지 않습니다. 같은 날 인스타그램 스크린샷처럼 행사와
    무관한 것이 섞이기 때문입니다. 스펙 7.3절.
    """
    cur = con.executemany("UPDATE photo SET event_id=? WHERE sha256=?",
                          [(event_id, sha) for sha in shas])
    con.commit()
    return cur.rowcount if cur.rowcount is not None else len(shas)


def unassign(con, shas):
    """잘못 붙인 것을 뗍니다."""
    cur = con.executemany("UPDATE photo SET event_id=NULL WHERE sha256=?",
                          [(sha,) for sha in shas])
    con.commit()
    return cur.rowcount if cur.rowcount is not None else len(shas)
