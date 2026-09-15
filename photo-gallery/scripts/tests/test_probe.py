#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe.py 회귀 검사.

    python3 photo-gallery/scripts/tests/test_probe.py
"""
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import helpers  # noqa: E402
import probe  # noqa: E402


class TestHash(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_bytes_same_hash(self):
        data = helpers.jpeg_bytes()
        helpers.make_tree(self.root, {"a.jpg": data, "b/c.jpg": data})
        self.assertEqual(probe.sha256_of(self.root / "a.jpg"),
                         probe.sha256_of(self.root / "b/c.jpg"))

    def test_different_bytes_different_hash(self):
        helpers.make_tree(self.root, {
            "a.jpg": helpers.gradient_jpeg(seed=1),
            "b.jpg": helpers.gradient_jpeg(seed=2)})
        self.assertNotEqual(probe.sha256_of(self.root / "a.jpg"),
                            probe.sha256_of(self.root / "b.jpg"))


class TestDhash(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_recompressed_copy_is_near(self):
        helpers.make_tree(self.root, {
            "hi.jpg": helpers.gradient_jpeg(seed=5, quality=95),
            "lo.jpg": helpers.gradient_jpeg(seed=5, quality=40)})
        a = probe.dhash(self.root / "hi.jpg")
        b = probe.dhash(self.root / "lo.jpg")
        self.assertLessEqual(probe.hamming(a, b), 4)

    def test_different_images_are_far(self):
        helpers.make_tree(self.root, {
            "a.jpg": helpers.gradient_jpeg(seed=1),
            "b.jpg": helpers.gradient_jpeg(seed=99)})
        a = probe.dhash(self.root / "a.jpg")
        b = probe.dhash(self.root / "b.jpg")
        self.assertGreater(probe.hamming(a, b), 6)

    def test_non_image_returns_none(self):
        helpers.make_tree(self.root, {"v.mp4": b"not an image"})
        self.assertIsNone(probe.dhash(self.root / "v.mp4"))

    def test_dhash_bytes_agrees_with_file(self):
        data = helpers.gradient_jpeg(seed=11)
        helpers.make_tree(self.root, {"g.jpg": data})
        self.assertEqual(probe.dhash(self.root / "g.jpg"), probe.dhash_bytes(data))

    def test_dhash_bytes_on_garbage_returns_none(self):
        self.assertIsNone(probe.dhash_bytes(b"not an image"))


class TestPhashEncoding(unittest.TestCase):
    def test_round_trips(self):
        for value in (0, 1, (1 << 63), (1 << 64) - 1, 0x0123456789abcdef):
            self.assertEqual(value, probe.phash_from_db(probe.phash_to_db(value)))

    def test_always_sixteen_hex_digits(self):
        self.assertEqual("0000000000000001", probe.phash_to_db(1))
        self.assertEqual("ffffffffffffffff", probe.phash_to_db((1 << 64) - 1))

    def test_none_passes_through(self):
        self.assertIsNone(probe.phash_to_db(None))
        self.assertIsNone(probe.phash_from_db(None))

    def test_garbage_reads_as_none(self):
        self.assertIsNone(probe.phash_from_db("not hex"))


class TestExif(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_datetime_and_model(self):
        helpers.make_tree(self.root, {
            "a.jpg": helpers.jpeg_bytes(exif_dt="2026:05:01 15:53:39")})
        ex = probe.read_exif(self.root / "a.jpg")
        self.assertEqual("2026:05:01 15:53:39", ex["dt"])
        self.assertEqual("TestModel", ex["model"])

    def test_png_without_exif(self):
        helpers.make_tree(self.root, {"s.png": helpers.png_bytes()})
        ex = probe.read_exif(self.root / "s.png")
        self.assertIsNone(ex["dt"])
        self.assertIsNone(ex["make"])

    def test_reads_dimensions(self):
        helpers.make_tree(self.root, {"a.jpg": helpers.jpeg_bytes(w=120, h=90)})
        ex = probe.read_exif(self.root / "a.jpg")
        self.assertEqual((120, 90), (ex["width"], ex["height"]))

    def test_video_uses_exiftool_creation_date(self):
        """Pillow 는 동영상을 못 엽니다. exiftool 이 지역시각을 줍니다."""
        real = probe._video_datetime
        probe._video_datetime = lambda path: "2021:06:12 00:28:03+09:00"
        self.addCleanup(lambda: setattr(probe, "_video_datetime", real))
        helpers.make_tree(self.root, {"v.mov": b"not really a video"})
        self.assertEqual("2021:06:12 00:28:03+09:00",
                         probe.read_exif(self.root / "v.mov")["dt"])

    def test_video_without_any_date(self):
        real = probe._video_datetime
        probe._video_datetime = lambda path: None
        self.addCleanup(lambda: setattr(probe, "_video_datetime", real))
        helpers.make_tree(self.root, {"v.mp4": b"not really a video"})
        ex = probe.read_exif(self.root / "v.mp4")
        self.assertIsNone(ex["dt"])
        self.assertIsNone(ex["width"])


class TestClassify(unittest.TestCase):
    def test_samsung_screenshot(self):
        self.assertEqual("스크린샷", probe.classify(
            "Screenshot_20260501_155542_Pokmon GO.jpg", {"make": "samsung"}))

    def test_samsung_screenshot_dash_form(self):
        self.assertEqual("스크린샷", probe.classify(
            "Screenshot_20181127-151357_Samsung Internet.jpg", {"make": None}))

    def test_iphone_png_without_make(self):
        self.assertEqual("스크린샷", probe.classify("IMG_2713.PNG", {"make": None}))

    def test_png_with_camera_make_is_photo(self):
        self.assertEqual("사진", probe.classify("IMG_2713.PNG", {"make": "Apple"}))

    def test_korean_screenshot_word(self):
        self.assertEqual("스크린샷", probe.classify(
            "스크린샷 2024-12-27 오전 12.23.38.png", {"make": None}))

    def test_pc_game_shipping(self):
        self.assertEqual("스크린샷", probe.classify(
            "Client-Win64-Shipping Screenshot 2024.11.29 - 00.42.30.13.png", {"make": None}))

    def test_video(self):
        self.assertEqual("동영상", probe.classify("20181205_163103.mp4", {"make": None}))
        self.assertEqual("동영상", probe.classify("IMG_0047.MOV", {"make": None}))

    def test_ordinary_photo(self):
        self.assertEqual("사진", probe.classify("20260501_140726.jpg", {"make": "samsung"}))
        self.assertEqual("사진", probe.classify("IMG_0047.JPG", {"make": None}))


if __name__ == "__main__":
    unittest.main()
