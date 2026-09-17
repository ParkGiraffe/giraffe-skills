#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""초안 meta.json의 상대 경로 해석과 스크립트의 리포 경로 계산을 검사한다."""
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "blog" / "scripts"))
sys.path.insert(0, str(REPO / "_lib"))
import paste_to_naver as P  # noqa: E402
import upload_to_editor as U  # noqa: E402
import upload_video as V  # noqa: E402


class RepoPathTest(unittest.TestCase):
    def test_repo_constants_point_to_repo_root(self):
        self.assertEqual(pathlib.Path(U.REPO).resolve(), REPO)
        self.assertEqual(pathlib.Path(V.REPO).resolve(), REPO)


class ImagesDirTest(unittest.TestCase):
    def setUp(self):
        self.td = pathlib.Path(tempfile.mkdtemp())
        (self.td / "images").mkdir()
        (self.td / "images" / "001.jpg").write_bytes(b"x")

    def tearDown(self):
        shutil.rmtree(self.td)

    def _meta(self, source_folder):
        (self.td / "meta.json").write_text(json.dumps({"images": {"source_folder": source_folder}}), encoding="utf-8")

    def test_relative_source_folder_resolves_against_draft(self):
        self._meta("images")
        self.assertEqual(P.resolve_images_dir(self.td, None), (self.td / "images").resolve())

    def test_absolute_source_folder_is_kept(self):
        self._meta(str((self.td / "images").resolve()))
        self.assertEqual(P.resolve_images_dir(self.td, None), (self.td / "images").resolve())

    def test_missing_folder_returns_none(self):
        self._meta("nope")
        self.assertIsNone(P.resolve_images_dir(self.td, None))


class VideosFolderTest(unittest.TestCase):
    def test_relative_videos_folder_resolves_against_draft(self):
        td = pathlib.Path(tempfile.mkdtemp())
        try:
            self.assertEqual(U.resolve_videos_folder(td, "."), td.resolve())
            self.assertEqual(U.resolve_videos_folder(td, "images"), (td / "images").resolve())
            self.assertEqual(U.resolve_videos_folder(td, str(td.resolve())), td.resolve())
            self.assertIsNone(U.resolve_videos_folder(td, None))
        finally:
            shutil.rmtree(td)


if __name__ == "__main__":
    unittest.main(verbosity=2)
