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
        """공백이 "+" 로 오므로 unquote 가 아니라 unquote_plus 여야 합니다.

        픽스처 내용에 기대지 않습니다. 실제 제목 758개 중 10개는 "판타노 바인더 + 속지"
        처럼 정당하게 "+" 를 포함하므로, "제목에 + 가 없다" 로 단언하면 픽스처를
        갱신할 때 엉뚱하게 깨집니다.
        """
        sample = ('{"logNo":"1","title":"%5B%ED%8F%AC%EC%BC%93%EB%AA%AC%5D'
                  '+%EC%84%B1%EC%88%98","categoryNo":"1","addDate":"2026. 5. 1."}')
        self.assertEqual("[포켓몬] 성수", blog.parse_post_list(sample)[0]["title"])

    def test_html_entities_are_unescaped(self):
        """제목에 &#39; 가 그대로 오는 글이 758편 중 22편 있습니다.

        이 제목이 이벤트 폴더 이름이 되므로 풀어야 합니다.
        """
        sample = ('{"logNo":"1","title":"%5B%EB%8B%88%EC%BC%80%5D+%26%2339%3B'
                  '%EC%95%84%EB%8B%88%EC%8A%A4%26%2339%3B","categoryNo":"1",'
                  '"addDate":"2026. 1. 2."}')
        self.assertEqual("[니케] '아니스'", blog.parse_post_list(sample)[0]["title"])

    def test_fixture_titles_are_decoded(self):
        titles = [p["title"] for p in blog.parse_post_list(self.text)]
        self.assertFalse(any("%" in t for t in titles))
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
        """원본 src 에 이미 ?type=w80_blur 가 붙어 있습니다.

        떼지 않고 붙이면 "?" 가 두 개인 망가진 URL 이 됩니다. assertIn 으로는
        그 중복을 못 잡으므로 "?" 개수를 셉니다.
        """
        urls = blog.parse_image_urls(self.html)
        self.assertTrue(urls, "픽스처에서 이미지 URL 을 하나도 못 뽑았습니다")
        for _n, url in urls:
            self.assertTrue(url.startswith("http"), url)
            self.assertEqual(1, url.count("?"), url)
            self.assertTrue(url.endswith("?type=w3840"), url)


if __name__ == "__main__":
    unittest.main()
