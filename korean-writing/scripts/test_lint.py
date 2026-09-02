#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lint.py 회귀 검사.

    python3 korean-writing/scripts/test_lint.py

픽스처 두 벌과 스킬 자신의 문서를 검사합니다. 규칙을 설명하는 문장이 규칙을 어기는 일이
실제로 일어나므로, 스킬 자신도 검사 대상에 넣습니다.
"""
import pathlib
import re
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))

import lint  # noqa: E402

FIXTURES = HERE / "fixtures"
RULES, EXCEPTIONS = lint.load_rules()


def run(text, heuristic=False):
    return lint.check(text, RULES, EXCEPTIONS, heuristic=heuristic)


class RuleTableTest(unittest.TestCase):
    def test_rules_load(self):
        self.assertGreater(len(RULES), 30, "규칙표를 제대로 읽지 못했습니다")

    def test_every_section_present(self):
        sections = {rule.section for rule in RULES}
        for expected in (1, 2, 3, 4, 5):
            self.assertIn(expected, sections, "§{} 규칙이 없습니다".format(expected))

    def test_rule_ids_unique(self):
        ids = [rule.rid for rule in RULES]
        self.assertEqual(len(ids), len(set(ids)), "규칙 ID가 중복됩니다")

    def test_exceptions_load(self):
        self.assertIn("OpenFGA", EXCEPTIONS)


class ViolationFixtureTest(unittest.TestCase):
    """`violations.md` 의 각 블록이 기대한 절에 걸리는지 봅니다."""

    def test_each_block_is_caught(self):
        text = (FIXTURES / "violations.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        findings = run(text, heuristic=True)
        by_line = {}
        for finding in findings:
            by_line.setdefault(finding.line, []).append(finding.section)

        expectations = []
        for index, line in enumerate(lines):
            marker = re.match(r"^<!--\s*expect:\s*(\d+)\s*-->$", line.strip())
            if marker:
                expectations.append((index + 1, int(marker.group(1))))
        self.assertGreaterEqual(len(expectations), 15, "기대 블록이 너무 적습니다")

        for marker_line, section in expectations:
            block = []
            for offset in range(marker_line + 1, min(marker_line + 4, len(lines) + 1)):
                if not lines[offset - 1].strip():
                    if block:
                        break
                    continue
                block.append(offset)
            hit = [s for line_no in block for s in by_line.get(line_no, [])]
            self.assertIn(
                section, hit,
                "{}행 블록이 §{} 로 걸리지 않았습니다. 실제: {}".format(
                    marker_line, section, hit,
                ),
            )


class CleanFixtureTest(unittest.TestCase):
    def test_no_false_positives(self):
        text = (FIXTURES / "clean.md").read_text(encoding="utf-8")
        findings = run(text)
        self.assertEqual(
            [], [f.as_dict() for f in findings],
            "통과 픽스처에서 오탐이 났습니다",
        )


class MaskingTest(unittest.TestCase):
    def test_code_fence_excluded(self):
        text = "본문입니다.\n\n```\n이것이 핵심입니다.\n```\n"
        self.assertEqual([], run(text))

    def test_inline_code_excluded(self):
        self.assertEqual([], run("값은 `한다.` 형태입니다.\n"))

    def test_quote_excluded(self):
        self.assertEqual([], run("원문은 「핵심입니다」 였습니다.\n"))

    def test_blockquote_excluded(self):
        self.assertEqual([], run("> 이것이 핵심입니다.\n"))

    def test_exempt_comment_excluded(self):
        self.assertEqual([], run("이것이 핵심입니다. <!-- write-exempt -->\n"))

    def test_line_numbers_survive_masking(self):
        text = "첫 줄입니다.\n\n```\n코드\n```\n\n이것이 핵심입니다.\n"
        findings = run(text)
        self.assertEqual(1, len(findings))
        self.assertEqual(7, findings[0].line)


class EndingTest(unittest.TestCase):
    def test_plain_style_reported(self):
        findings = run("권한 데이터가 앱 DB 밖에 있어서 생기는 문제다.\n")
        self.assertTrue(any(f.section == 3 for f in findings))

    def test_polite_style_passes(self):
        self.assertEqual([], run("권한 데이터가 앱 DB 밖에 있어서 생기는 문제입니다.\n"))

    def test_list_item_noun_phrase_passes(self):
        self.assertEqual([], run("- 인증 통과 여부\n- 권한 검사 결과\n"))

    def test_heading_not_checked_for_ending(self):
        self.assertEqual([], run("## 인증 처리 절차\n"))

    def test_sentence_ending_in_english_skipped(self):
        self.assertEqual([], run("반환값은 `SUCCESS`.\n"))

    def test_sentence_ending_in_number_skipped(self):
        self.assertEqual([], run("응답 시간은 120ms.\n"))

    def test_metadata_line_skipped(self):
        self.assertEqual([], run("상태: 승인 대기\n작성일: 2026-09-02\n"))

    def test_metadata_like_sentence_still_checked(self):
        findings = run("참고: 이 값은 매번 다시 계산된다.\n")
        self.assertTrue(any(f.section == 3 for f in findings))

    def test_sentence_across_lines(self):
        text = "이 값은 요청마다 다시 계산되므로 캐시를 두지\n않으면 비용이 크게 늘어난다.\n"
        findings = run(text)
        self.assertTrue(any(f.section == 3 for f in findings))


class HeadingTest(unittest.TestCase):
    def test_question_heading_reported(self):
        findings = run("## 이것이 무엇인가\n")
        self.assertTrue(any(f.rid == "KW-6-HEADING" for f in findings))

    def test_clausal_heading_reported(self):
        findings = run("## 권한을 검사하는 방법\n")
        self.assertTrue(any(f.rid == "KW-6-HEADING" for f in findings))

    def test_noun_phrase_heading_passes(self):
        self.assertEqual([], run("## 처리 방법\n"))
        self.assertEqual([], run("## 확인 사항\n"))
        self.assertEqual([], run("## 검사 제외 목록\n"))

    def test_numbered_heading_stripped(self):
        self.assertEqual([], run("## 1. 확정 금지 문자\n"))


class FixTest(unittest.TestCase):
    def test_fix_replaces_only_confirmed_tier(self):
        text = "검사 레시피를 확정했다. 이것이 핵심입니다.\n"
        fixed, applied = lint.apply_fix(text, RULES, EXCEPTIONS)
        self.assertEqual(1, applied)
        self.assertIn("확정했습니다", fixed)
        self.assertIn("핵심입니다", fixed)

    def test_fix_removes_emoji(self):
        fixed, applied = lint.apply_fix("결과입니다 📊\n", RULES, EXCEPTIONS)
        self.assertEqual(1, applied)
        self.assertNotIn("📊", fixed)

    def test_fix_replaces_em_dash(self):
        fixed, _ = lint.apply_fix("제목 — 부제입니다.\n", RULES, EXCEPTIONS)
        self.assertNotIn("—", fixed)
        self.assertIn(":", fixed)

    def test_fix_is_idempotent(self):
        text = "검사 레시피를 확정했다. 결과입니다 📊\n"
        once, _ = lint.apply_fix(text, RULES, EXCEPTIONS)
        twice, applied = lint.apply_fix(once, RULES, EXCEPTIONS)
        self.assertEqual(once, twice)
        self.assertEqual(0, applied)


class HeuristicTest(unittest.TestCase):
    def test_suspicion_tier_hidden_by_default(self):
        text = "이 스킬은 권한을 다룹니다.\n"
        self.assertEqual([], run(text))

    def test_suspicion_tier_shown_with_flag(self):
        text = "이 스킬은 권한을 다룹니다.\n"
        findings = run(text, heuristic=True)
        self.assertTrue(any(f.tier == "의심" for f in findings))


class ExceptionListTest(unittest.TestCase):
    def test_listed_term_not_reported(self):
        self.assertEqual([], run("표준은 NIST SP 800-162 입니다.\n"))


class SelfCheckTest(unittest.TestCase):
    """스킬 자신의 문서가 자기 규약을 지키는지 봅니다."""

    def test_skill_documents_are_clean(self):
        targets = sorted(SKILL.rglob("*.md"))
        targets = [p for p in targets if FIXTURES not in p.parents]
        self.assertGreaterEqual(len(targets), 5, "검사할 문서가 너무 적습니다")
        problems = []
        for path in targets:
            findings = run(path.read_text(encoding="utf-8"))
            for finding in findings:
                problems.append(
                    "{}:{}  [{}] {}".format(
                        path.relative_to(SKILL), finding.line,
                        finding.tier, finding.found,
                    )
                )
        self.assertEqual([], problems, "\n".join(problems))


if __name__ == "__main__":
    unittest.main(verbosity=2)
