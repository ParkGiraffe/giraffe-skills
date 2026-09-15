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
        con.execute("INSERT OR REPLACE INTO blog_post(log_no, title, tag, posted_at)"
                    " VALUES(?,?,?,?)",
                    (post["log_no"], post["title"], tag, post["posted_at"]))
    con.commit()
    print(f"글 {len(posts)}편 저장")

    done = {r[0] for r in con.execute("SELECT DISTINCT log_no FROM blog_image")}
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
        con.commit()
        if i % 25 == 0:
            print(f"  [{i}/{len(todo)}] 진행 중")
    total = con.execute("SELECT COUNT(*) FROM blog_image").fetchone()[0]
    print(f"발행 이미지 파일명 {total}개")
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

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
