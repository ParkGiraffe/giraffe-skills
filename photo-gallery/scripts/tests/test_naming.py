#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""naming.py 회귀 검사. 실제 T7에 있는 파일명 형태를 표본으로 씁니다.

    python3 photo-gallery/scripts/tests/test_naming.py
"""
import datetime as dt
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import naming  # noqa: E402


class TestResolveDatetime(unittest.TestCase):
    def test_exif_wins(self):
        got, src = naming.resolve_datetime("IMG_2713.PNG", "2024:03:16 19:30:21")
        self.assertEqual(dt.datetime(2024, 3, 16, 19, 30, 21), got)
        self.assertEqual("exif", src)

    def test_samsung_underscore(self):
        got, src = naming.resolve_datetime("20181121_180959.jpg", None)
        self.assertEqual(dt.datetime(2018, 11, 21, 18, 9, 59), got)
        self.assertEqual("filename", src)

    def test_samsung_dash(self):
        got, _ = naming.resolve_datetime("20181216-135720.jpg", None)
        self.assertEqual(dt.datetime(2018, 12, 16, 13, 57, 20), got)

    def test_samsung_screenshot(self):
        got, _ = naming.resolve_datetime("Screenshot_20260501_155542_Pokmon GO.jpg", None)
        self.assertEqual(dt.datetime(2026, 5, 1, 15, 55, 42), got)

    def test_samsung_screenshot_dash(self):
        got, _ = naming.resolve_datetime("Screenshot_20181127-151357_Samsung Internet.jpg", None)
        self.assertEqual(dt.datetime(2018, 11, 27, 15, 13, 57), got)

    def test_ios_millisecond_form(self):
        got, _ = naming.resolve_datetime("20201115_072644083_iOS.jpg", None)
        self.assertEqual(dt.datetime(2020, 11, 15, 7, 26, 44), got)

    def test_game_prefix_dashes(self):
        got, _ = naming.resolve_datetime("별이되어라_2018-12-20-00-13-57.jpg", None)
        self.assertEqual(dt.datetime(2018, 12, 20, 0, 13, 57), got)

    def test_mac_screenshot_24h(self):
        got, _ = naming.resolve_datetime("스크린샷 2024-12-21 145611.png", None)
        self.assertEqual(dt.datetime(2024, 12, 21, 14, 56, 11), got)

    def test_mac_screenshot_afternoon(self):
        got, _ = naming.resolve_datetime("스크린샷 2024-12-26 오후 5.22.13.png", None)
        self.assertEqual(dt.datetime(2024, 12, 26, 17, 22, 13), got)

    def test_mac_screenshot_midnight(self):
        got, _ = naming.resolve_datetime("스크린샷 2024-12-27 오전 12.23.38.png", None)
        self.assertEqual(dt.datetime(2024, 12, 27, 0, 23, 38), got)

    def test_unreal_shipping_form(self):
        got, _ = naming.resolve_datetime(
            "Client-Win64-Shipping Screenshot 2024.11.29 - 00.42.30.13.png", None)
        self.assertEqual(dt.datetime(2024, 11, 29, 0, 42, 30), got)

    def test_already_normalized(self):
        got, _ = naming.resolve_datetime("20240108_072733_IMG_1027.PNG", None)
        self.assertEqual(dt.datetime(2024, 1, 8, 7, 27, 33), got)

    def test_no_date_anywhere(self):
        got, src = naming.resolve_datetime("IMG_2713.PNG", None)
        self.assertIsNone(got)
        self.assertEqual("unknown", src)

    def test_kakao_video_has_no_date(self):
        got, src = naming.resolve_datetime("_talkv_wu895sf0Jj_x_talkv_high.mp4", None)
        self.assertIsNone(got)
        self.assertEqual("unknown", src)

    def test_mtime_is_never_used(self):
        """파일 mtime을 받는 인자가 아예 없어야 합니다."""
        import inspect
        self.assertEqual(["basename", "exif_dt"],
                         list(inspect.signature(naming.resolve_datetime).parameters))

    def test_bad_exif_falls_back_to_filename(self):
        got, src = naming.resolve_datetime("20181121_180959.jpg", "0000:00:00 00:00:00")
        self.assertEqual(dt.datetime(2018, 11, 21, 18, 9, 59), got)
        self.assertEqual("filename", src)


class TestNormalizeName(unittest.TestCase):
    D = dt.datetime(2024, 3, 16, 19, 30, 21)

    def test_already_normalized_is_untouched(self):
        self.assertEqual("20240108_072733_IMG_1027.PNG",
                         naming.normalize_name("20240108_072733_IMG_1027.PNG",
                                               dt.datetime(2024, 1, 8, 7, 27, 33)))

    def test_bare_dated_name_is_untouched(self):
        self.assertEqual("20181121_180959.jpg",
                         naming.normalize_name("20181121_180959.jpg",
                                               dt.datetime(2018, 11, 21, 18, 9, 59)))

    def test_plain_name_gets_prefix(self):
        self.assertEqual("20240316_193021_IMG_2713.PNG",
                         naming.normalize_name("IMG_2713.PNG", self.D))

    def test_samsung_screenshot_keeps_app_name(self):
        d = dt.datetime(2026, 5, 1, 15, 55, 42)
        self.assertEqual("20260501_155542_Pokmon GO.jpg",
                         naming.normalize_name("Screenshot_20260501_155542_Pokmon GO.jpg", d))

    def test_samsung_screenshot_without_app(self):
        d = dt.datetime(2018, 11, 29, 16, 35, 55)
        self.assertEqual("20181129_163555_Screenshot.jpg",
                         naming.normalize_name("Screenshot_20181129-163555.jpg", d))

    def test_ios_millisecond_form(self):
        d = dt.datetime(2020, 11, 15, 7, 26, 44)
        self.assertEqual("20201115_072644_iOS.jpg",
                         naming.normalize_name("20201115_072644083_iOS.jpg", d))

    def test_game_prefix_is_kept(self):
        d = dt.datetime(2018, 12, 20, 0, 13, 57)
        self.assertEqual("20181220_001357_별이되어라.jpg",
                         naming.normalize_name("별이되어라_2018-12-20-00-13-57.jpg", d))

    def test_dashed_bare_date_becomes_canonical(self):
        d = dt.datetime(2018, 12, 16, 13, 57, 20)
        self.assertEqual("20181216_135720.jpg",
                         naming.normalize_name("20181216-135720.jpg", d))


class TestDestination(unittest.TestCase):
    D = dt.datetime(2026, 5, 1, 15, 53, 39)

    def test_photo_without_event(self):
        self.assertEqual("사진/2026/05/20260501_155339_IMG_1.jpg",
                         naming.destination("사진", self.D, "20260501_155339_IMG_1.jpg"))

    def test_photo_in_event(self):
        self.assertEqual("사진/2026/05/20260501_성수 메가페스타 1차/20260501_155339_IMG_1.jpg",
                         naming.destination("사진", self.D, "20260501_155339_IMG_1.jpg",
                                            "20260501_성수 메가페스타 1차"))

    def test_screenshot_default(self):
        self.assertEqual("스크린샷/2026/05/20260501_155542_Pokmon GO.jpg",
                         naming.destination("스크린샷", self.D, "20260501_155542_Pokmon GO.jpg"))

    def test_screenshot_pulled_into_event(self):
        self.assertEqual("사진/2026/05/20260501_성수 메가페스타 1차/20260501_155542_Pokmon GO.jpg",
                         naming.destination("스크린샷", self.D, "20260501_155542_Pokmon GO.jpg",
                                            "20260501_성수 메가페스타 1차"))

    def test_video_lives_with_photos(self):
        self.assertEqual("사진/2026/05/20260501_155339_v.mp4",
                         naming.destination("동영상", self.D, "20260501_155339_v.mp4"))

    def test_month_is_zero_padded(self):
        d = dt.datetime(2024, 3, 5, 1, 2, 3)
        self.assertTrue(naming.destination("사진", d, "x.jpg").startswith("사진/2024/03/"))

    def test_unknown_date_goes_to_quarantine(self):
        self.assertEqual("_시스템/미상날짜/IMG_2713.PNG",
                         naming.destination("사진", None, "IMG_2713.PNG"))


class TestEventFolderName(unittest.TestCase):
    def test_format(self):
        self.assertEqual("20260501_성수 메가페스타 1차",
                         naming.event_folder_name(dt.datetime(2026, 5, 1, 15, 0, 0),
                                                  "성수 메가페스타 1차"))

    def test_strips_path_separators(self):
        self.assertEqual("20260501_A B",
                         naming.event_folder_name(dt.datetime(2026, 5, 1), "A/B"))


if __name__ == "__main__":
    unittest.main()
