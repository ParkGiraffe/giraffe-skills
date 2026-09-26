#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""naming.py 회귀 검사. 실제 T7에 있는 파일명 형태를 표본으로 씁니다.

    python3 photo-gallery/scripts/tests/test_naming.py
"""
import datetime as dt
import pathlib
import sys
import unittest
import unicodedata as ud

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
        """파일 시각을 받는 인자가 아예 없어야 합니다.

        받을 수 있게 열어 두면 언젠가 씁니다. mtime 은 복사와 이동으로 이미
        오염됐습니다. 허용 목록으로 잠급니다. origin 은 경로일 뿐 시각이
        아니어서 들어와도 됩니다.
        """
        import inspect
        allowed = {"basename", "exif_dt", "origin"}
        params = set(inspect.signature(naming.resolve_datetime).parameters)
        self.assertEqual(set(), params - allowed,
                         "날짜 출처가 될 수 있는 인자가 새로 들어왔습니다")

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

    def test_screenshot_sits_under_its_month(self):
        """스크린샷을 최상위에 따로 두지 않습니다. 그 달 사진 옆에 둡니다."""
        self.assertEqual("사진/2026/05/스크린샷/20260501_155542_Pokmon GO.jpg",
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
        self.assertEqual("날짜미상/IMG_2713.PNG",
                         naming.destination("사진", None, "IMG_2713.PNG"))


class TestEventFolderName(unittest.TestCase):
    def test_format(self):
        self.assertEqual("20260501_성수 메가페스타 1차",
                         naming.event_folder_name(dt.datetime(2026, 5, 1, 15, 0, 0),
                                                  "성수 메가페스타 1차"))

    def test_strips_path_separators(self):
        self.assertEqual("20260501_A B",
                         naming.event_folder_name(dt.datetime(2026, 5, 1), "A/B"))


class TestEpochAndDateOnly(unittest.TestCase):
    """카카오톡과 몇몇 앱은 받은 시각을 13자리 밀리초로 이름에 박습니다."""

    def test_kakao_epoch_millis(self):
        got, src = naming.resolve_datetime("kakaotalk_1545297538011.mp4", None)
        self.assertEqual("filename", src)
        self.assertEqual(dt.datetime(2018, 12, 20, 18, 18, 58), got)

    def test_epoch_millis_with_suffix(self):
        got, src = naming.resolve_datetime("1745920032694_100.PNG", None)
        self.assertEqual("filename", src)
        self.assertEqual(dt.datetime(2025, 4, 29, 18, 47, 12), got)

    def test_a_long_number_that_is_not_a_time_is_ignored(self):
        """0204160954458243256257 같은 이름을 시각으로 읽으면 안 됩니다."""
        got, src = naming.resolve_datetime("0204160954458243256257.jpg", None)
        self.assertIsNone(got)
        self.assertEqual("unknown", src)

    def test_epoch_outside_the_plausible_range_is_ignored(self):
        got, _src = naming.resolve_datetime("1000000000000.jpg", None)
        self.assertIsNotNone(got)
        got, src = naming.resolve_datetime("9999999999999.jpg", None)
        self.assertIsNone(got)

    def test_date_only_filename(self):
        got, src = naming.resolve_datetime("Selfie_20240529_박기린퍼_000.jpg", None)
        self.assertEqual(naming.FILENAME_DATE, src)
        self.assertEqual(dt.datetime(2024, 5, 29), got)

    def test_date_only_keeps_the_real_day(self):
        name = naming.normalize_name("Selfie_20240529_박기린퍼_000.jpg",
                                     dt.datetime(2024, 5, 29), naming.FILENAME_DATE)
        self.assertTrue(name.startswith("20240529_000000_"), name)

    def test_impossible_date_is_not_read(self):
        got, src = naming.resolve_datetime("x_20241345_y.jpg", None)
        self.assertIsNone(got)

    def test_full_timestamp_still_wins(self):
        """같은 이름에 둘 다 있으면 시각까지 있는 쪽을 씁니다."""
        got, src = naming.resolve_datetime("20181121_180959.jpg", None)
        self.assertEqual("filename", src)
        self.assertEqual(dt.datetime(2018, 11, 21, 18, 9, 59), got)


class TestOriginFolder(unittest.TestCase):
    """EXIF 도 파일명도 없으면 원본이 놓여 있던 폴더를 봅니다.

    사용자가 손으로 "2024/7월/포켓몬고페스트" 처럼 정리해 둔 경로라 mtime 과
    달리 복사로 오염되지 않습니다. 미상날짜 602장 중 539장이 여기서 살아납니다.
    """

    def test_year_and_korean_month(self):
        got, src = naming.resolve_datetime(
            "IMG_1234.jpg", None, "/T7/사진/아이폰 12 pro/2024/7월/포켓몬고페스트/IMG_1234.jpg")
        self.assertEqual(naming.FOLDER_MONTH, src)
        self.assertEqual((2024, 7), (got.year, got.month))

    def test_year_and_two_digit_month(self):
        got, src = naming.resolve_datetime(
            "IMG_1.jpg", None, "/T7/사진/아이폰 12 pro/2025/02/IMG_1.jpg")
        self.assertEqual(naming.FOLDER_MONTH, src)
        self.assertEqual((2025, 2), (got.year, got.month))

    def test_year_only(self):
        got, src = naming.resolve_datetime(
            "IMG_1.jpg", None, "/T7/사진/아이폰 12 pro/2023/IMG_1.jpg")
        self.assertEqual(naming.FOLDER_YEAR, src)
        self.assertEqual(2023, got.year)

    def test_nfd_month_folder(self):
        """exFAT 은 "7월" 도 NFD 로 돌려줍니다."""
        origin = ud.normalize("NFD", "/T7/아이폰 12 pro/2024/7월/IMG_1.jpg")
        got, src = naming.resolve_datetime("IMG_1.jpg", None, origin)
        self.assertEqual(naming.FOLDER_MONTH, src)
        self.assertEqual((2024, 7), (got.year, got.month))

    def test_no_year_in_path(self):
        got, src = naming.resolve_datetime(
            "IMG_1.jpg", None, "/T7/사진/동동이 사진/IMG_1.jpg")
        self.assertIsNone(got)
        self.assertEqual("unknown", src)

    def test_exif_still_wins_over_the_folder(self):
        """폴더는 월까지뿐입니다. EXIF 가 있으면 그것이 정확합니다."""
        got, src = naming.resolve_datetime(
            "IMG_1.jpg", "2024:03:16 19:30:21", "/T7/아이폰 12 pro/2020/1월/IMG_1.jpg")
        self.assertEqual("exif", src)
        self.assertEqual(dt.datetime(2024, 3, 16, 19, 30, 21), got)

    def test_filename_still_wins_over_the_folder(self):
        got, src = naming.resolve_datetime(
            "20181121_180959.jpg", None, "/T7/아이폰 12 pro/2020/1월/20181121_180959.jpg")
        self.assertEqual("filename", src)
        self.assertEqual(dt.datetime(2018, 11, 21, 18, 9, 59), got)

    def test_a_folder_that_is_not_a_year_is_ignored(self):
        got, src = naming.resolve_datetime(
            "IMG_1.jpg", None, "/T7/1999년기록/13월/IMG_1.jpg")
        self.assertIsNone(got)


class TestMonthOnlyStamp(unittest.TestCase):
    """날짜를 모르면 그 자리를 00 으로 둡니다. 없는 날을 지어내지 않습니다."""

    def test_month_only_name(self):
        got = naming.normalize_name(
            "IMG_1234.jpg", dt.datetime(2024, 7, 1), naming.FOLDER_MONTH)
        self.assertEqual("20240700_000000_IMG_1234.jpg", got)

    def test_year_only_name(self):
        got = naming.normalize_name(
            "IMG_1.jpg", dt.datetime(2023, 1, 1), naming.FOLDER_YEAR)
        self.assertEqual("20230000_000000_IMG_1.jpg", got)

    def test_exact_date_is_unchanged(self):
        got = naming.normalize_name("IMG_1.jpg", dt.datetime(2024, 7, 11, 9, 30, 12))
        self.assertEqual("20240711_093012_IMG_1.jpg", got)

    def test_month_only_sorts_after_nothing_in_that_month(self):
        """이름만으로 시간순 정렬되는 성질이 유지돼야 합니다."""
        names = sorted([
            naming.normalize_name("b.jpg", dt.datetime(2024, 7, 11, 9, 30, 12)),
            naming.normalize_name("a.jpg", dt.datetime(2024, 7, 1), naming.FOLDER_MONTH),
            naming.normalize_name("c.jpg", dt.datetime(2024, 8, 2, 1, 0, 0)),
        ])
        self.assertEqual(["20240700_000000_a.jpg", "20240711_093012_b.jpg",
                          "20240802_010000_c.jpg"], names)

    def test_month_only_goes_to_its_month_folder(self):
        got = naming.destination("사진", dt.datetime(2024, 7, 1),
                                 "20240700_000000_IMG_1.jpg", src=naming.FOLDER_MONTH)
        self.assertEqual("사진/2024/07/20240700_000000_IMG_1.jpg", got)

    def test_year_only_stays_in_the_unknown_folder(self):
        """월을 모르면 월 폴더를 정할 수 없습니다. 01 에서 12 만 씁니다."""
        got = naming.destination("사진", dt.datetime(2023, 1, 1),
                                 "20230000_000000_IMG_1.jpg", src=naming.FOLDER_YEAR)
        self.assertEqual("날짜미상/20230000_000000_IMG_1.jpg", got)


class TestUndatedPlacement(unittest.TestCase):
    """날짜를 못 정한 사진도 갤러리 안에 둡니다.

    _시스템 밑에 두면 도구가 쓰는 파일처럼 보이는데, 그 사진들은 사용자가 가진
    유일본입니다. 앱을 거치며 EXIF 가 떨어져 나간 것뿐입니다.
    """

    def test_a_curated_subject_folder_is_kept_whole(self):
        """사람이 주제로 묶어 둔 폴더는 그 묶음 자체가 정보입니다."""
        got = naming.destination("사진", None, "IMG_1.JPG", group="동동이 사진")
        self.assertEqual("동동이 사진/IMG_1.JPG", got)

    def test_a_dated_photo_in_a_subject_folder_stays_there(self):
        """연/월로 흩으면 135장이 30개 폴더로 흩어집니다."""
        got = naming.destination("사진", dt.datetime(2020, 1, 15, 14, 30, 22),
                                 "20200115_143022_IMG_1.JPG", group="동동이 사진")
        self.assertEqual("동동이 사진/20200115_143022_IMG_1.JPG", got)

    def test_an_unlisted_subject_goes_to_the_undated_folder(self):
        got = naming.destination("사진", None, "IMG_1.JPG", group="어떤 폴더")
        self.assertEqual("날짜미상/어떤 폴더/IMG_1.JPG", got)

    def test_without_a_subject_it_sits_at_the_top(self):
        got = naming.destination("사진", None, "IMG_1.JPG")
        self.assertEqual("날짜미상/IMG_1.JPG", got)

    def test_it_is_not_under_the_system_folder(self):
        got = naming.destination("사진", None, "IMG_1.JPG", group="어떤 폴더")
        self.assertFalse(got.startswith("_시스템"), got)

    def test_a_date_structured_root_is_not_a_subject(self):
        """아이폰 12 pro 는 밑에 연/월이 들어 있어 날짜가 곧 구조입니다."""
        self.assertNotIn("아이폰 12 pro", naming.SUBJECT_ROOTS)
        self.assertNotIn("카메라 앨범", naming.SUBJECT_ROOTS)


class TestSubjectFolder(unittest.TestCase):
    def test_last_non_date_folder_wins(self):
        self.assertEqual("동동이 사진", naming.subject_folder(
            "002_Areas/001_사진/동동이 사진/IMG_1.JPG"))

    def test_date_folders_are_skipped(self):
        self.assertEqual("아이폰 12 pro", naming.subject_folder(
            "002_Areas/001_사진/아이폰 12 pro/2024/7월/IMG_1.JPG"))

    def test_the_innermost_subject_wins(self):
        self.assertEqual("포켓몬고페스트", naming.subject_folder(
            "002_Areas/001_사진/아이폰 12 pro/2024/7월/포켓몬고페스트/IMG_1.JPG"))

    def test_nfd_folder_name(self):
        got = naming.subject_folder(
            ud.normalize("NFD", "002_Areas/001_사진/동동이 사진/IMG_1.JPG"))
        self.assertEqual("동동이 사진", got)

    def test_no_folder_at_all(self):
        self.assertIsNone(naming.subject_folder("IMG_1.JPG"))


class TestMonthRangeFolder(unittest.TestCase):
    """1월-2월 처럼 두 달에 걸친 폴더는 시작 월을 씁니다.

    여러 날에 걸친 행사 폴더가 시작일만 쓰는 것과 같은 규칙입니다.
    """

    def test_korean_month_range(self):
        got, src = naming.resolve_datetime(
            "IMG_1835.JPG", None, "/T7/아이폰 12 pro/2023/1월-2월/IMG_1835.JPG")
        self.assertEqual(naming.FOLDER_MONTH, src)
        self.assertEqual((2023, 1), (got.year, got.month))

    def test_range_with_spaces(self):
        got, src = naming.resolve_datetime(
            "IMG_1.JPG", None, "/T7/아이폰 12 pro/2023/11월 - 12월/IMG_1.JPG")
        self.assertEqual((2023, 11), (got.year, got.month))

    def test_a_single_month_still_works(self):
        got, src = naming.resolve_datetime(
            "IMG_1.JPG", None, "/T7/아이폰 12 pro/2024/7월/IMG_1.JPG")
        self.assertEqual((2024, 7), (got.year, got.month))

    def test_a_nonsense_range_is_not_a_month(self):
        got, src = naming.resolve_datetime(
            "IMG_1.JPG", None, "/T7/아이폰 12 pro/2024/13월-99월/IMG_1.JPG")
        self.assertEqual(naming.FOLDER_YEAR, src)


class TestNfdFilenames(unittest.TestCase):
    """exFAT 은 한글 파일명을 NFD 로 돌려줍니다.

    이 파일의 정규식에 든 "오전|오후" 와 "스크린샷" 은 NFC 라, 정규화하지
    않으면 맥 스크린샷 이름이 하나도 안 맞습니다. 실제로 10장이 통째로
    미상날짜로 갔습니다.
    """

    def test_ampm_screenshot_in_nfd(self):
        nfd = ud.normalize("NFD", "스크린샷 2024-11-04 오후 10.24.12.png")
        when, src = naming.resolve_datetime(nfd, None)
        self.assertEqual("filename", src)
        self.assertEqual(dt.datetime(2024, 11, 4, 22, 24, 12), when)

    def test_nfc_and_nfd_agree(self):
        nfc = "스크린샷 2024-12-26 오전 5.22.13.png"
        nfd = ud.normalize("NFD", nfc)
        self.assertNotEqual(nfc, nfd, "시험할 값이 NFD 로 달라야 합니다")
        self.assertEqual(naming.resolve_datetime(nfc, None),
                         naming.resolve_datetime(nfd, None))

    def test_normalize_name_handles_nfd(self):
        nfd = ud.normalize("NFD", "스크린샷 2024-11-04 오후 10.24.12.png")
        got = naming.normalize_name(nfd, dt.datetime(2024, 11, 4, 22, 24, 12))
        self.assertEqual("20241104_222412_스크린샷.png", ud.normalize("NFC", got))


if __name__ == "__main__":
    unittest.main()
