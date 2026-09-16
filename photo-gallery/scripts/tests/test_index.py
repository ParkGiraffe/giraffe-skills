#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""index.py 회귀 검사.

    python3 photo-gallery/scripts/tests/test_index.py
"""
import pathlib
import sqlite3
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

    def test_phash_column_is_declared_text(self):
        """컬럼이 INTEGER 면 숫자로만 된 16진수 해시가 정수로 변환됩니다.

        선언 타입을 직접 확인합니다. 값을 넣어 보는 것만으로는 부족한데,
        16진수 글자가 섞인 값은 컬럼이 INTEGER 여도 문자열로 남기 때문입니다.
        """
        con = index.open_db(self.db)
        types = {row[1]: row[2] for row in con.execute("PRAGMA table_info(photo)")}
        self.assertEqual("TEXT", types["phash"])
        con.close()

    def test_raw_64bit_int_cannot_be_stored(self):
        """지각해시를 정수 그대로 넣으면 안 되는 이유를 못박아 둡니다.

        dHash 는 부호 없는 64비트라 최상위 비트가 1이면 2^63 을 넘습니다.
        16진수 문자열로 인코딩하는 이유가 이것입니다.
        """
        con = index.open_db(self.db)
        con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                    " VALUES('a','p',1,'사진','/o','t')")
        with self.assertRaises(OverflowError):
            con.execute("UPDATE photo SET phash=? WHERE sha256='a'", ((1 << 64) - 1,))
        con.close()

    def test_all_digit_phash_stays_text(self):
        """숫자로만 이루어진 16진수도 정수로 변환되면 안 됩니다."""
        con = index.open_db(self.db)
        con.execute("INSERT INTO photo(sha256, path, bytes, kind, origin, imported_at)"
                    " VALUES('b','q',1,'사진','/o','t')")
        con.execute("UPDATE photo SET phash='1234567890123456' WHERE sha256='b'")
        got = con.execute("SELECT phash FROM photo WHERE sha256='b'").fetchone()[0]
        self.assertIsInstance(got, str)
        con.close()

    def test_post_upsert_keeps_images_collected_at(self):
        """글 목록을 다시 받아도 수집 완료 표시가 살아남아야 합니다.

        INSERT OR REPLACE 는 행을 지우고 새로 넣어 이 컬럼을 NULL 로 만듭니다.
        그러면 재개 가능성이 통째로 무력화되므로 UPSERT 여야 합니다.
        """
        con = index.open_db(self.db)
        con.execute("INSERT INTO blog_post(log_no, title, tag, posted_at,"
                    " images_collected_at) VALUES('1','옛 제목','태그','d','t')")
        con.execute(
            "INSERT INTO blog_post(log_no, title, tag, posted_at) VALUES(?,?,?,?)"
            " ON CONFLICT(log_no) DO UPDATE SET"
            " title=excluded.title, tag=excluded.tag, posted_at=excluded.posted_at",
            ("1", "새 제목", "태그", "d"))
        row = con.execute(
            "SELECT title, images_collected_at FROM blog_post WHERE log_no='1'").fetchone()
        self.assertEqual(("새 제목", "t"), row)
        con.close()

    def test_migration_adds_images_collected_at(self):
        """옛 모양 blog_post 표에도 open_db 가 새 컬럼을 채워 넣어야 합니다.

        CREATE TABLE IF NOT EXISTS 는 이미 있는 표를 건드리지 않으므로, 컬럼을
        DDL에만 추가해서는 기존 DB가 못 따라옵니다. _migrate() 가 ALTER TABLE로
        메꾸는지 직접 확인합니다.
        """
        con = sqlite3.connect(str(self.db))
        con.execute("""
            CREATE TABLE blog_post (
              log_no    TEXT PRIMARY KEY,
              title     TEXT NOT NULL,
              tag       TEXT,
              posted_at TEXT
            )
        """)
        con.close()

        con = index.open_db(self.db)
        cols = {row[1] for row in con.execute("PRAGMA table_info(blog_post)")}
        self.assertIn("images_collected_at", cols)
        con.close()

    def test_migration_backfills_already_collected_posts(self):
        """blog_image 행이 있던 글은 컬럼이 막 생겨도 재수집 대상이 되면 안 됩니다.

        컬럼만 추가하고 비워 두면, 옛 스키마로 이미 이미지까지 받아 둔 글도
        images_collected_at이 없다는 이유만으로 cmd_blog가 재실행 때마다 다시
        받습니다. 이미지가 0개라 blog_image 행이 아예 없는 글은 옛 스키마로는
        "받았는지" 구분할 수 없으므로 비워 둔 채로 남아야 합니다.
        """
        con = sqlite3.connect(str(self.db))
        con.execute("""
            CREATE TABLE blog_post (
              log_no    TEXT PRIMARY KEY,
              title     TEXT NOT NULL,
              tag       TEXT,
              posted_at TEXT
            )
        """)
        con.execute("""
            CREATE TABLE blog_image (
              log_no   TEXT NOT NULL,
              filename TEXT NOT NULL,
              sha256   TEXT,
              match    TEXT,
              PRIMARY KEY (log_no, filename)
            )
        """)
        con.execute("INSERT INTO blog_post(log_no, title) VALUES('1', '이미지 있음')")
        con.execute("INSERT INTO blog_post(log_no, title) VALUES('2', '이미지 없음')")
        con.execute(
            "INSERT INTO blog_image(log_no, filename, match) VALUES('1','a.jpg','none')")
        con.commit()
        con.close()

        con = index.open_db(self.db)
        got = dict(con.execute("SELECT log_no, images_collected_at FROM blog_post"))
        self.assertIsNotNone(got["1"])
        self.assertIsNone(got["2"])
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
