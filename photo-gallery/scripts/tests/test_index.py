#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""index.py 회귀 검사.

    python3 photo-gallery/scripts/tests/test_index.py
"""
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import index  # noqa: E402


class TestSchema(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "index.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_all_tables(self):
        con = index.open_db(self.db)
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(
            {"photo", "file", "keyword", "event", "blog_post", "blog_image",
             "duplicate", "meta"},
            names - {"sqlite_sequence"})
        con.close()

    def test_reopen_is_idempotent(self):
        index.open_db(self.db).close()
        con = index.open_db(self.db)
        # meta.value 는 TEXT 라서 SQLite 가 정수를 문자열로 바꿔 저장합니다.
        # 읽어 온 값이 문자열인 것이 정상입니다.
        self.assertEqual(str(index.SCHEMA_VERSION),
                         con.execute("SELECT value FROM meta WHERE key='schema_version'")
                            .fetchone()[0])
        con.close()

    def test_photo_primary_key_is_sha256(self):
        con = index.open_db(self.db)
        con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                    " VALUES('a', 'p1', 1, '사진', '/x', '2026-01-01')")
        with self.assertRaises(Exception):
            con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                        " VALUES('a', 'p2', 1, '사진', '/y', '2026-01-01')")
        con.close()

    def test_many_files_can_share_one_photo(self):
        """바이트가 같은 파일이 여러 곳에 있어도 각각을 기억해야 격리할 수 있습니다."""
        con = index.open_db(self.db)
        con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                    " VALUES('a', 'p1', 1, '사진', '/x', '2026-01-01')")
        con.execute("INSERT INTO file(path, sha256, bytes, seen_at)"
                    " VALUES('p1','a',1,'2026-01-01')")
        con.execute("INSERT INTO file(path, sha256, bytes, seen_at)"
                    " VALUES('p2','a',1,'2026-01-01')")
        n = con.execute("SELECT COUNT(*) FROM file WHERE sha256='a'").fetchone()[0]
        self.assertEqual(2, n)
        con.close()

    def test_keyword_is_unique_per_photo(self):
        con = index.open_db(self.db)
        con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                    " VALUES('a', 'p1', 1, '사진', '/x', '2026-01-01')")
        con.execute("INSERT INTO keyword(sha256, word, source) VALUES('a','게임','blog')")
        with self.assertRaises(Exception):
            con.execute("INSERT INTO keyword(sha256, word, source) VALUES('a','게임','manual')")
        con.close()


if __name__ == "__main__":
    unittest.main()
