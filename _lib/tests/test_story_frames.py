#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""story_frames 회귀 검사. 합성 이미지로 유형 추정, 같은 구도 묶기, 렌더를 확인한다."""
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import story_frames as sf  # noqa: E402


def base_frame(seed: int) -> Image.Image:
    """seed에 따라 상단 색이 달라지는 1920x1080 배경. 밝기는 80 이상이라 어두운 영역이 없다."""
    im = Image.new("RGB", sf.FRAME)
    d = ImageDraw.Draw(im)
    for y in range(0, 1080, 20):
        d.rectangle([0, y, 1920, y + 20], fill=(60 + seed * 40, 120, 80 + y // 10))
    return im


def with_subtitle(im: Image.Image, text: str) -> Image.Image:
    d = ImageDraw.Draw(im)
    d.text((700, 900), text, fill="white", font=sf.load_font(48), stroke_width=3, stroke_fill="black")
    return im


def with_dialog(im: Image.Image, text: str) -> Image.Image:
    d = ImageDraw.Draw(im)
    d.rectangle([600, 780, 1560, 980], fill=(15, 15, 15))
    d.text((640, 850), text, fill="white", font=sf.load_font(40), stroke_width=2, stroke_fill="black")
    return im


def result_screen() -> Image.Image:
    im = Image.new("RGB", sf.FRAME, (200, 190, 170))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 100, 1920, 220], fill=(40, 30, 20))
    font = sf.load_font(36)
    for label, top in (("배틀 클리어", 330), ("격파 수", 425), ("클리어 타임", 520)):
        d.rectangle([310, top, 1060, top + 70], fill=(30, 30, 30))
        d.text((350, top + 15), label, fill="white", font=font)
        d.text((950, top + 15), "500", fill="white", font=font)
    return im


class ClassifyTest(unittest.TestCase):
    def test_plain_gradient(self):
        self.assertEqual(sf.classify(base_frame(0)), "plain")

    def test_subtitle_text_in_band(self):
        self.assertEqual(sf.classify(with_subtitle(base_frame(0), "여기가 과거라는 것을 확인합니다")), "subtitle")

    def test_dialog_box_beats_subtitle(self):
        self.assertEqual(sf.classify(with_dialog(base_frame(0), "라울님, 지금 도착했어요")), "dialog")

    def test_result_screen(self):
        self.assertEqual(sf.classify(result_screen()), "result")


