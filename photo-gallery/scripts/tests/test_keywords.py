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


class TestRealSuffix(unittest.TestCase):
    """exiftool 이 "내용이 딴판" 이라고 말한 경우에만 폴백을 씁니다."""

    def test_reads_the_type_exiftool_named(self):
        self.assertEqual(".jpg", keywords._real_suffix(
            "Error: Not a valid PNG (looks more like a JPEG) - /x/a.PNG"))

    def test_handles_the_article_an(self):
        self.assertEqual(".mp4", keywords._real_suffix(
            "Error: Not a valid MOV (looks more like an MP4) - /x/a.MOV"))

    def test_unrelated_error_is_not_a_mismatch(self):
        self.assertIsNone(keywords._real_suffix(
            "Error: File format error - /x/a.jpg"))

    def test_unknown_type_is_not_a_mismatch(self):
        self.assertIsNone(keywords._real_suffix(
            "Error: Not a valid JPEG (looks more like a DOCX) - /x/a.jpg"))


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

    def test_appledouble_sidecar_is_removed(self):
        """exFAT 에서는 exiftool 이 쓸 때마다 "._이름" 짝꿍이 생깁니다.

        macOS 가 com.apple.provenance 확장속성을 붙이는데 exFAT 에 담을 자리가
        없어서입니다. 그대로 두면 이 디스크를 윈도우에 꽂을 때 전부 보입니다.
        테스트 임시폴더는 APFS 라 짝꿍이 저절로 생기지 않으므로 직접 만들어
        둡니다. 지우는 코드가 없으면 그대로 남습니다.
        """
        (self.root / "._a.jpg").write_bytes(b"\x00\x05\x16\x07")
        (self.root / "._a.jpg_exiftool_tmp").write_bytes(b"\x00\x05\x16\x07")
        keywords.write(self.root / "a.jpg", ["가"])
        self.assertFalse((self.root / "._a.jpg").exists())
        self.assertFalse((self.root / "._a.jpg_exiftool_tmp").exists())
        self.assertEqual(["가"], keywords.read(self.root / "a.jpg"))

    def test_writes_to_a_file_whose_extension_lies(self):
        """이름만 .PNG 인 JPEG 입니다. T7 에 실제로 5장 있습니다.

        exiftool 은 확장자와 내용이 어긋나면 쓰기를 거부하고 -m 으로도 안 됩니다.
        """
        liar = self.root / "b.PNG"
        liar.write_bytes(helpers.jpeg_bytes())
        keywords.write(liar, ["스크린샷"])
        self.assertEqual(["스크린샷"], keywords.read(liar))

    def test_a_lying_extension_keeps_the_image_intact(self):
        """되돌려 놓다가 잘리면 사진이 망가집니다."""
        liar = self.root / "b.PNG"
        data = helpers.jpeg_bytes()
        liar.write_bytes(data)
        keywords.write(liar, ["스크린샷"])
        after = liar.read_bytes()
        self.assertTrue(after.startswith(b"\xff\xd8"), "JPEG 가 아닙니다")
        self.assertGreaterEqual(len(after), len(data))

    def test_no_work_file_is_left_behind(self):
        liar = self.root / "b.PNG"
        liar.write_bytes(helpers.jpeg_bytes())
        keywords.write(liar, ["스크린샷"])
        leftovers = [p.name for p in self.root.iterdir()
                     if "키워드작업" in p.name]
        self.assertEqual([], leftovers)

    def test_a_real_failure_still_raises(self):
        """확장자 불일치가 아닌 오류를 조용히 삼키면 안 됩니다."""
        broken = self.root / "c.jpg"
        broken.write_bytes(b"this is not an image at all")
        with self.assertRaises(RuntimeError):
            keywords.write(broken, ["스크린샷"])

    def test_other_files_sidecars_are_left_alone(self):
        """폴더를 쓸어 담으면 안 됩니다. 건드린 그 파일의 짝꿍만 지웁니다."""
        (self.root / "._남의파일.jpg").write_bytes(b"\x00\x05\x16\x07")
        keywords.write(self.root / "a.jpg", ["가"])
        self.assertTrue((self.root / "._남의파일.jpg").exists())


if __name__ == "__main__":
    unittest.main()
