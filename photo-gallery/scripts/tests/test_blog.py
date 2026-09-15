#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blog.py 파싱 회귀 검사. 네트워크를 타지 않습니다.

    python3 photo-gallery/scripts/tests/test_blog.py
"""
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import blog  # noqa: E402

FIX = HERE / "fixtures"


class TestPostList(unittest.TestCase):
    def setUp(self):
        self.text = (FIX / "post_list.txt").read_text(encoding="utf-8", errors="replace")

    def test_parses_thirty_posts(self):
        got = blog.parse_post_list(self.text)
        self.assertEqual(30, len(got))

    def test_log_no_is_digits(self):
        for p in blog.parse_post_list(self.text):
            self.assertTrue(p["log_no"].isdigit(), p)

    def test_title_is_url_decoded(self):
        titles = [p["title"] for p in blog.parse_post_list(self.text)]
        self.assertFalse(any("+" in t and "%" in t for t in titles))
        self.assertTrue(any("[" in t for t in titles))


class TestSplitTag(unittest.TestCase):
    def test_extracts_bracket_tag(self):
        tag, rest = blog.split_tag("[포켓몬 팝업] 성수 메가페스타 1차 방문기 : 포켓몬고 스탬프")
        self.assertEqual("포켓몬 팝업", tag)
        self.assertEqual("성수 메가페스타 1차 방문기 : 포켓몬고 스탬프", rest)

    def test_no_tag(self):
        tag, rest = blog.split_tag("2025년 종합 회고")
        self.assertIsNone(tag)
        self.assertEqual("2025년 종합 회고", rest)


class TestEventName(unittest.TestCase):
    def test_drops_tag_and_subtitle(self):
        self.assertEqual(
            "성수 메가페스타 1차",
            blog.event_name("[포켓몬 팝업] 성수 메가페스타 1차 방문기 : 포켓몬고 스탬프와 올리브영 콜라보"))

    def test_drops_visit_suffix_forms(self):
        self.assertEqual("잠실 무릉도원 팝업스토어",
                         blog.event_name("[포켓몬 팝업] 잠실 무릉도원 팝업스토어 방문기 : 1622팀 웨이팅"))
        self.assertEqual("띵조페스티벌 2026",
                         blog.event_name("[명조 팝업] 띵조페스티벌 2026 방문기 (2/2) : 굿즈샵 입장"))

    def test_keeps_plain_title(self):
        self.assertEqual("포켓몬 메가페스타 in 성수",
                         blog.event_name("포켓몬 메가페스타 in 성수.. 오픈 하루만에 입장 중단!!!!"))


class TestImageNames(unittest.TestCase):
    def setUp(self):
        self.html = (FIX / "post_view.html").read_text(encoding="utf-8", errors="replace")

    def test_finds_image_filenames(self):
        got = blog.parse_image_names(self.html)
        self.assertGreater(len(got), 0)

    def test_names_have_extensions(self):
        for name in blog.parse_image_names(self.html):
            self.assertRegex(name.lower(), r"\.(jpg|jpeg|png|gif|webp|heic)$")

    def test_names_are_not_url_encoded(self):
        for name in blog.parse_image_names(self.html):
            self.assertNotIn("%", name)


class TestImageUrls(unittest.TestCase):
    def setUp(self):
        self.html = (FIX / "post_view.html").read_text(encoding="utf-8", errors="replace")

    def test_same_filenames_as_parse_image_names(self):
        self.assertEqual(blog.parse_image_names(self.html),
                         [n for n, _u in blog.parse_image_urls(self.html)])

    def test_urls_are_absolute_and_full_quality(self):
        for _n, url in blog.parse_image_urls(self.html):
            self.assertTrue(url.startswith("http"), url)
            self.assertIn("type=w3840", url)


if __name__ == "__main__":
    unittest.main()
