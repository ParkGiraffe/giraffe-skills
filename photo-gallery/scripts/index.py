#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""갤러리 인덱스. 사람이 보는 조회 수단이 아니라 도구가 쓰는 장부입니다.

키를 경로가 아니라 sha256으로 잡습니다. 폴더를 바꾸거나 사진을 옮겨도 분류가 따라옵니다.
"""
import datetime as dt
import pathlib
import sqlite3

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS photo (
  sha256      TEXT PRIMARY KEY,
  path        TEXT NOT NULL,
  bytes       INTEGER NOT NULL,
  width       INTEGER,
  height      INTEGER,
  kind        TEXT NOT NULL,
  shot_at     TEXT,
  shot_at_src TEXT,
  make        TEXT,
  model       TEXT,
  gps_lat     REAL,
  gps_lon     REAL,
  phash       TEXT,
  event_id    INTEGER REFERENCES event(id),
  origin      TEXT NOT NULL,
  imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS photo_shot_at ON photo(shot_at);
CREATE INDEX IF NOT EXISTS photo_kind ON photo(kind);

CREATE TABLE IF NOT EXISTS file (
  path    TEXT PRIMARY KEY,
  sha256  TEXT NOT NULL REFERENCES photo(sha256),
  bytes   INTEGER NOT NULL,
  seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS file_sha ON file(sha256);

CREATE TABLE IF NOT EXISTS keyword (
  sha256 TEXT NOT NULL REFERENCES photo(sha256),
  word   TEXT NOT NULL,
  source TEXT NOT NULL,
  PRIMARY KEY (sha256, word)
);

CREATE TABLE IF NOT EXISTS event (
  id       INTEGER PRIMARY KEY,
  folder   TEXT NOT NULL UNIQUE,
  name     TEXT NOT NULL,
  start_at TEXT NOT NULL,
  end_at   TEXT NOT NULL,
  log_no   TEXT
);

CREATE TABLE IF NOT EXISTS blog_post (
  log_no              TEXT PRIMARY KEY,
  title               TEXT NOT NULL,
  tag                 TEXT,
  posted_at           TEXT,
  images_collected_at TEXT
);

CREATE TABLE IF NOT EXISTS blog_image (
  log_no   TEXT NOT NULL REFERENCES blog_post(log_no),
  filename TEXT NOT NULL,
  sha256   TEXT,
  match    TEXT,
  PRIMARY KEY (log_no, filename)
);

CREATE TABLE IF NOT EXISTS duplicate (
  sha256     TEXT NOT NULL PRIMARY KEY,
  keeper     TEXT NOT NULL,
  method     TEXT NOT NULL,
  quarantine TEXT NOT NULL,
  decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def _migrate(con):
    """DDL이 CREATE TABLE IF NOT EXISTS라서 이미 있는 표는 새 컬럼을 못 받습니다.

    옛 DB로 열었을 때 빠진 컬럼을 ALTER TABLE로 채웁니다. 새 DB는 DDL이 이미
    컬럼을 갖고 있으므로 여기서는 아무 일도 하지 않습니다.

    컬럼을 막 추가한 직후에는, 이미 blog_image 행이 있는 글의 images_collected_at도
    함께 채웁니다. 그러지 않으면 옛 스키마로 이미 다 받아 둔 글까지 컬럼이 없다는
    이유만으로 재실행 때 전부 다시 받습니다. 이미지가 0개라 blog_image 행이 없는
    글은 옛 스키마에서는 "받았는지" 구분할 수 없으므로 이번만 한 번 더 받게
    비워 둡니다. cmd_blog 가 그 글들을 받고 나면 images_collected_at이 채워집니다.
    """
    cols = {row[1] for row in con.execute("PRAGMA table_info(blog_post)")}
    if "images_collected_at" not in cols:
        con.execute("ALTER TABLE blog_post ADD COLUMN images_collected_at TEXT")
        con.execute(
            "UPDATE blog_post SET images_collected_at = ?"
            " WHERE log_no IN (SELECT DISTINCT log_no FROM blog_image)",
            (dt.datetime.now().isoformat(timespec="seconds"),))


def open_db(path):
    """스키마를 보장하고 커넥션을 돌려줍니다."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(DDL)
    _migrate(con)
    con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (SCHEMA_VERSION,))
    con.commit()
    return con
