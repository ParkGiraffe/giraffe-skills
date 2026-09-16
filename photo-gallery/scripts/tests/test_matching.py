#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matching.py 회귀 검사.

    python3 photo-gallery/scripts/tests/test_matching.py
"""
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import index  # noqa: E402
import matching  # noqa: E402
import probe as probe_mod  # noqa: E402


class TestNameKey(unittest.TestCase):
    def test_strips_normalized_prefix(self):
        self.assertEqual("img_1027.png", matching.name_key("20240108_072733_IMG_1027.PNG"))

    def test_blog_original_name_makes_same_key(self):
        self.assertEqual(matching.name_key("20240108_072733_IMG_1027.PNG"),
                         matching.name_key("IMG_1027.PNG"))

    def test_bare_dated_name_keeps_itself(self):
        self.assertEqual("20181121_180959.jpg", matching.name_key("20181121_180959.jpg"))

    def test_case_insensitive(self):
        self.assertEqual(matching.name_key("IMG_1.JPEG"), matching.name_key("img_1.jpeg"))


class TestBuildNameIndex(unittest.TestCase):
    def test_unique_key_maps_to_sha(self):
        got = matching.build_name_index([("aaa", "x/20240108_072733_IMG_1027.PNG")])
        self.assertEqual("aaa", got["img_1027.png"])

    def test_colliding_key_is_ambiguous(self):
        got = matching.build_name_index([
            ("aaa", "x/20240108_072733_IMG_1027.PNG"),
            ("bbb", "y/20250101_010101_IMG_1027.PNG")])
        self.assertIsNone(got["img_1027.png"])


class TestMatchByName(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = index.open_db(pathlib.Path(self.tmp.name) / "i.sqlite")
        self.con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                         " VALUES('aaa','g/20240108_072733_IMG_1027.PNG',1,'사진','/o','t')")
        self.con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                         " VALUES('bbb','g/20240109_010101_IMG_2222.JPG',1,'사진','/o','t')")
        self.con.execute("INSERT INTO file(path, sha256, bytes, seen_at)"
                         " VALUES('g/20240108_072733_IMG_1027.PNG','aaa',1,'t')")
        self.con.execute("INSERT INTO file(path, sha256, bytes, seen_at)"
                         " VALUES('g/20240109_010101_IMG_2222.JPG','bbb',1,'t')")
        self.con.execute("INSERT INTO blog_post(log_no, title) VALUES('1','[포켓몬 팝업] 성수')")
        for name in ("IMG_1027.PNG", "IMG_9999.JPG"):
            self.con.execute("INSERT INTO blog_image(log_no, filename, match)"
                             " VALUES('1',?,'none')", (name,))
        self.con.commit()

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_matches_and_marks(self):
        got = matching.match_by_name(self.con)
        self.assertEqual(1, got["맞음"])
        self.assertEqual(1, got["없음"])
        row = self.con.execute(
            "SELECT sha256, match FROM blog_image WHERE filename='IMG_1027.PNG'").fetchone()
        self.assertEqual(("aaa", "name"), row)

    def test_unmatched_stays_none(self):
        matching.match_by_name(self.con)
        row = self.con.execute(
            "SELECT sha256, match FROM blog_image WHERE filename='IMG_9999.JPG'").fetchone()
        self.assertEqual((None, "none"), row)


class TestMatchByHash(unittest.TestCase):
    """네이버가 리네임해 올린 이미지를 잇는 폴백. 네트워크 없이 검사합니다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = index.open_db(pathlib.Path(self.tmp.name) / "i.sqlite")
        # phash 는 16자리 16진수 문자열로 저장됩니다 (최상위 비트가 1이어도 안전).
        self.local_phash = 0b1010101010101010101010101010101010101010101010101010101010101010
        self.con.execute(
            "INSERT INTO photo(sha256, path, bytes, kind, phash, origin, imported_at)"
            " VALUES('aaa','g/IMG_1.jpg',1,'사진',?,'/o','t')",
            (probe_mod.phash_to_db(self.local_phash),))
        self.con.execute("INSERT INTO blog_post(log_no, title) VALUES('1','글')")
        self.con.execute("INSERT INTO blog_image(log_no, filename, match)"
                         " VALUES('1','네이버가_바꾼이름.jpg','none')")
        self.con.commit()
        self.html = '<img class="se-image-resource" src="https://x/네이버가_바꾼이름.jpg">'

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def _fetchers(self, phash_value):
        import probe
        real = probe.dhash_bytes
        probe.dhash_bytes = lambda data: phash_value
        self.addCleanup(lambda: setattr(probe, "dhash_bytes", real))
        return (lambda blog_id, log_no: self.html), (lambda url: b"bytes")

    def test_near_hash_matches(self):
        fh, fb = self._fetchers(self.local_phash ^ 0b11)   # 거리 2
        got = matching.match_by_hash(self.con, "op5321", threshold=6,
                                     fetch_html=fh, fetch_bytes=fb)
        self.assertEqual(1, got["맞음"])
        row = self.con.execute(
            "SELECT sha256, match FROM blog_image WHERE filename='네이버가_바꾼이름.jpg'"
        ).fetchone()
        self.assertEqual(("aaa", "dhash"), row)

    def test_undecodable_image_is_counted_not_raised(self):
        """디코딩 실패는 실패로 세고 넘어가야 합니다.

        가드가 없으면 probe.hamming(None, ...) 이 TypeError 를 내는데 감싸는
        try 가 없어 실행 전체가 죽습니다. 만 육천 건짜리 작업이 한 장 때문에
        중단되면 안 됩니다.
        """
        fh, fb = self._fetchers(None)
        got = matching.match_by_hash(self.con, "op5321", threshold=6,
                                     fetch_html=fh, fetch_bytes=fb)
        self.assertEqual(1, got["실패"])
        self.assertEqual(0, got["맞음"])

    def test_distance_one_over_threshold_does_not_match(self):
        """거리가 임계값보다 1 크면 매칭이 아닙니다."""
        fh, fb = self._fetchers(self.local_phash ^ 0b1111111)   # 거리 7
        got = matching.match_by_hash(self.con, "op5321", threshold=6,
                                     fetch_html=fh, fetch_bytes=fb)
        self.assertEqual(0, got["맞음"])
        self.assertEqual(1, got["없음"])

    def test_far_hash_does_not_match(self):
        fh, fb = self._fetchers(~self.local_phash & ((1 << 64) - 1))   # 거리 64
        got = matching.match_by_hash(self.con, "op5321", threshold=6,
                                     fetch_html=fh, fetch_bytes=fb)
        self.assertEqual(0, got["맞음"])
        self.assertEqual(1, got["없음"])

    def test_exact_threshold_distance_matches(self):
        """거리가 정확히 threshold면 매칭입니다. dist 초기값이 threshold+1이라야

        `if d < dist`에서 threshold 자신도 통과합니다. 초기값을 threshold로
        "정리"하면 이 경계가 조용히 없음으로 바뀝니다.
        """
        fh, fb = self._fetchers(self.local_phash ^ 0b111111)   # 거리 정확히 6
        got = matching.match_by_hash(self.con, "op5321", threshold=6,
                                     fetch_html=fh, fetch_bytes=fb)
        self.assertEqual(1, got["맞음"])
        row = self.con.execute(
            "SELECT sha256, match FROM blog_image WHERE filename='네이버가_바꾼이름.jpg'"
        ).fetchone()
        self.assertEqual(("aaa", "dhash"), row)

    def test_already_matched_rows_are_skipped(self):
        self.con.execute("UPDATE blog_image SET sha256='aaa', match='name'")
        self.con.commit()
        fh, fb = self._fetchers(self.local_phash)
        got = matching.match_by_hash(self.con, "op5321", fetch_html=fh, fetch_bytes=fb)
        self.assertEqual({"맞음": 0, "없음": 0, "실패": 0}, got)

    def test_fetch_failure_is_counted_not_raised(self):
        def boom(blog_id, log_no):
            raise OSError("네트워크 실패")
        got = matching.match_by_hash(self.con, "op5321", fetch_html=boom,
                                     fetch_bytes=lambda url: b"")
        self.assertEqual(1, got["실패"])


if __name__ == "__main__":
    unittest.main()
