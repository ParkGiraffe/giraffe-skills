#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply.py 회귀 검사. 실제 T7을 건드리지 않고 임시 트리에서만 돕니다.

    python3 photo-gallery/scripts/tests/test_apply.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import unittest.mock  # noqa: E402

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

        소스 문자열을 보지 않고 결과를 봅니다. copy2 는 원본 mtime 을 그대로
        가져오고 copy 는 안 가져옵니다. 원본 시각을 2001년으로 밀어 두면
        타임스탬프 해상도와 무관하게 갈립니다.
        """
        old_time = 978307200.0  # 2001-01-01
        os.utime(self.base / "old/a/IMG_1.jpg", (old_time, old_time))
        applymod.run(self.rows, self.base, self.gallery, self.journal)
        copied = (self.gallery / "사진/2026/05/x.jpg").stat().st_mtime
        self.assertNotAlmostEqual(old_time, copied, delta=1,
                                  msg="원본 메타데이터가 복사본에 따라왔습니다")

    @unittest.skipUnless(sys.platform == "darwin" and shutil.which("xattr"),
                         "xattr 명령 없음")
    def test_copy_does_not_carry_extended_attributes(self):
        """짝꿍 파일을 만드는 진짜 원인은 확장속성입니다.

        복사본에 확장속성이 하나도 없는지를 보면 안 됩니다. macOS 가 파일을 쓴
        프로세스를 기록하려고 com.apple.provenance 를 제 손으로 붙이기 때문에,
        copy 를 써도 그것 하나는 항상 있습니다. 원본의 것이 따라왔는지만 봅니다.
        """
        src = self.base / "old/a/IMG_1.jpg"
        subprocess.run(["xattr", "-w", "com.apple.metadata:시험", "값", str(src)],
                       check=True)
        applymod.run(self.rows, self.base, self.gallery, self.journal)
        out = subprocess.run(["xattr", str(self.gallery / "사진/2026/05/x.jpg")],
                             capture_output=True, text=True)
        self.assertNotIn("com.apple.metadata:시험", out.stdout,
                         "원본 확장속성이 복사본에 따라왔습니다")

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

    def test_two_runs_in_the_same_second_keep_both_journals(self):
        """이름이 초 단위라 덮어쓰면 앞 실행을 되돌릴 방법이 사라집니다."""
        first = applymod.run(self.rows[:1], self.base, self.gallery, self.journal)
        second = applymod.run(self.rows, self.base, self.gallery, self.journal)
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists(), "앞 실행의 작업기록이 덮어써졌습니다")
        rec = json.loads(first.read_text(encoding="utf-8"))
        self.assertEqual(["사진/2026/05/x.jpg"], [i["dst"] for i in rec["항목"]])

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
        self.assertEqual(2, applymod.undo(path, self.gallery)[0])
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


class TestPartialFile(unittest.TestCase):
    """복사가 끊기면 조각 파일이 남습니다. 남기면 안 됩니다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.gallery = self.base / "갤러리"
        self.journal = self.base / "작업기록"
        self.data = helpers.gradient_jpeg(seed=7)
        helpers.make_tree(self.base, {"old/a.jpg": self.data})
        self.rows = [{"src": "old/a.jpg", "dst": "사진/a.jpg",
                      "sha256": "s1", "action": "복사"}]

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _half_written(error):
        """반쯤 쓰다가 죽는 복사를 흉내냅니다."""
        def fake(src, dst):
            pathlib.Path(dst).write_bytes("절반만".encode("utf-8"))
            raise error
        return fake

    def test_failed_copy_leaves_no_fragment(self):
        with unittest.mock.patch.object(
                applymod.shutil, "copy", self._half_written(OSError("디스크 꽉 참"))):
            applymod.run(self.rows, self.base, self.gallery, self.journal)
        self.assertFalse((self.gallery / "사진/a.jpg").exists(),
                         "복사가 실패했는데 조각 파일이 남았습니다")

    def test_rerun_after_a_failed_copy_copies_the_whole_file(self):
        """조각이 남으면 다음 실행이 완성본으로 착각해 영영 건너뜁니다."""
        with unittest.mock.patch.object(
                applymod.shutil, "copy", self._half_written(OSError("디스크 꽉 참"))):
            applymod.run(self.rows, self.base, self.gallery, self.journal)
        path = applymod.run(self.rows, self.base, self.gallery, self.journal)
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(0, rec["건너뜀"])
        self.assertEqual(self.data, (self.gallery / "사진/a.jpg").read_bytes())

    def test_interrupt_during_copy_leaves_no_fragment(self):
        """Ctrl+C 는 OSError 가 아닙니다. 그래도 조각은 치워야 합니다."""
        with unittest.mock.patch.object(
                applymod.shutil, "copy",
                self._half_written(KeyboardInterrupt("복사 도중 중단"))):
            with self.assertRaises(KeyboardInterrupt):
                applymod.run(self.rows, self.base, self.gallery, self.journal)
        self.assertFalse((self.gallery / "사진/a.jpg").exists(),
                         "중단됐는데 조각 파일이 남았습니다")

    def test_interrupt_during_copy_still_writes_the_journal(self):
        rows = [{"src": "old/a.jpg", "dst": "사진/먼저.jpg",
                 "sha256": "s0", "action": "복사"}] + self.rows
        real = applymod.shutil.copy
        calls = []

        def fake(src, dst):
            calls.append(dst)
            if len(calls) == 1:
                return real(src, dst)
            pathlib.Path(dst).write_bytes("절반만".encode("utf-8"))
            raise KeyboardInterrupt("복사 도중 중단")

        with unittest.mock.patch.object(applymod.shutil, "copy", fake):
            with self.assertRaises(KeyboardInterrupt):
                applymod.run(rows, self.base, self.gallery, self.journal)
        written = sorted(self.journal.glob("*.json"))
        self.assertEqual(1, len(written), "중단됐는데 작업기록이 없습니다")
        rec = json.loads(written[0].read_text(encoding="utf-8"))
        self.assertEqual(["사진/먼저.jpg"], [i["dst"] for i in rec["항목"]])


