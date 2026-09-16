#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""placement.py 회귀 검사.

    python3 photo-gallery/scripts/tests/test_placement.py
"""
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import index  # noqa: E402
import placement  # noqa: E402


class TestResolveCollisions(unittest.TestCase):
    def test_same_dst_different_content_gets_suffix(self):
        rows = [{"src": "a", "dst": "사진/2026/05/x.jpg", "sha256": "aa"},
                {"src": "b", "dst": "사진/2026/05/x.jpg", "sha256": "bb"}]
        got = placement.resolve_collisions(rows)
        self.assertEqual("사진/2026/05/x.jpg", got[0]["dst"])
        self.assertEqual("사진/2026/05/x_2.jpg", got[1]["dst"])

    def test_three_way_collision(self):
        rows = [{"src": f"s{i}", "dst": "사진/2026/05/x.jpg", "sha256": f"h{i}"}
                for i in range(3)]
        got = placement.resolve_collisions(rows)
        self.assertEqual(["사진/2026/05/x.jpg", "사진/2026/05/x_2.jpg",
                          "사진/2026/05/x_3.jpg"], [r["dst"] for r in got])

    def test_untouched_when_no_collision(self):
        rows = [{"src": "a", "dst": "사진/2026/05/x.jpg", "sha256": "aa"},
                {"src": "b", "dst": "사진/2026/05/y.jpg", "sha256": "bb"}]
        got = placement.resolve_collisions(rows)
        self.assertEqual(["사진/2026/05/x.jpg", "사진/2026/05/y.jpg"],
                         [r["dst"] for r in got])


class TestValidate(unittest.TestCase):
    def test_reports_duplicate_destination(self):
        rows = [{"src": "a", "dst": "d", "sha256": "aa", "action": "복사"},
                {"src": "b", "dst": "d", "sha256": "bb", "action": "복사"}]
        self.assertTrue(any("목적지 충돌" in m for m in placement.validate(rows)))

    def test_reports_source_used_twice(self):
        rows = [{"src": "a", "dst": "d1", "sha256": "aa", "action": "복사"},
                {"src": "a", "dst": "d2", "sha256": "aa", "action": "복사"}]
        self.assertTrue(any("출처 중복" in m for m in placement.validate(rows)))

    def test_clean_plan_has_no_problems(self):
        rows = [{"src": "a", "dst": "d1", "sha256": "aa", "action": "복사"},
                {"src": "b", "dst": "d2", "sha256": "bb", "action": "복사"}]
        self.assertEqual([], placement.validate(rows))


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = index.open_db(pathlib.Path(self.tmp.name) / "i.sqlite")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def photo(self, sha, path, kind="사진", shot="2026-05-01T15:53:39", phash=None, eid=None):
        # phash 를 넘길 때는 probe.phash_to_db() 가 만든 16진수 문자열이어야 합니다.
        self.con.execute(
            "INSERT INTO photo(sha256, path, bytes, width, height, kind, shot_at,"
            " shot_at_src, phash, event_id, origin, imported_at)"
            " VALUES(?,?,1000,100,100,?,?,'exif',?,?,'/o','t')",
            (sha, path, kind, shot, phash, eid))
        self.con.execute("INSERT INTO file(path, sha256, bytes, seen_at) VALUES(?,?,1000,'t')",
                         (path, sha))

    def test_photo_goes_to_year_month(self):
        self.photo("aa", "old/IMG_1.jpg")
        self.con.commit()
        rows = placement.build(self.con)
        self.assertEqual("사진/2026/05/20260501_155339_IMG_1.jpg", rows[0]["dst"])
        self.assertEqual("복사", rows[0]["action"])

    def test_orphan_file_row_refuses_to_plan(self):
        """photo 행이 없는 file 행은 조용히 건너뛰면 안 됩니다.

        이 함수는 파일을 옮기기 직전의 마지막 관문이라, 빠진 파일은 갤러리에
        영영 도착하지 않는데 아무도 모릅니다. 지금은 외래키가 막아 주지만
        그 보장이 코드 밖에 있으므로 여기서도 막습니다.
        """
        self.photo("aa", "old/IMG_1.jpg")
        self.con.commit()
        # PRAGMA 는 트랜잭션 밖에서만 먹습니다. 커밋 뒤에 끕니다.
        self.con.execute("PRAGMA foreign_keys = OFF")
        self.con.execute("INSERT INTO file(path, sha256, bytes, seen_at)"
                         " VALUES('old/고아.jpg','없는해시',1000,'t')")
        self.con.commit()
        with self.assertRaises(RuntimeError) as caught:
            placement.build(self.con)
        self.assertIn("고아.jpg", str(caught.exception))

    def test_screenshot_goes_to_screenshot_tree(self):
        self.photo("bb", "old/IMG_2.PNG", kind="스크린샷")
        self.con.commit()
        rows = placement.build(self.con)
        self.assertTrue(rows[0]["dst"].startswith("스크린샷/2026/05/"))

    def test_event_photo_goes_into_event_folder(self):
        self.con.execute("INSERT INTO event(id, folder, name, start_at, end_at)"
                         " VALUES(1,'20260501_성수 메가페스타 1차','성수',"
                         "'2026-05-01T13:30:00','2026-05-01T16:30:00')")
        self.photo("cc", "old/IMG_3.jpg", eid=1)
        self.con.commit()
        rows = placement.build(self.con)
        self.assertIn("/20260501_성수 메가페스타 1차/", rows[0]["dst"])

    def test_unknown_date_goes_to_quarantine_folder(self):
        self.photo("dd", "old/IMG_4.jpg", shot=None)
        self.con.commit()
        rows = placement.build(self.con)
        self.assertTrue(rows[0]["dst"].startswith("_시스템/미상날짜/"))

    def test_exact_duplicate_second_file_is_quarantined(self):
        self.photo("ee", "old/a/IMG_5.jpg")
        self.con.execute("INSERT INTO file(path, sha256, bytes, seen_at)"
                         " VALUES('old/b/IMG_5.jpg','ee',1000,'t')")
        self.con.commit()
        rows = placement.build(self.con)
        actions = sorted(r["action"] for r in rows)
        self.assertEqual(["격리", "복사"], actions)
        q = [r for r in rows if r["action"] == "격리"][0]
        self.assertTrue(q["dst"].startswith("_시스템/중복격리/"))

    def test_every_file_appears_exactly_once(self):
        self.photo("ff", "old/a/IMG_6.jpg")
        self.con.execute("INSERT INTO file(path, sha256, bytes, seen_at)"
                         " VALUES('old/b/IMG_6.jpg','ff',1000,'t')")
        self.photo("gg", "old/c/IMG_7.jpg")
        self.con.commit()
        rows = placement.build(self.con)
        self.assertEqual(3, len(rows))
        self.assertEqual(3, len({r["src"] for r in rows}))


if __name__ == "__main__":
    unittest.main()
