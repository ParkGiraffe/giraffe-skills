#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dedup.py 회귀 검사. 합집합 금지 규칙이 핵심입니다.

    python3 photo-gallery/scripts/tests/test_dedup.py
"""
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import dedup  # noqa: E402
import index  # noqa: E402


def bits(*positions):
    """지정한 비트만 1인 64비트 정수."""
    v = 0
    for p in positions:
        v |= 1 << p
    return v


class TestNearGroups(unittest.TestCase):
    def test_pairs_within_threshold(self):
        got = dedup.near_groups([("a", bits()), ("b", bits(0, 1))], threshold=4)
        self.assertEqual([["a", "b"]], [sorted(g) for g in got])

    def test_pairs_beyond_threshold_are_separate(self):
        got = dedup.near_groups([("a", bits()), ("b", bits(0, 1, 2, 3, 4, 5))], threshold=4)
        self.assertEqual([], got)

    def test_chain_must_not_merge(self):
        """A-B 가깝고 B-C 가까워도 A-C가 멀면 셋을 한 그룹으로 만들면 안 됩니다.

        실측에서 이 규칙을 어겼을 때 2018년과 2020년 사진이 뒤섞인
        221장짜리 가짜 그룹이 나왔습니다.
        """
        a = bits()
        b = bits(0, 1, 2)
        c = bits(0, 1, 2, 3, 4, 5)   # a와는 거리 6, b와는 거리 3
        got = dedup.near_groups([("a", a), ("b", b), ("c", c)], threshold=4)
        for g in got:
            self.assertFalse({"a", "c"} <= set(g), f"사슬 병합 발생: {g}")

    def test_true_clique_is_kept(self):
        a = bits()
        b = bits(0)
        c = bits(1)
        got = dedup.near_groups([("a", a), ("b", b), ("c", c)], threshold=4)
        self.assertEqual(1, len(got))
        self.assertEqual(["a", "b", "c"], sorted(got[0]))

    def test_oversized_group_is_dropped(self):
        rows = [(chr(97 + i), bits()) for i in range(12)]
        got = dedup.near_groups(rows, threshold=4, max_size=8)
        self.assertEqual([], got)

    def test_ignores_null_phash(self):
        got = dedup.near_groups([("a", None), ("b", None)], threshold=4)
        self.assertEqual([], got)


class TestExactGroups(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = index.open_db(pathlib.Path(self.tmp.name) / "i.sqlite")
        self.con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                         " VALUES('aaa','p1',10,'사진','/o','t')")
        self.con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                         " VALUES('bbb','q1',10,'사진','/o','t')")
        for path, sha in (("p1", "aaa"), ("p2", "aaa"), ("p3", "aaa"), ("q1", "bbb")):
            self.con.execute("INSERT INTO file(path, sha256, bytes, seen_at)"
                             " VALUES(?,?,10,'t')", (path, sha))
        self.con.commit()

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_finds_three_way_duplicate(self):
        got = dedup.exact_groups(self.con)
        self.assertEqual(1, len(got))
        self.assertEqual(["p1", "p2", "p3"], sorted(got[0]))

    def test_singleton_is_not_a_group(self):
        for g in dedup.exact_groups(self.con):
            self.assertNotIn("q1", g)


class TestPickKeeper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = index.open_db(pathlib.Path(self.tmp.name) / "i.sqlite")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def add(self, sha, w, h, b, src="filename", shot="2026-01-01T00:00:00"):
        self.con.execute(
            "INSERT INTO photo(sha256, path, bytes, width, height, kind, shot_at,"
            " shot_at_src, origin, imported_at) VALUES(?,?,?,?,?,'사진',?,?,'/o','t')",
            (sha, sha, b, w, h, shot, src))

    def test_prefers_larger_resolution(self):
        self.add("small", 800, 600, 100000)
        self.add("big", 4000, 3000, 90000)
        self.con.commit()
        self.assertEqual("big", dedup.pick_keeper(self.con, ["small", "big"]))

    def test_prefers_larger_bytes_when_resolution_ties(self):
        self.add("lo", 1000, 1000, 50000)
        self.add("hi", 1000, 1000, 500000)
        self.con.commit()
        self.assertEqual("hi", dedup.pick_keeper(self.con, ["lo", "hi"]))

    def test_prefers_exif_over_filename(self):
        self.add("noexif", 1000, 1000, 100000, src="filename")
        self.add("hasexif", 1000, 1000, 100000, src="exif")
        self.con.commit()
        self.assertEqual("hasexif", dedup.pick_keeper(self.con, ["noexif", "hasexif"]))

    def test_prefers_earlier_shot(self):
        self.add("late", 1000, 1000, 100000, src="exif", shot="2026-05-02T00:00:00")
        self.add("early", 1000, 1000, 100000, src="exif", shot="2026-05-01T00:00:00")
        self.con.commit()
        self.assertEqual("early", dedup.pick_keeper(self.con, ["late", "early"]))


if __name__ == "__main__":
    unittest.main()