class TestUndoLeavesForeignFiles(unittest.TestCase):
    """그 자리에 이미 있던 파일이 우리 복사본이라는 보장은 없습니다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.gallery = self.base / "갤러리"
        self.journal = self.base / "작업기록"
        helpers.make_tree(self.base, {"old/a.jpg": helpers.gradient_jpeg(seed=1)})
        self.rows = [{"src": "old/a.jpg", "dst": "사진/a.jpg",
                      "sha256": "s1", "action": "복사"}]

    def tearDown(self):
        self.tmp.cleanup()

    def test_undo_keeps_a_file_the_user_put_there(self):
        mine = helpers.gradient_jpeg(seed=42)
        target = self.gallery / "사진/a.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(mine)

        path = applymod.run(self.rows, self.base, self.gallery, self.journal)
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(1, rec["건너뜀"])

        removed, kept = applymod.undo(path, self.gallery)
        self.assertEqual(0, removed)
        self.assertEqual(["사진/a.jpg"], kept)
        self.assertEqual(mine, target.read_bytes(),
                         "사용자가 넣어 둔 사진을 지웠습니다")

    def test_undo_removes_a_copy_an_earlier_run_made(self):
        """앞선 실행이 남긴 복사본은 내용이 같으므로 지워야 합니다."""
        applymod.run(self.rows, self.base, self.gallery, self.journal)
        path = applymod.run(self.rows, self.base, self.gallery, self.journal)
        removed, kept = applymod.undo(path, self.gallery)
        self.assertEqual(1, removed)
        self.assertEqual([], kept)
        self.assertFalse((self.gallery / "사진/a.jpg").exists())


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
        n, kept = applymod.undo(self.path, self.gallery)
        self.assertEqual(1, n)
        self.assertEqual([], kept)
        self.assertFalse((self.gallery / "사진/2026/05/a.jpg").exists())
        self.assertTrue((self.base / "old/a.jpg").exists())

    def test_undo_cleans_empty_folders(self):
        applymod.undo(self.path, self.gallery)
        self.assertFalse((self.gallery / "사진/2026/05").exists())


if __name__ == "__main__":
    unittest.main()
