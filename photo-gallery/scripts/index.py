#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""갤러리 인덱스. 사람이 보는 조회 수단이 아니라 도구가 쓰는 장부입니다.

키를 경로가 아니라 sha256으로 잡습니다. 폴더를 바꾸거나 사진을 옮겨도 분류가 따라옵니다.
"""
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
  log_no    TEXT PRIMARY KEY,
  title     TEXT NOT NULL,
  tag       TEXT,
  posted_at TEXT
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


def open_db(path):
    """스키마를 보장하고 커넥션을 돌려줍니다."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(DDL)
    con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (SCHEMA_VERSION,))
    con.commit()
    return con
