#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""events.py 회귀 검사.

    python3 photo-gallery/scripts/tests/test_events.py
"""
import datetime as dt
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import events  # noqa: E402
import index  # noqa: E402


class TestWindow(unittest.TestCase):
    def test_adds_margin_both_sides(self):
        shots = [dt.datetime(2026, 5, 1, 14, 0), dt.datetime(2026, 5, 1, 16, 0)]
        start, end = events.window(shots, margin_minutes=30)
        self.assertEqual(dt.datetime(2026, 5, 1, 13, 30), start)
        self.assertEqual(dt.datetime(2026, 5, 1, 16, 30), end)

    def test_single_shot(self):
        shots = [dt.datetime(2026, 5, 1, 14, 0)]
        start, end = events.window(shots, margin_minutes=30)
        self.assertEqual(dt.datetime(2026, 5, 1, 13, 30), start)
        self.assertEqual(dt.datetime(2026, 5, 1, 14, 30), end)


class TestDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = index.open_db(pathlib.Path(self.tmp.name) / "i.sqlite")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def photo(self, sha, shot, kind="사진"):
        self.con.execute(
            "INSERT INTO photo(sha256, path, bytes, kind, shot_at, shot_at_src,"
            " origin, imported_at) VALUES(?,?,1,?,?,'exif','/o','t')",
            (sha, "g/" + sha + ".jpg", kind, shot))

    def post(self, log_no, title, shas):
        self.con.execute("INSERT INTO blog_post(log_no, title, tag, posted_at)"
                         " VALUES(?,?,NULL,'2026. 5. 2.')", (log_no, title))
        for i, sha in enumerate(shas):
            self.con.execute(
                "INSERT INTO blog_image(log_no, filename, sha256, match)"
                " VALUES(?,?,?,'name')", (log_no, f"f{i}.jpg", sha))


class TestCandidates(TestDb):
    def test_tight_cluster_becomes_candidate(self):
        for i in range(4):
            self.photo(f"s{i}", f"2026-05-01T14:0{i}:00")
        self.post("1", "[포켓몬 팝업] 성수 메가페스타 1차 방문기 : 스탬프", [f"s{i}" for i in range(4)])
        self.con.commit()
        got = events.candidates(self.con)
        self.assertEqual(1, len(got))
        self.assertEqual("성수 메가페스타 1차", got[0]["name"])

    def test_scattered_guide_post_is_rejected(self):
        """게임 공략글은 스크린샷이 몇 달에 걸쳐 있어 행사가 아닙니다."""
        for i, month in enumerate((1, 4, 7, 11)):
            self.photo(f"g{i}", f"2026-{month:02d}-10T14:00:00")
        self.post("2", "[원신 공략] 이나즈마 연하궁", [f"g{i}" for i in range(4)])
        self.con.commit()
        self.assertEqual([], events.candidates(self.con))

    def test_too_few_photos_is_rejected(self):
        self.photo("x0", "2026-05-01T14:00:00")
        self.photo("x1", "2026-05-01T14:01:00")
        self.post("3", "[포켓몬 팝업] 작은 행사", ["x0", "x1"])
        self.con.commit()
        self.assertEqual([], events.candidates(self.con, min_photos=3))

    def test_window_covers_all_matched_photos(self):
        self.photo("w0", "2026-05-01T14:00:00")
        self.photo("w1", "2026-05-01T16:00:00")
        self.photo("w2", "2026-05-01T15:00:00")
        self.post("4", "[포켓몬 팝업] 성수", ["w0", "w1", "w2"])
        self.con.commit()
        got = events.candidates(self.con)[0]
        self.assertEqual(dt.datetime(2026, 5, 1, 13, 30), got["start"])
        self.assertEqual(dt.datetime(2026, 5, 1, 16, 30), got["end"])


class TestScreenshotsInWindow(TestDb):
    def test_finds_only_screenshots_inside(self):
        self.photo("in", "2026-05-01T15:55:42", kind="스크린샷")
        self.photo("out", "2026-05-01T22:00:00", kind="스크린샷")
        self.photo("photo", "2026-05-01T15:00:00", kind="사진")
        self.con.commit()
        got = events.screenshots_in_window(
            self.con, dt.datetime(2026, 5, 1, 13, 30), dt.datetime(2026, 5, 1, 16, 30))
        self.assertEqual(["in"], [r[0] for r in got])


class TestAssign(TestDb):
    def test_assigns_screenshot_to_event(self):
        """시간창 안 스크린샷 약 270장을 사람이 보고 판정한 결과를 기록합니다."""
        self.con.execute("INSERT INTO event(id, folder, name, start_at, end_at)"
                         " VALUES(1,'20260501_성수','성수','s','e')")
        self.photo("ss", "2026-05-01T15:55:42", kind="스크린샷")
        self.con.commit()
        self.assertEqual(1, events.assign(self.con, 1, ["ss"]))
        got = self.con.execute("SELECT event_id FROM photo WHERE sha256='ss'").fetchone()[0]
        self.assertEqual(1, got)

    def test_unassign_clears(self):
        self.con.execute("INSERT INTO event(id, folder, name, start_at, end_at)"
                         " VALUES(1,'20260501_성수','성수','s','e')")
        self.photo("ss", "2026-05-01T15:55:42", kind="스크린샷")
        self.con.commit()
        events.assign(self.con, 1, ["ss"])
        self.assertEqual(1, events.unassign(self.con, ["ss"]))
        self.assertIsNone(
            self.con.execute("SELECT event_id FROM photo WHERE sha256='ss'").fetchone()[0])


class TestUniqueFolder(TestDb):
    def test_free_name_is_returned_as_is(self):
        self.con.commit()
        self.assertEqual("20260530_띵조페스티벌 2026",
                         events.unique_folder(self.con, "20260530_띵조페스티벌 2026"))

    def test_taken_name_gets_a_suffix(self):
        """1/2, 2/2 다회차 글이 같은 날 같은 이름을 내놓습니다.

        event.folder 에 UNIQUE 가 걸려 있어 그대로 저장하면
        FOREIGN KEY constraint failed 로 죽습니다.
        """
        self.con.execute("INSERT INTO event(folder, name, start_at, end_at)"
                         " VALUES('20260530_띵조페스티벌 2026','x','s','e')")
        self.con.commit()
        self.assertEqual("20260530_띵조페스티벌 2026_2",
                         events.unique_folder(self.con, "20260530_띵조페스티벌 2026"))

    def test_many_collisions_need_a_real_loop(self):
        """증가가 두 번 이상 필요한 경우를 넣습니다.

        미리 채운 이름이 둘뿐이면 증가가 한 번이면 끝나서, while 을 단일 if 로
        바꿔도 통과합니다. 그러면 1/3 2/3 3/3 처럼 같은 날 세 편이 나올 때
        조용히 깨집니다. 셋을 채워 두 번 돌게 만듭니다.
        """
        for suffix in ("", "_2", "_3"):
            self.con.execute("INSERT INTO event(folder, name, start_at, end_at)"
                             " VALUES(?,'x','s','e')", ("20260530_행사" + suffix,))
        self.con.commit()
        self.assertEqual("20260530_행사_4",
                         events.unique_folder(self.con, "20260530_행사"))


class TestSave(TestDb):
    def test_writes_event_and_links_photos(self):
        for i in range(3):
            self.photo(f"s{i}", f"2026-05-01T14:0{i}:00")
        self.post("1", "[포켓몬 팝업] 성수 메가페스타 1차 방문기", [f"s{i}" for i in range(3)])
        self.con.commit()
        cand = events.candidates(self.con)[0]
        eid = events.save(self.con, cand, "20260501_성수 메가페스타 1차")
        row = self.con.execute("SELECT folder, name, log_no FROM event WHERE id=?",
                               (eid,)).fetchone()
        self.assertEqual(("20260501_성수 메가페스타 1차", "성수 메가페스타 1차", "1"), row)
        n = self.con.execute("SELECT COUNT(*) FROM photo WHERE event_id=?", (eid,)).fetchone()[0]
        self.assertEqual(3, n)


if __name__ == "__main__":
    unittest.main()
