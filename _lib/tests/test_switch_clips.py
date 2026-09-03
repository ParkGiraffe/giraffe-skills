#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""switch_clips 회귀 검사. ffmpeg가 없으면 영상 통합 테스트는 건너뛴다."""
import datetime as dt
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import switch_clips as sc  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def clip(file, end, dur):
    return {"file": file, "end": end, "dur": dur, "mb": 1.0}


class StampTest(unittest.TestCase):
    def test_parse_stamp_reads_first_14_digits(self):
        self.assertEqual(sc.parse_stamp("2026072007441100_s.mp4"),
                         dt.datetime(2026, 7, 20, 7, 44, 11))

    def test_parse_stamp_rejects_names_without_stamp(self):
        with self.assertRaises(ValueError):
            sc.parse_stamp("clip.mp4")


class GroupTest(unittest.TestCase):
    def test_contiguous_clips_join_and_gap_splits(self):
        clips = [clip("2026090300000300_s.mp4", "2026-09-03T00:00:03", 3.0),
                 clip("2026090300000600_s.mp4", "2026-09-03T00:00:06", 3.0),
                 clip("2026090300001500_s.mp4", "2026-09-03T00:00:15", 3.0)]
        s = sc.group_sessions(clips, gap=3.0)
        self.assertEqual([x["files"] for x in s],
                         [[clips[0]["file"], clips[1]["file"]], [clips[2]["file"]]])
        self.assertEqual(s[0]["id"], "S01")
        self.assertEqual(s[1]["id"], "S02")
        self.assertAlmostEqual(s[0]["total"], 6.0)
        self.assertEqual(s[0]["durs"], [3.0, 3.0])
        self.assertEqual(s[0]["start"], "2026-09-03T00:00:00")
        self.assertEqual(s[0]["end"], "2026-09-03T00:00:06")

    def test_gap_boundary_is_inclusive(self):
        clips = [clip("2026090300000300_s.mp4", "2026-09-03T00:00:03", 3.0),
                 clip("2026090300000900_s.mp4", "2026-09-03T00:00:09", 3.0)]
        self.assertEqual(len(sc.group_sessions(clips, gap=3.0)), 1)
        self.assertEqual(len(sc.group_sessions(clips, gap=2.9)), 2)

    def test_unsorted_input_is_sorted_by_end(self):
        clips = [clip("2026090300000600_s.mp4", "2026-09-03T00:00:06", 3.0),
                 clip("2026090300000300_s.mp4", "2026-09-03T00:00:03", 3.0)]
        s = sc.group_sessions(clips)
        self.assertEqual(s[0]["files"], ["2026090300000300_s.mp4", "2026090300000600_s.mp4"])


def make_clip(path, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x180:rate=30",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    str(path)], check=True)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg 필요")
class ProbeTest(unittest.TestCase):
    def setUp(self):
        self.td = pathlib.Path(tempfile.mkdtemp())
        self.raw = self.td / "raw"
        self.raw.mkdir()
        make_clip(self.raw / "2026090300000300_s.mp4", 3)
        make_clip(self.raw / "2026090300000600_s.mp4", 3)
        make_clip(self.raw / "2026090300001500_s.mp4", 3)
        (self.raw / "._2026090300001500_s.mp4").write_bytes(b"x")

    def tearDown(self):
        shutil.rmtree(self.td)

    def test_probe_dir_skips_dotfiles_and_reads_duration(self):
        clips = sc.probe_dir(self.raw)
        self.assertEqual([c["file"] for c in clips],
                         ["2026090300000300_s.mp4", "2026090300000600_s.mp4", "2026090300001500_s.mp4"])
        self.assertAlmostEqual(clips[0]["dur"], 3.0, delta=0.2)
        self.assertEqual(len(sc.group_sessions(clips)), 2)

    def test_strip_has_one_column_per_second(self):
        from PIL import Image
        sessions = sc.group_sessions(sc.probe_dir(self.raw))
        single = sessions[1]
        p = sc.render_strip(self.raw, single, self.td / "strip.jpg", step=1.0, width=100)
        im = Image.open(p)
        self.assertIn(im.width, {sc.STRIP_LABEL_W + 3 * 100, sc.STRIP_LABEL_W + 4 * 100})
        joined = sessions[0]
        p2 = sc.render_strip(self.raw, joined, self.td / "strip2.jpg", step=1.0, width=100)
        im2 = Image.open(p2)
        self.assertGreater(im2.height, im.height)


if __name__ == "__main__":
    unittest.main(verbosity=2)
