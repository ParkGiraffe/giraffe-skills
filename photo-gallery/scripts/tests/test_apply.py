#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply.py 회귀 검사. 실제 T7을 건드리지 않고 임시 트리에서만 돕니다.

    python3 photo-gallery/scripts/tests/test_apply.py
"""
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import apply as applymod  # noqa: E402
import helpers  # noqa: E402


class TestApply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.gallery = self.base / "갤러리"
        self.journal = self.base / "작업기록"
        self.data = helpers.gradient_jpeg(seed=3)
        helpers.make_tree(self.base, {"old/a/IMG_1.jpg": self.data,
                                      "old/b/IMG_2.jpg": helpers.gradient_jpeg(seed=4)})
        self.rows = [
            {"src": "old/a/IMG_1.jpg", "dst": "사진/2026/05/x.jpg",
             "sha256": "s1", "action": "복사"},
            {"src": "old/b/IMG_2.jpg", "dst": "_시스템/중복격리/y.jpg",
             "sha256": "s2", "action": "격리"},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_copies_to_destination(self):
        applymod.run(self.rows, self.base, self.gallery, self.journal)
        self.assertTrue((self.gallery / "사진/2026/05/x.jpg").exists())
        self.assertTrue((self.gallery / "_시스템/중복격리/y.jpg").exists())

    def test_originals_are_not_removed(self):
        applymod.run(self.rows, self.base, self.gallery, self.journal)
        self.assertTrue((self.base / "old/a/IMG_1.jpg").exists())
        self.assertTrue((self.base / "old/b/IMG_2.jpg").exists())

    def test_content_is_identical(self):
        applymod.run(self.rows, self.base, self.gallery, self.journal)
        self.assertEqual(self.data, (self.gallery / "사진/2026/05/x.jpg").read_bytes())

    def test_copy_does_not_carry_metadata(self):
        """메타데이터를 복사하면 exFAT 에서 "._이름" 짝꿍 파일이 생깁니다.

        T7 은 exFAT 이라 확장속성을 담을 자리가 없어서, macOS 가 파일마다
        짝꿍을 만듭니다. 12,693개면 짝꿍도 그만큼이고 윈도우에 꽂으면 다 보입니다.
        shutil.copy2 가 아니라 copy 여야 합니다.
        """
        import inspect, re
        calls = re.findall(r"shutil\.\w+\(", inspect.getsource(applymod.run))
        self.assertEqual(["shutil.copy("], calls,
                         "복사는 shutil.copy 한 곳뿐이어야 합니다")

    def test_journal_records_every_row(self):
        path = applymod.run(self.rows, self.base, self.gallery, self.journal)
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(2, len(rec["항목"]))
        self.assertEqual({"old/a/IMG_1.jpg", "old/b/IMG_2.jpg"},
                         {i["src"] for i in rec["항목"]})

    def test_missing_source_is_recorded_not_fatal(self):
        rows = self.rows + [{"src": "old/none.jpg", "dst": "사진/2026/05/z.jpg",
                             "sha256": "s3", "action": "복사"}]
        path = applymod.run(rows, self.base, self.gallery, self.journal)
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(1, len(rec["실패"]))

    def test_rerun_skips_already_copied(self):
        applymod.run(self.rows, self.base, self.gallery, self.journal)
        path = applymod.run(self.rows, self.base, self.gallery, self.journal)
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(2, rec["건너뜀"])


class TestCrashRecovery(unittest.TestCase):
    """중간에 죽었다 다시 돌렸을 때도 되돌릴 수 있어야 합니다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.gallery = self.base / "갤러리"
        self.journal = self.base / "작업기록"
        helpers.make_tree(self.base, {"old/a.jpg": helpers.gradient_jpeg(seed=1),
                                      "old/b.jpg": helpers.gradient_jpeg(seed=2)})
        self.rows = [
            {"src": "old/a.jpg", "dst": "사진/a.jpg", "sha256": "s1", "action": "복사"},
            {"src": "old/b.jpg", "dst": "사진/b.jpg", "sha256": "s2", "action": "복사"},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_rerun_records_already_copied_files(self):
        """앞선 실행이 남긴 복사본도 이번 기록에 잡혀야 되돌리기가 닿습니다.

        기록에 없으면 undo 가 못 지웁니다. 52GB 짜리 작업이 중간에 죽는 것은
        드문 일이 아닙니다.
        """
        applymod.run(self.rows[:1], self.base, self.gallery, self.journal)
        path = applymod.run(self.rows, self.base, self.gallery, self.journal)
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual({"사진/a.jpg", "사진/b.jpg"},
                         {i["dst"] for i in rec["항목"]})
        self.assertEqual(2, applymod.undo(path, self.gallery))
        self.assertFalse((self.gallery / "사진/a.jpg").exists())
        self.assertFalse((self.gallery / "사진/b.jpg").exists())

    def test_journal_survives_a_crash_midway(self):
        """도중에 죽어도 그때까지 복사한 것이 기록에 남아야 합니다.

        끝에 한 번만 쓰면 기록 파일 자체가 안 생겨서, 이미 디스크에 올라간
        수천 장을 되돌릴 방법이 없습니다.
        """
        def rows_then_crash():
            for i in range(applymod.FLUSH_EVERY):
                yield {"src": "old/a.jpg", "dst": f"사진/{i}.jpg",
                       "sha256": f"s{i}", "action": "복사"}
            raise KeyboardInterrupt("복사 도중 중단")

        with self.assertRaises(KeyboardInterrupt):
            applymod.run(rows_then_crash(), self.base, self.gallery, self.journal)

        written = sorted(self.journal.glob("*.json"))
        self.assertEqual(1, len(written), "중단됐는데 작업기록이 없습니다")
        rec = json.loads(written[0].read_text(encoding="utf-8"))
        self.assertEqual(applymod.FLUSH_EVERY, len(rec["항목"]))

    def test_apply_refuses_to_write_outside_the_gallery(self):
        """나가는 쪽이 아니라 들어오는 쪽에서 막아야 합니다.

        갤러리 밖에 쓰고 나서 undo 가 거부하면, 이미 원본을 덮어쓴 뒤이고
        정상 항목까지 못 되돌립니다. 계획 CSV 는 사람이 고치라고 만든
        문서이므로 이 경로는 가정이 아닙니다.
        """
        precious = self.base / "old/소중한사진.jpg"
        precious.write_bytes(helpers.gradient_jpeg(seed=9))
        before = precious.read_bytes()
        rows = self.rows + [{"src": "old/a.jpg", "dst": "../old/소중한사진.jpg",
                             "sha256": "s9", "action": "복사"}]
        path = applymod.run(rows, self.base, self.gallery, self.journal)
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("갤러리 밖을 가리키는 목적지",
                      [f.get("이유") for f in rec["실패"]])
        self.assertEqual(before, precious.read_bytes(), "원본이 덮어써졌습니다")

    def test_undo_checks_everything_before_deleting_anything(self):
        """중간에 예외를 던지면 앞쪽 수천 개는 이미 지워진 채로 멈춥니다."""
        path = applymod.run(self.rows, self.base, self.gallery, self.journal)
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["항목"].append({"src": "x", "dst": "../탈출.jpg",
                           "sha256": "s9", "action": "복사"})
        path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(RuntimeError):
            applymod.undo(path, self.gallery)
        self.assertTrue((self.gallery / "사진/a.jpg").exists(),
                        "거부하기 전에 이미 지웠습니다")

    def test_undo_refuses_a_journal_pointing_outside(self):
        """작업기록은 손으로 고칠 수 있으므로 갤러리 밖을 가리킬 수 있습니다."""
        path = applymod.run(self.rows, self.base, self.gallery, self.journal)
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["항목"][0]["dst"] = "../old/a.jpg"
        path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(RuntimeError):
            applymod.undo(path, self.gallery)
        self.assertTrue((self.base / "old/a.jpg").exists())


class TestVerifyAndUndo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.gallery = self.base / "갤러리"
        self.journal = self.base / "작업기록"
        helpers.make_tree(self.base, {"old/a.jpg": helpers.gradient_jpeg(seed=9)})
        self.rows = [{"src": "old/a.jpg", "dst": "사진/2026/05/a.jpg",
                      "sha256": "s1", "action": "복사"}]
        self.path = applymod.run(self.rows, self.base, self.gallery, self.journal)

    def tearDown(self):
        self.tmp.cleanup()

    def test_verify_passes_after_apply(self):
        self.assertEqual([], applymod.verify(self.path, self.base, self.gallery))

    def test_verify_catches_corrupted_copy(self):
        (self.gallery / "사진/2026/05/a.jpg").write_bytes(b"corrupted")
        problems = applymod.verify(self.path, self.base, self.gallery)
        self.assertEqual(1, len(problems))

    def test_verify_catches_missing_copy(self):
        (self.gallery / "사진/2026/05/a.jpg").unlink()
        self.assertEqual(1, len(applymod.verify(self.path, self.base, self.gallery)))

    def test_undo_removes_copies_and_keeps_originals(self):
        n = applymod.undo(self.path, self.gallery)
        self.assertEqual(1, n)
        self.assertFalse((self.gallery / "사진/2026/05/a.jpg").exists())
        self.assertTrue((self.base / "old/a.jpg").exists())

    def test_undo_cleans_empty_folders(self):
        applymod.undo(self.path, self.gallery)
        self.assertFalse((self.gallery / "사진/2026/05").exists())


if __name__ == "__main__":
    unittest.main()
