#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""keywords.py 회귀 검사. exiftool이 없으면 쓰기 검사는 건너뜁니다.

    python3 photo-gallery/scripts/tests/test_keywords.py
"""
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import helpers  # noqa: E402
import index  # noqa: E402
import keywords  # noqa: E402

VOCAB = HERE.parent.parent / "references" / "vocab.md"
HAS_EXIFTOOL = shutil.which("exiftool") is not None


class TestVocab(unittest.TestCase):
    def test_loads_mapping(self):
        got = keywords.load_vocab(VOCAB)
        self.assertEqual("포켓몬 GO", got["Pokmon GO"])
        self.assertEqual("두근두근타운", got["Heartopia"])
        self.assertEqual("명조", got["Wuthering Waves"])

    def test_does_not_transliterate_unknown(self):
        got = keywords.load_vocab(VOCAB)
        self.assertNotIn("SomeUnknownApp", got)

    def test_hierarchy_table_does_not_pollute_vocab(self):
        """같은 파일에 표가 둘이라 거르지 않으면 어휘가 오염됩니다."""
        got = keywords.load_vocab(VOCAB)
        for key, value in got.items():
            self.assertNotIn("|", value, f"{key} 에 계층이 섞였습니다")
        self.assertNotIn("포켓몬 GO", got, "계층 표의 잎이 앱 내부명으로 들어왔습니다")


class TestAppName(unittest.TestCase):
    def test_extracts_app_from_samsung_screenshot(self):
        self.assertEqual("Pokmon GO",
                         keywords.app_name("Screenshot_20260501_155542_Pokmon GO.jpg"))

    def test_dash_form(self):
        self.assertEqual("Samsung Internet",
                         keywords.app_name("Screenshot_20181127-151357_Samsung Internet.jpg"))

    def test_no_app_part(self):
        self.assertIsNone(keywords.app_name("Screenshot_20181129-163555.jpg"))

    def test_not_a_screenshot(self):
        self.assertIsNone(keywords.app_name("IMG_1027.PNG"))


class TestHierarchy(unittest.TestCase):
    def setUp(self):
        self.hier = keywords.load_hierarchy(VOCAB)

    def test_loads_hierarchy_table(self):
        self.assertEqual("포켓몬|포켓몬 GO", self.hier["포켓몬 GO"])
        self.assertEqual("게임|명조", self.hier["명조"])

    def test_maps_known_leaves_only(self):
        got = keywords.hierarchical(["포켓몬 GO", "딸"], self.hier)
        self.assertEqual(["포켓몬|포켓몬 GO"], got)

    def test_empty_when_nothing_matches(self):
        self.assertEqual([], keywords.hierarchical(["딸", "블로그"], self.hier))


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = index.open_db(pathlib.Path(self.tmp.name) / "i.sqlite")
        self.vocab = keywords.load_vocab(VOCAB)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_app_name_becomes_keyword(self):
        self.con.execute(
            "INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
            " VALUES('a','g/x.jpg',1,'스크린샷',"
            "'/o/Screenshot_20260501_155542_Pokmon GO.jpg','t')")
        self.con.commit()
        self.assertIn("포켓몬 GO", keywords.collect(self.con, "a", self.vocab))

    def test_blog_tag_becomes_keyword(self):
        self.con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                         " VALUES('b','g/y.jpg',1,'사진','/o/y.jpg','t')")
        self.con.execute("INSERT INTO blog_post(log_no, title, tag)"
                         " VALUES('1','[명조] 무언가','명조')")
        self.con.execute("INSERT INTO blog_image(log_no, filename, sha256, match)"
                         " VALUES('1','y.jpg','b','name')")
        self.con.commit()
        self.assertIn("명조", keywords.collect(self.con, "b", self.vocab))

    def test_event_name_becomes_keyword(self):
        self.con.execute("INSERT INTO event(id, folder, name, start_at, end_at)"
                         " VALUES(1,'20260501_성수','성수 메가페스타 1차','s','e')")
        self.con.execute("INSERT INTO photo(sha256, path, bytes, kind, event_id,"
                         " origin, imported_at) VALUES('c','g/z.jpg',1,'사진',1,'/o/z.jpg','t')")
        self.con.commit()
        self.assertIn("성수 메가페스타 1차", keywords.collect(self.con, "c", self.vocab))

    def test_manual_keywords_are_included(self):
        self.con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                         " VALUES('d','g/w.jpg',1,'사진','/o/w.jpg','t')")
        self.con.execute("INSERT INTO keyword(sha256, word, source) VALUES('d','딸','manual')")
        self.con.commit()
        self.assertIn("딸", keywords.collect(self.con, "d", self.vocab))

    def test_no_duplicates_and_sorted(self):
        self.con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                         " VALUES('e','g/v.jpg',1,'사진','/o/v.jpg','t')")
        self.con.execute("INSERT INTO keyword(sha256, word, source) VALUES('e','나','manual')")
        self.con.execute("INSERT INTO keyword(sha256, word, source) VALUES('e','가','rule')")
        self.con.commit()
        got = keywords.collect(self.con, "e", self.vocab)
        self.assertEqual(sorted(set(got)), got)


@unittest.skipUnless(HAS_EXIFTOOL, "exiftool 없음")
class TestWriteRead(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        helpers.make_tree(self.root, {"a.jpg": helpers.jpeg_bytes()})

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip_korean_keywords(self):
        keywords.write(self.root / "a.jpg", ["포켓몬 GO", "딸", "성수 메가페스타 1차"])
        got = keywords.read(self.root / "a.jpg")
        self.assertEqual({"포켓몬 GO", "딸", "성수 메가페스타 1차"}, set(got))

    def test_hierarchy_goes_to_its_own_field(self):
        keywords.write(self.root / "a.jpg", ["포켓몬 GO"], ["포켓몬|포켓몬 GO"])
        self.assertEqual(["포켓몬 GO"], keywords.read(self.root / "a.jpg"))
        self.assertEqual(["포켓몬|포켓몬 GO"], keywords.read_hierarchy(self.root / "a.jpg"))

    def test_rewrite_replaces_not_appends(self):
        keywords.write(self.root / "a.jpg", ["가"])
        keywords.write(self.root / "a.jpg", ["나"])
        self.assertEqual(["나"], keywords.read(self.root / "a.jpg"))

    def test_shrinking_hierarchy_clears_stale_value(self):
        """계층이 있던 사진이 재기록 때 계층 없음으로 바뀌면 옛 계층이 남으면 안 됩니다."""
        keywords.write(self.root / "a.jpg", ["포켓몬 GO"], ["포켓몬|포켓몬 GO"])
        keywords.write(self.root / "a.jpg", ["딸"], [])
        self.assertEqual([], keywords.read_hierarchy(self.root / "a.jpg"))

    def test_no_backup_file_is_left(self):
        keywords.write(self.root / "a.jpg", ["가"])
        self.assertFalse((self.root / "a.jpg_original").exists())


if __name__ == "__main__":
    unittest.main()
