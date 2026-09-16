#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""갤러리 CLI. 서브명령을 모읍니다.

    python3 photo-gallery/scripts/gallery.py scan
"""
import argparse
import datetime as dt
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import index  # noqa: E402
import naming  # noqa: E402
import probe  # noqa: E402

T7 = pathlib.Path("/Volumes/T7")
GALLERY = T7 / "002_Areas" / "001_사진"
DB = GALLERY / "_시스템" / "index.sqlite"
DEFAULT_ROOTS = [GALLERY / "아이폰 12 pro", T7 / "그림" / "카메라 앨범",
                 GALLERY / "동동이 사진", GALLERY / "운동",
                 GALLERY / "박기린", GALLERY / "블로그"]

MEDIA_EXT = probe.IMAGE_EXT | probe.VIDEO_EXT


def _walk(roots):
    for root in roots:
        root = pathlib.Path(root)
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in sorted(filenames):
                if fn.startswith("."):
                    continue
                if os.path.splitext(fn)[1].lower() not in MEDIA_EXT:
                    continue
                yield pathlib.Path(dirpath) / fn


def scan(con, roots, base):
    """파일을 읽어 인덱스에 넣습니다. 아무것도 옮기거나 고치지 않습니다."""
    base = pathlib.Path(base)
    now = dt.datetime.now().isoformat(timespec="seconds")
    known = {r[0] for r in con.execute("SELECT sha256 FROM photo")}
    stat = {"파일": 0, "새 내용": 0, "같은 내용": 0, "건너뜀": 0}

    for path in _walk(roots):
        try:
            digest = probe.sha256_of(path)
            size = path.stat().st_size
        except OSError:
            stat["건너뜀"] += 1
            continue
        rel = str(path.relative_to(base))
        stat["파일"] += 1

        if digest in known:
            stat["같은 내용"] += 1
        else:
            exif = probe.read_exif(path)
            kind = probe.classify(path.name, exif)
            when, src = naming.resolve_datetime(path.name, exif["dt"])
            con.execute(
                "INSERT INTO photo(sha256, path, bytes, width, height, kind, shot_at,"
                " shot_at_src, make, model, gps_lat, gps_lon, phash, origin, imported_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (digest, rel, size, exif["width"], exif["height"], kind,
                 when.isoformat(timespec="seconds") if when else None, src,
                 exif["make"], exif["model"], exif["gps_lat"], exif["gps_lon"],
                 probe.phash_to_db(probe.dhash(path)), str(path), now))
            known.add(digest)
            stat["새 내용"] += 1

        # 파일 행은 언제나 넣습니다. 같은 내용이 여러 곳에 있다는 사실이 남아야
        # Task 7에서 격리할 대상을 찾을 수 있습니다.
        #
        # photo 행보다 반드시 뒤에 넣습니다. file.sha256 이 photo.sha256 을 참조하고
        # open_db 가 PRAGMA foreign_keys 를 켜 두므로, 처음 보는 내용인데 photo 행이
        # 아직 없으면 같은 트랜잭션 안이라도 FOREIGN KEY constraint failed 가 납니다.
        con.execute("INSERT OR REPLACE INTO file(path, sha256, bytes, seen_at)"
                    " VALUES(?,?,?,?)", (rel, digest, size, now))

    con.commit()
    return stat


def cmd_scan(args):
    con = index.open_db(args.db)
    roots = [pathlib.Path(r) for r in args.root] if args.root else DEFAULT_ROOTS
    stat = scan(con, roots, args.base)
    print(f"파일 {stat['파일']}개, 새 내용 {stat['새 내용']}개, "
          f"같은 내용 {stat['같은 내용']}개, 건너뜀 {stat['건너뜀']}개")
    files = con.execute("SELECT COUNT(*) FROM file").fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM photo").fetchone()[0]
    print(f"인덱스 파일 {files}개, 고유 내용 {total}개")
    for kind, n in con.execute("SELECT kind, COUNT(*) FROM photo GROUP BY kind"):
        print(f"  {kind}: {n}")
    unknown = con.execute(
        "SELECT COUNT(*) FROM photo WHERE shot_at IS NULL").fetchone()[0]
    print(f"  촬영시각 미상: {unknown}")
    nophash = con.execute(
        "SELECT COUNT(*) FROM photo WHERE phash IS NULL").fetchone()[0]
    print(f"  지각해시 없음(중복 판정에서 빠짐): {nophash}")
    con.close()
    return 0


def cmd_blog(args):
    import blog as blogmod
    con = index.open_db(args.db)
    posts = blogmod.fetch_all(args.blog_id, pages=args.pages)
    for post in posts:
        tag, _rest = blogmod.split_tag(post["title"])
        # INSERT OR REPLACE 를 쓰면 안 됩니다. REPLACE 는 기존 행을 지우고 새로
        # 넣으므로 VALUES 에 없는 images_collected_at 이 NULL 로 초기화됩니다.
        # 이 루프는 매 실행마다 758편 전부에 대해 도니까, 바로 아래에서 계산하는
        # done 이 항상 비어 재개 가능성이 통째로 무력화됩니다.
        con.execute(
            "INSERT INTO blog_post(log_no, title, tag, posted_at) VALUES(?,?,?,?)"
            " ON CONFLICT(log_no) DO UPDATE SET"
            " title=excluded.title, tag=excluded.tag, posted_at=excluded.posted_at",
            (post["log_no"], post["title"], tag, post["posted_at"]))
    con.commit()
    print(f"글 {len(posts)}편 저장")

    # 이미지가 0개인 글도 "수집 완료" 로 표시해야 재실행 때 다시 받지 않습니다.
    # blog_image 행 유무로만 판단하면 코드블록만 있는 JS 강의 글 27편이 매번 재수집됩니다.
    done = {r[0] for r in con.execute(
        "SELECT log_no FROM blog_post WHERE images_collected_at IS NOT NULL")}
    todo = [p for p in posts if p["log_no"] not in done]
    print(f"이미지 수집 대상 {len(todo)}편")
    for i, post in enumerate(todo, 1):
        try:
            names = blogmod.parse_image_names(
                blogmod.fetch_post_html(args.blog_id, post["log_no"]))
        except Exception as exc:
            print(f"  [{i}/{len(todo)}] {post['log_no']} 실패: {exc}")
            continue
        con.executemany(
            "INSERT OR IGNORE INTO blog_image(log_no, filename, match)"
            " VALUES(?,?,'none')",
            [(post["log_no"], n) for n in names])
        con.execute("UPDATE blog_post SET images_collected_at=? WHERE log_no=?",
                    (dt.datetime.now().isoformat(timespec="seconds"), post["log_no"]))
        con.commit()
        if i % 25 == 0:
            print(f"  [{i}/{len(todo)}] 진행 중")
    total = con.execute("SELECT COUNT(*) FROM blog_image").fetchone()[0]
    print(f"발행 이미지 파일명 {total}개")
    con.close()
    return 0


def cmd_match(args):
    import matching
    con = index.open_db(args.db)
    stat = matching.match_by_name(con)
    print(f"파일명 매칭: 맞음 {stat['맞음']}, 모호 {stat['모호']}, 없음 {stat['없음']}")
    if args.hash:
        h = matching.match_by_hash(con, args.blog_id, args.threshold, limit=args.limit)
        print(f"지각해시 폴백: 맞음 {h['맞음']}, 없음 {h['없음']}, 실패 {h['실패']}")
    rows = con.execute(
        "SELECT p.tag, COUNT(*) FROM blog_image i"
        " JOIN blog_post p ON p.log_no = i.log_no"
        " WHERE i.sha256 IS NOT NULL AND p.tag IS NOT NULL"
        " GROUP BY p.tag ORDER BY 2 DESC LIMIT 20").fetchall()
    print("매칭된 사진이 많은 태그:")
    for tag, n in rows:
        print(f"  {tag}: {n}")
    con.close()
    return 0


def cmd_dup(args):
    import dedup
    con = index.open_db(args.db)

    exact = dedup.exact_groups(con)
    waste = 0
    for paths in exact:
        row = con.execute("SELECT bytes FROM file WHERE path=?", (paths[0],)).fetchone()
        waste += (row[0] if row else 0) * (len(paths) - 1)
    print(f"바이트 완전 일치: {len(exact)}그룹, 잉여 {sum(len(g) - 1 for g in exact)}개, "
          f"{waste / 2**30:.2f}GB")

    rows = [(sha, probe.phash_from_db(v)) for sha, v in
            con.execute("SELECT sha256, phash FROM photo WHERE phash IS NOT NULL")]
    near = dedup.near_groups(rows, args.threshold)
    n_waste = 0
    for shas in near:
        keeper = dedup.pick_keeper(con, shas)
        for sha in shas:
            if sha == keeper:
                continue
            r = con.execute("SELECT bytes FROM photo WHERE sha256=?", (sha,)).fetchone()
            n_waste += r[0] if r else 0
    print(f"지각해시 거리 {args.threshold} 이하: {len(near)}그룹, "
          f"잉여 {sum(len(g) - 1 for g in near)}개, {n_waste / 2**30:.2f}GB")

    print("\n표본 5그룹:")
    for shas in near[:5]:
        keeper = dedup.pick_keeper(con, shas)
        for sha in shas:
            p_, w, h, b = con.execute(
                "SELECT path, width, height, bytes FROM photo WHERE sha256=?", (sha,)).fetchone()
            mark = "남김" if sha == keeper else "격리"
            print(f"  [{mark}] {w}x{h} {b/1024:.0f}KB  {p_}")
        print()
    con.close()
    return 0


def cmd_event(args):
    import events
    import naming as nm
    con = index.open_db(args.db)
    cands = events.candidates(con)
    print(f"이벤트 후보 {len(cands)}건\n")
    for c in cands:
        folder = nm.event_folder_name(c["day"], c["name"])
        ss = events.screenshots_in_window(con, c["start"], c["end"])
        print(f"{folder}")
        print(f"  사진 {len(c['shas'])}장, 시간창 {c['start']:%H:%M}~{c['end']:%H:%M}, "
              f"창 안 스크린샷 {len(ss)}장")
        print(f"  원제 {c['title'][:70]}")
        if args.save:
            events.save(con, c, folder)
        print()
    if args.save:
        print("인덱스에 저장했습니다.")
    else:
        print("확정하려면 --save 를 붙여 다시 실행하십시오.")
    con.close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="T7 사진 갤러리 도구")
    ap.add_argument("--db", default=str(DB))
    ap.add_argument("--base", default=str(T7))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="파일을 읽어 인덱스에 넣습니다 (읽기 전용)")
    p.add_argument("--root", action="append", help="훑을 폴더. 여러 번 줄 수 있습니다")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("blog", help="블로그 글과 발행 이미지 파일명을 인덱스에 넣습니다")
    p.add_argument("--blog-id", default="op5321")
    p.add_argument("--pages", type=int, default=30)
    p.set_defaults(func=cmd_blog)

    p = sub.add_parser("match", help="블로그 이미지와 로컬 사진을 잇습니다")
    p.add_argument("--hash", action="store_true",
                   help="파일명으로 못 찾은 것을 지각해시로 다시 시도합니다 (네트워크)")
    p.add_argument("--blog-id", default="op5321")
    p.add_argument("--threshold", type=int, default=6)
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_match)

    p = sub.add_parser("dup", help="중복 후보를 보여줍니다 (파일을 옮기지 않습니다)")
    p.add_argument("--threshold", type=int, default=4)
    p.set_defaults(func=cmd_dup)

    p = sub.add_parser("event", help="이벤트 후보를 보여줍니다")
    p.add_argument("--save", action="store_true", help="후보를 인덱스에 확정합니다")
    p.set_defaults(func=cmd_event)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
