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


if __name__ == "__main__":
    unittest.main(verbosity=2)
