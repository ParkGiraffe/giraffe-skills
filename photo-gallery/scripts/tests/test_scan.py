#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gallery.scan 회귀 검사.

    python3 photo-gallery/scripts/tests/test_scan.py
"""
import pathlib
import sys
import tempfile
import unittest
import unittest.mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import gallery  # noqa: E402
import helpers  # noqa: E402
import index  # noqa: E402


class TestScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.con = index.open_db(self.base / "db" / "index.sqlite")
        helpers.make_tree(self.base, {
            "src/a/20260501_155339_IMG_1.jpg":
                helpers.jpeg_bytes(exif_dt="2026:05:01 15:53:39"),
            "src/a/Screenshot_20260501_155542_Pokmon GO.jpg": helpers.jpeg_bytes(),
            "src/b/IMG_9999.PNG": helpers.png_bytes(),
            "src/b/.DS_Store": b"junk",
            "src/b/notes.txt": b"not media",
        })
        self.roots = [self.base / "src"]

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_inserts_media_only(self):
        got = gallery.scan(self.con, self.roots, self.base)
        self.assertEqual(3, got["새 내용"])
        self.assertEqual(3, self.con.execute("SELECT COUNT(*) FROM photo").fetchone()[0])
        self.assertEqual(3, self.con.execute("SELECT COUNT(*) FROM file").fetchone()[0])

    def test_skips_dotfiles_and_non_media(self):
        gallery.scan(self.con, self.roots, self.base)
        paths = {r[0] for r in self.con.execute("SELECT path FROM file")}
        self.assertNotIn("src/b/.DS_Store", paths)
        self.assertNotIn("src/b/notes.txt", paths)

    def test_path_is_relative_to_base(self):
        gallery.scan(self.con, self.roots, self.base)
        paths = {r[0] for r in self.con.execute("SELECT path FROM file")}
        self.assertIn("src/a/20260501_155339_IMG_1.jpg", paths)

    def test_records_kind_and_date_source(self):
        gallery.scan(self.con, self.roots, self.base)
        row = self.con.execute(
            "SELECT kind, shot_at, shot_at_src FROM photo WHERE path LIKE '%IMG_1.jpg'"
        ).fetchone()
        self.assertEqual("사진", row[0])
        self.assertEqual("2026-05-01T15:53:39", row[1])
        self.assertEqual("exif", row[2])

    def test_screenshot_is_classified(self):
        gallery.scan(self.con, self.roots, self.base)
        kinds = {r[0] for r in self.con.execute(
            "SELECT kind FROM photo WHERE path LIKE '%Pokmon GO.jpg'")}
        self.assertEqual({"스크린샷"}, kinds)

    def test_unknown_date_is_null(self):
        gallery.scan(self.con, self.roots, self.base)
        row = self.con.execute(
            "SELECT shot_at, shot_at_src FROM photo WHERE path LIKE '%IMG_9999.PNG'"
        ).fetchone()
        self.assertIsNone(row[0])
        self.assertEqual("unknown", row[1])

    def test_rescan_is_idempotent(self):
        gallery.scan(self.con, self.roots, self.base)
        got = gallery.scan(self.con, self.roots, self.base)
        self.assertEqual(0, got["새 내용"])
        self.assertEqual(3, got["같은 내용"])
        self.assertEqual(3, self.con.execute("SELECT COUNT(*) FROM photo").fetchone()[0])
        self.assertEqual(3, self.con.execute("SELECT COUNT(*) FROM file").fetchone()[0])

    def test_duplicate_content_keeps_both_files_one_photo(self):
        """바이트가 같아도 파일 두 개를 둘 다 기억해야 나중에 격리할 수 있습니다."""
        same = helpers.gradient_jpeg(seed=77)
        helpers.make_tree(self.base, {"src/c/copy1.jpg": same, "src/c/copy2.jpg": same})
        gallery.scan(self.con, self.roots, self.base)
        sha = self.con.execute(
            "SELECT sha256 FROM file WHERE path='src/c/copy1.jpg'").fetchone()[0]
        self.assertEqual(1, self.con.execute(
            "SELECT COUNT(*) FROM photo WHERE sha256=?", (sha,)).fetchone()[0])
        self.assertEqual(2, self.con.execute(
            "SELECT COUNT(*) FROM file WHERE sha256=?", (sha,)).fetchone()[0])

    def test_does_not_move_any_file(self):
        before = sorted(p.name for p in (self.base / "src").rglob("*") if p.is_file())
        gallery.scan(self.con, self.roots, self.base)
        after = sorted(p.name for p in (self.base / "src").rglob("*") if p.is_file())
        self.assertEqual(before, after)


class TestScanOutsideBase(unittest.TestCase):
    """--root 가 --base 밖이면 인덱스에 담을 상대경로 자체가 없습니다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.base = self.root / "기준"
        self.outside = self.root / "바깥"
        self.con = index.open_db(self.root / "db" / "index.sqlite")
        helpers.make_tree(self.base, {"안/a.jpg": helpers.jpeg_bytes()})
        helpers.make_tree(self.outside, {"b.jpg": helpers.jpeg_bytes()})

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_refuses_before_reading_anything(self):
        with self.assertRaises(ValueError):
            gallery.scan(self.con, [self.base / "안", self.outside], self.base)
        self.assertEqual(0, self.con.execute(
            "SELECT COUNT(*) FROM file").fetchone()[0])

    def test_error_names_the_offending_root(self):
        with self.assertRaises(ValueError) as caught:
            gallery.scan(self.con, [self.outside], self.base)
        self.assertIn(str(self.outside), str(caught.exception))

    def test_roots_inside_base_still_scan(self):
        stat = gallery.scan(self.con, [self.base / "안"], self.base)
        self.assertEqual(1, stat["파일"])


class TestScanCommitsAlongTheWay(unittest.TestCase):
    """끝에 한 번만 커밋하면 도중에 죽었을 때 읽은 것을 전부 버립니다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.dbpath = self.base / "db" / "index.sqlite"
        self.con = index.open_db(self.dbpath)
        helpers.make_tree(self.base, {
            f"src/{i:03d}.jpg": helpers.gradient_jpeg(seed=i) for i in range(6)})

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_rows_are_durable_before_the_walk_ends(self):
        seen = []
        real = gallery.probe.sha256_of

        def counting(path):
            seen.append(path)
            if len(seen) == 5:
                raise KeyboardInterrupt("훑는 도중 중단")
            return real(path)

        with unittest.mock.patch.object(gallery.probe, "sha256_of", counting):
            with self.assertRaises(KeyboardInterrupt):
                gallery.scan(self.con, [self.base / "src"], self.base,
                             commit_every=2)

        # 커밋 안 된 것은 rollback 으로 사라집니다. 남는 것이 진짜 저장된 것입니다.
        self.con.rollback()
        self.assertEqual(4, self.con.execute(
            "SELECT COUNT(*) FROM file").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