class FramingTest(unittest.TestCase):
    def test_same_top_different_subtitle_is_same_framing(self):
        a = with_subtitle(base_frame(0), "첫 번째 대사입니다")
        b = with_subtitle(base_frame(0), "두 번째 대사입니다")
        self.assertTrue(sf.same_framing(a, b))
        self.assertLess(sf.frame_diff(a, b), 0.02)

    def test_different_top_is_not_same_framing(self):
        self.assertFalse(sf.same_framing(base_frame(0), base_frame(3)))


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.td = pathlib.Path(tempfile.mkdtemp())
        self.ep = self.td / "01_1장 시작의 대지로"
        self.ep.mkdir()
        self.orig = self.td / "orig"
        self.orig.mkdir()
        with_subtitle(base_frame(0), "여기가 과거라는 것을 확인합니다").save(self.ep / "001_#0_2026072007314700_s.jpg")
        with_subtitle(base_frame(0), "봉인 전쟁이라고 부르는 시대입니다").save(self.ep / "002_#1_2026072007315200_s.jpg")
        with_subtitle(base_frame(0), "타이틀이 뜨고 이야기가 시작됩니다").save(self.ep / "003_#2_2026072007321700_s.jpg")
        base_frame(3).save(self.ep / "004_#3_2026072007332400_s.jpg")
        result_screen().save(self.ep / "005_#4_2026072007342300_s.jpg")
        # 손 크롭본과 그 원본
        base_frame(5).crop((0, 830, 827, 1083)).save(self.ep / "006_#5_2026072007342500_s.jpg")
        base_frame(5).save(self.orig / "2026072007342500_s.jpg")
        (self.ep / "._006_#5_2026072007342500_s.jpg").write_bytes(b"x")

    def tearDown(self):
        shutil.rmtree(self.td)

    def test_build_plan_groups_strips_skips_result_and_restores_originals(self):
        plan = sf.build_plan(self.ep, self.orig, threshold=0.10)
        self.assertEqual(plan["sections"][0]["title"], "1장 시작의 대지로")
        items = plan["sections"][0]["items"]
        self.assertEqual([it["type"] for it in items], ["strip", "photo", "skip", "photo"])
        self.assertEqual(items[0]["band"], "subtitle")
        self.assertTrue(items[0]["lead"].endswith("001_#0_2026072007314700_s.jpg"))
        self.assertEqual(len(items[0]["src"]), 2)
        self.assertEqual(items[2]["reason"], "결과 화면")
        self.assertTrue(items[3]["src"].endswith("orig/2026072007342500_s.jpg"))
        self.assertEqual(items[3]["hand_crop"], "006_#5_2026072007342500_s.jpg")

    def test_build_plan_without_originals_keeps_hand_crop_as_plain(self):
        plan = sf.build_plan(self.ep, None, threshold=0.10)
        last = plan["sections"][0]["items"][-1]
        self.assertEqual(last["type"], "photo")
        self.assertEqual(last["guess"], "plain")
        self.assertNotIn("hand_crop", last)

    def test_render_sheets_one_row_per_item(self):
        plan = sf.build_plan(self.ep, self.orig, threshold=0.10)
        out = self.td / "work"
        out.mkdir()
        sheets = sf.render_sheets(plan, out, per_sheet=3, thumb=(160, 90))
        self.assertEqual([p.name for p in sheets], ["sheet_01.jpg", "sheet_02.jpg"])
        with Image.open(sheets[0]) as im:
            self.assertEqual(im.size, (300 + 6 * 160, 3 * (90 + 8)))
        with Image.open(sheets[1]) as im2:
            self.assertEqual(im2.height, 1 * (90 + 8))


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.td = pathlib.Path(tempfile.mkdtemp())
        self.src = self.td / "src"
        self.src.mkdir()
        self.a = str(self.src / "a.jpg")
        self.b = str(self.src / "b.jpg")
        self.c = str(self.src / "c.jpg")
        self.d = str(self.src / "d.jpg")
        with_subtitle(base_frame(0), "여기가 과거라는 것을 확인합니다").save(self.a)
        with_subtitle(base_frame(0), "봉인 전쟁이라고 부르는 시대입니다").save(self.b)
        with_subtitle(base_frame(0), "타이틀이 뜨고 이야기가 시작됩니다").save(self.c)
        base_frame(2).save(self.d)
        self.plan = {"source": str(self.src), "originals": None, "threshold": 0.10, "sections": [
            {"title": "시작의 대지로", "items": [
                {"type": "photo", "src": self.d, "guess": "plain"},
                {"type": "strip", "lead": self.a, "src": [self.b, self.c], "band": "subtitle", "guess": "subtitle"},
                {"type": "heading", "title": "하이랄 성"},
                {"type": "crop", "src": self.d, "preset": "popup"},
                {"type": "skip", "src": self.d, "guess": "result", "reason": "결과 화면"},
                {"type": "video", "file": "01_v01_시작의 대지 도착.mp4", "title": "시작의 대지 도착"},
            ]},
            {"title": "검술 훈련", "items": [
                {"type": "photo", "src": self.d, "guess": "plain"},
            ]},
        ]}

    def tearDown(self):
        shutil.rmtree(self.td)

    def test_make_strip_size(self):
        im = sf.make_strip([self.b, self.c], "subtitle")
        self.assertEqual(im.size, (1920, 200 * 2 + sf.SEP))

    def test_crop_preset_size(self):
        self.assertEqual(sf.crop_preset(self.d, "popup").size, (1123, 966))

    def test_render_writes_images_script_and_meta(self):
        out = self.td / "draft"
        meta = sf.render(self.plan, out, title="[젤다무쌍 봉인전기] 1. 테스트", category="젤다무쌍 봉인전기",
                         category_no=None, date="2026-09-03", watermark=False)
        names = sorted(p.name for p in (out / "images").iterdir())
        self.assertEqual(names, ["001.jpg", "002.jpg", "002_strip.jpg", "003_crop.jpg", "004.jpg"])
        with Image.open(out / "images" / "002_strip.jpg") as im:
            self.assertEqual(im.size, (1920, 404))
        self.assertEqual(meta["images"]["count"], 5)
        self.assertEqual(meta["videos"], [{"file": "01_v01_시작의 대지 도착.mp4", "title": "시작의 대지 도착"}])
        self.assertEqual(meta["videos_folder"], str((out / "images").resolve()))
        self.assertEqual(meta["title_candidates"], ["[젤다무쌍 봉인전기] 1. 테스트"])
        md = (out / "script.md").read_text(encoding="utf-8")
        self.assertIn('title: "[젤다무쌍 봉인전기] 1. 테스트"', md)
        self.assertIn("# [젤다무쌍 봉인전기] 1. 테스트", md)
        self.assertIn("## 시작의 대지로", md)
        self.assertIn("### 하이랄 성", md)
        self.assertIn("![](images/002.jpg)\n\n![](images/002_strip.jpg)\n\n<!-- 캡션 -->", md)
        self.assertIn("[영상 자리 : images/01_v01_시작의 대지 도착.mp4]", md)
        self.assertIn("\n---\n\n## 검술 훈련", md)
        self.assertEqual(json.loads((out / "meta.json").read_text(encoding="utf-8"))["images"]["count"], 5)


class CheckTest(unittest.TestCase):
    def test_caption_with_period_passes(self):
        md = "![](images/001.jpg)\n\n라울이 젤다를 찾고 있었다고 말합니다.\n"
        self.assertEqual(sf.check_captions(md), [])

    def test_caption_without_period_is_reported(self):
        md = "![](images/001.jpg)\n\n라울이 젤다를 찾고 있었다고 말합니다\n"
        self.assertEqual([p[0] for p in sf.check_captions(md)], [3])

    def test_empty_caption_mark_is_reported(self):
        md = "![](images/001.jpg)\n\n<!-- 캡션 -->\n"
        self.assertEqual(len(sf.check_captions(md)), 1)

    def test_consecutive_images_and_video_slots_are_allowed(self):
        md = "![](images/001.jpg)\n\n![](images/002.jpg)\n\n[영상 자리 : images/v.mp4]\n\n## 소제목\n\n설명입니다.\n"
        self.assertEqual(sf.check_captions(md), [])

    def test_intro_mark_is_reported(self):
        md = "# 제목\n\n<!-- 도입 -->\n\n![](images/001.jpg)\n\n설명입니다.\n"
        self.assertEqual([p[1] for p in sf.check_captions(md)], ["도입이 비어 있습니다"])

    def test_caption_spanning_two_lines_passes(self):
        md = "![](images/001.jpg)\n\n라울이 젤다를\n찾고 있었다고 말합니다.\n"
        self.assertEqual(sf.check_captions(md), [])

    def test_two_line_caption_without_period_reports_last_line(self):
        md = "![](images/001.jpg)\n\n라울이 젤다를\n찾고 있었다고 말합니다\n"
        self.assertEqual([p[0] for p in sf.check_captions(md)], [4])


if __name__ == "__main__":
    unittest.main(verbosity=2)
