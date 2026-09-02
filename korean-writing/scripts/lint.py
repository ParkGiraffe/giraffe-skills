#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lint.py: 박기린의 한국어 글쓰기 규약 검사기.

    python3 lint.py 초안.md
    python3 lint.py 초안.md --fix
    python3 lint.py 초안.md --heuristic
    python3 lint.py 초안.md --json
    cat 초안.md | python3 lint.py -

규칙은 `references/rules.md`의 표에서만 읽습니다. 규칙을 이 파일에 옮겨 적지 않습니다.
표에 담을 수 없는 두 검사(문장 종결의 합쇼체 여부, 헤더의 명사구 여부)만 코드에 있습니다.

보고는 네 갈래입니다.

    고침   확정 위반. --fix 가 자동 치환합니다
    검토   문맥을 보고 사람이 결정합니다
    제목   헤더가 명사구가 아닙니다
    의심   --heuristic 을 줄 때만 보고합니다
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys

for _stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

HERE = pathlib.Path(__file__).resolve().parent
RULES_PATH = HERE.parent / "references" / "rules.md"

EXEMPT = "write-exempt"
TEACHING = "write-teaching"

TIERS = ("고침", "검토", "제목", "의심")
SCOPES = ("prose", "heading", "list", "table", "all")

HANGUL = re.compile(r"[가-힣]")
# 합쇼체 종결. 이 셋 말고는 전부 어체 이탈입니다.
POLITE_END = re.compile(r"(?:니다|니까|십시오)$")
# 문장 끝에서 떼어낼 부호. 닫는 따옴표와 마크다운 강조를 포함합니다.
TRAILING = " \t.!?)]}」』>\"'”’`*_~"

# 헤더 판정. 서술형·의문형·관형절형 제목을 잡습니다.
BAD_HEADING = re.compile(r"(?:다|까)$|[?!]$|(?:은|는|한|인)가$")
QUESTION_OPENER = re.compile(
    r"^(?:무엇|무슨|왜|어떻게|어째서|언제|누가|누구|어디|얼마|어느|어떤|이것이|이게)"
)
CLAUSAL_HEADING = re.compile(
    r"(?:하는|되는|시키는|받는|주는|보장하는|검사하는|처리하는)\s*(?:방법|과정|이유|것)$"
    r"|(?:할|될|해야\s*할)\s*(?:때|것)$"
    r"|[가-힣]하기$"
)

# `상태: 승인 대기` 처럼 짧은 키와 값으로만 된 줄입니다. 문장이 아니므로 어체를 보지 않습니다.
META_LINE = re.compile(r"^[가-힣A-Za-z][가-힣A-Za-z0-9 ]{0,11}:\s*[^.!?]{1,30}$")

FENCE = re.compile(r"^(\s*)(```|~~~)")
HTML_BLOCK = re.compile(r"<(pre|code|script|style)\b[^>]*>.*?</\1\s*>", re.I | re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
QUOTED = re.compile("\"[^\"\n]*\"|'[^'\n]*'|「[^」\n]*」|“[^”\n]*”|『[^』\n]*』")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)


class Rule:
    """`rules.md` 표의 한 행입니다."""

    def __init__(self, section, title, find, repl, tier, kind, scope):
        self.section = section
        self.title = title
        self.find = find
        self.repl = repl
        self.tier = tier
        self.kind = kind
        self.scope = scope
        digest = hashlib.sha1(find.encode("utf-8")).hexdigest()[:8].upper()
        self.rid = "KW-{}-{}".format(section, digest)
        pattern = find if kind == "regex" else re.escape(find)
        self.pattern = re.compile(pattern)

    @property
    def fixable(self):
        return self.tier == "고침" and self.repl not in ("(직접)",)

    def replacement(self):
        return "" if self.repl == "(삭제)" else self.repl


def _clean_cell(cell):
    """표 한 칸을 규칙 값으로 바꿉니다. 백틱을 벗기고 세로줄 escape 를 되돌립니다."""
    cell = cell.strip()
    if cell.startswith("`") and cell.endswith("`") and len(cell) > 1:
        cell = cell[1:-1]
    return cell.replace("\\|", "|")


def _decode_escapes(text):
    r"""표에 적힌 `\uXXXX` 와 `\UXXXXXXXX` 를 실제 문자로 바꿉니다."""
    if "\\u" not in text and "\\U" not in text:
        return text
    return re.sub(
        r"\\U([0-9A-Fa-f]{8})|\\u([0-9A-Fa-f]{4})",
        lambda m: chr(int(m.group(1) or m.group(2), 16)),
        text,
    )


def load_rules(path=RULES_PATH):
    """`rules.md` 에서 규칙 표만 읽습니다. 열 이름이 `찾기` 인 표가 규칙 표입니다."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    rules = []
    exceptions = []
    section = 0
    title = ""
    in_rule_table = False
    in_exception_table = False

    for raw in text.splitlines():
        line = raw.strip()
        heading = re.match(r"^##\s+(?:(\d+)\.\s*)?(.+)$", line)
        if heading:
            section = int(heading.group(1)) if heading.group(1) else 0
            title = heading.group(2).strip()
            in_rule_table = in_exception_table = False
            continue

        if not line.startswith("|"):
            in_rule_table = in_exception_table = False
            continue

        # 정규식 안의 `\|` 는 열 구분자가 아닙니다.
        cells = re.split(r"(?<!\\)\|", line.strip("|"))
        head = _clean_cell(cells[0]) if cells else ""

        if head == "찾기":
            in_rule_table, in_exception_table = True, False
            continue
        if head == "예외":
            in_exception_table, in_rule_table = True, False
            continue
        if set(line.replace("|", "").strip()) <= set("-: "):
            continue

        if in_exception_table:
            term = _clean_cell(cells[0])
            if term:
                exceptions.append(term)
            continue

        if not in_rule_table or len(cells) < 5:
            continue

        find = _decode_escapes(_clean_cell(cells[0]))
        repl = _clean_cell(cells[1])
        tier = _clean_cell(cells[2])
        kind = _clean_cell(cells[3])
        scope = _clean_cell(cells[4])
        if tier not in TIERS or scope not in SCOPES or not find:
            continue
        try:
            rules.append(Rule(section, title, find, repl, tier, kind, scope))
        except re.error as exc:
            print(
                "규칙을 컴파일하지 못했습니다: {} ({})".format(find, exc),
                file=sys.stderr,
            )
    return rules, exceptions


def _blank(match):
    """줄바꿈은 남기고 나머지를 공백으로 바꿉니다. 위치가 어긋나지 않게 합니다."""
    return "".join("\n" if ch == "\n" else " " for ch in match.group(0))


def mask(text):
    """검사에서 제외할 구간을 공백으로 덮습니다. 길이와 줄 번호는 그대로 둡니다."""
    # 예외 표시는 주석을 덮기 전에 찾습니다. 다만 백틱 안에서 표시를 설명하는 자리는
    # 표시가 아니므로, 인라인 코드를 먼저 지운 사본에서 봅니다.
    marker_lines = INLINE_CODE.sub(_blank, text).splitlines(keepends=True)
    masked = FRONTMATTER.sub(_blank, text)
    masked = HTML_BLOCK.sub(_blank, masked)
    masked = HTML_COMMENT.sub(_blank, masked)

    # 펜스 코드 블록
    out = []
    fence = None
    for line in masked.splitlines(keepends=True):
        opener = FENCE.match(line)
        if fence is None and opener:
            fence = opener.group(2)
            out.append(_blank_text(line))
            continue
        if fence is not None:
            out.append(_blank_text(line))
            if opener and opener.group(2) == fence:
                fence = None
            continue
        out.append(line)
    masked = "".join(out)

    masked = INLINE_CODE.sub(_blank, masked)
    masked = QUOTED.sub(_blank, masked)

    # 인용 줄, 예외 주석 줄, 규칙 표 블록
    out = []
    rule_table = False
    teaching = False
    teaching_table_seen = False
    for index, line in enumerate(masked.splitlines(keepends=True)):
        marker = marker_lines[index] if index < len(marker_lines) else line
        stripped = line.strip()

        if TEACHING in marker:
            teaching, teaching_table_seen = True, False
            out.append(_blank_text(line))
            continue

        if teaching:
            # 표시 뒤에 오는 표 한 덩어리까지 덮습니다. 나쁜 예를 보여주는 표입니다.
            if stripped.startswith("|"):
                teaching_table_seen = True
                out.append(_blank_text(line))
                continue
            if teaching_table_seen:
                teaching = False
            elif stripped:
                out.append(_blank_text(line))
                continue

        if stripped.startswith("|"):
            head = re.split(r"(?<!\\)\|", stripped.strip("|"))[0].strip().strip("`")
            if head in ("찾기", "예외"):
                rule_table = True
            if rule_table:
                out.append(_blank_text(line))
                continue
        else:
            rule_table = False

        if stripped.startswith(">") or EXEMPT in marker:
            out.append(_blank_text(line))
            continue
        out.append(line)
    return "".join(out)


def _blank_text(line):
    return "".join("\n" if ch == "\n" else " " for ch in line)


def line_starts(text):
    starts = [0]
    for match in re.finditer(r"\n", text):
        starts.append(match.end())
    return starts


def locate(starts, offset):
    low, high = 0, len(starts) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if starts[mid] <= offset:
            low = mid
        else:
            high = mid - 1
    return low + 1, offset - starts[low] + 1


def classify(line):
    """줄의 검사 범위를 정합니다."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return "heading"
    if stripped.startswith("|"):
        return "table"
    if re.match(r"^(?:[-*+]\s|\d+[.)]\s)", stripped):
        return "list"
    return "prose"


class Finding:
    def __init__(self, line, col, tier, found, suggest, section, title, rid):
        self.line = line
        self.col = col
        self.tier = tier
        self.found = found
        self.suggest = suggest
        self.section = section
        self.title = title
        self.rid = rid

    def as_dict(self):
        return {
            "line": self.line,
            "column": self.col,
            "tier": self.tier,
            "found": self.found,
            "suggest": self.suggest,
            "section": self.section,
            "section_title": self.title,
            "rule": self.rid,
        }


def _exception_spans(text, exceptions):
    spans = []
    for term in exceptions:
        for match in re.finditer(re.escape(term), text):
            spans.append((match.start(), match.end()))
    return spans


def _inside(spans, start, end):
    return any(s <= start and end <= e for s, e in spans)


def check(text, rules, exceptions, heuristic=False):
    """규칙표 검사와 어체·제목 검사를 함께 돌립니다."""
    masked = mask(text)
    starts = line_starts(text)
    lines = text.splitlines()
    scopes = [classify(line) for line in lines]
    skip = _exception_spans(text, exceptions)
    findings = []
    matched_spans = []

    for rule in rules:
        if rule.tier == "의심" and not heuristic:
            continue
        for match in rule.pattern.finditer(masked):
            line_no, col = locate(starts, match.start())
            scope = scopes[line_no - 1] if line_no - 1 < len(scopes) else "prose"
            if rule.scope != "all" and rule.scope != scope:
                continue
            if _inside(skip, match.start(), match.end()):
                continue
            found = text[match.start():match.end()]
            findings.append(
                Finding(
                    line_no, col, rule.tier, found, rule.repl,
                    rule.section, rule.title, rule.rid,
                )
            )
            matched_spans.append((match.start(), match.end()))

    findings.extend(
        _check_endings(text, masked, starts, lines, scopes, matched_spans, heuristic)
    )
    findings.extend(_check_headings(text, masked, starts, lines))
    findings.sort(key=lambda f: (f.line, f.col))
    return findings


def _prose_blocks(masked, lines, scopes, starts):
    """연속된 산문 줄을 한 덩어리로 묶습니다. 문장이 줄을 넘어가기 때문입니다."""
    blocks = []
    current = None
    masked_lines = masked.splitlines()
    for index, line in enumerate(lines):
        masked_line = masked_lines[index] if index < len(masked_lines) else ""
        is_prose = (
            line.strip()
            and scopes[index] == "prose"
            and masked_line.strip()
            and not META_LINE.match(line.strip())
            and not IMAGE_LINE.match(line.strip())
        )
        if is_prose:
            if current is None:
                current = [starts[index], starts[index] + len(line)]
            else:
                current[1] = starts[index] + len(line)
        elif current is not None:
            blocks.append(tuple(current))
            current = None
    if current is not None:
        blocks.append(tuple(current))
    return blocks


IMAGE_LINE = re.compile(r"^!\[|^\s*<img\b|^\[영상")


def _split_by_image(lines, index):
    """다음 비어 있지 않은 줄이 사진인지 봅니다.

    블로그 캡션은 한 문장을 사진 사이에 쪼개 놓는 경우가 있습니다.
    `사막에 사는 겔드족은 풍요로운 대지를 찾아` 다음에 사진이 오고
    `몇 번이고 침범했습니다` 로 이어지는 형태입니다. 이때 앞 조각은
    문장이 끊긴 것이 아니라 이어지는 중이므로 어체를 판정하지 않습니다.
    """
    for line in lines[index + 1:]:
        if not line.strip():
            continue
        return bool(IMAGE_LINE.match(line.strip()))
    return False


def _check_endings(text, masked, starts, lines, scopes, matched_spans, heuristic=False):
    """문장 종결이 합쇼체인지 봅니다. 규칙표가 잡은 자리는 건너뜁니다."""
    findings = []
    for begin, end in _prose_blocks(masked, lines, scopes, starts):
        chunk = masked[begin:end]
        origin = text[begin:end]
        for match in re.finditer(r"[^.!?\n]*[.!?]|[^.!?\n]+$", chunk):
            sentence = match.group(0)
            if not HANGUL.search(sentence):
                continue
            tail = sentence.rstrip(TRAILING)
            if not tail or not HANGUL.match(tail[-1]):
                continue
            if POLITE_END.search(tail):
                continue
            # 문장 끝이 인용이나 코드로 덮인 자리였다면 종결어미를 판정할 수 없습니다.
            cut = match.start() + len(tail)
            if origin[cut:match.end()] != chunk[cut:match.end()]:
                continue
            abs_end = begin + cut
            if any(s < abs_end <= e + 1 for s, e in matched_spans):
                continue
            line_no, col = locate(starts, abs_end - 1)
            # 종결부호 없이 끝났고 바로 뒤가 사진이면 문장이 사진을 사이에 두고
            # 이어지는 중입니다. 블로그 캡션에서 쓰는 구성이라 기본 검사에서는 빼고,
            # 읽는 흐름이 끊긴다는 판단도 가능하므로 --heuristic 에서만 보고합니다.
            if sentence[-1] not in ".!?" and _split_by_image(lines, line_no - 1):
                if not heuristic:
                    continue
                findings.append(
                    Finding(
                        line_no, col, "의심", tail[-6:], "(사진 사이로 문장이 끊깁니다)",
                        4, "문장 구조", "KW-4-SPLITCAPTION",
                    )
                )
                continue
            findings.append(
                Finding(
                    line_no, col, "검토", tail[-6:], "(합쇼체로)",
                    3, "어체", "KW-3-ENDING",
                )
            )
    return findings


def _check_headings(text, masked, starts, lines):
    """헤더가 명사구인지 봅니다."""
    findings = []
    masked_lines = masked.splitlines()
    for index, line in enumerate(lines):
        if classify(line) != "heading":
            continue
        if index < len(masked_lines) and not masked_lines[index].strip():
            continue
        title = re.sub(r"^#+\s*", "", line).strip()
        title = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", title)
        if not title or not HANGUL.search(title):
            continue
        bare = title.rstrip(TRAILING + ":")
        if not (
            BAD_HEADING.search(bare)
            or QUESTION_OPENER.match(bare)
            or CLAUSAL_HEADING.search(bare)
        ):
            continue
        line_no, col = locate(starts, starts[index])
        findings.append(
            Finding(line_no, col, "제목", title, "(명사구로)", 6, "제목", "KW-6-HEADING")
        )
    return findings


def apply_fix(text, rules, exceptions):
    """`고침` 갈래만 치환합니다. 나머지는 손대지 않습니다."""
    masked = mask(text)
    starts = line_starts(text)
    scopes = [classify(line) for line in text.splitlines()]
    skip = _exception_spans(text, exceptions)
    edits = []
    for rule in rules:
        if not rule.fixable:
            continue
        for match in rule.pattern.finditer(masked):
            line_no, _ = locate(starts, match.start())
            scope = scopes[line_no - 1] if line_no - 1 < len(scopes) else "prose"
            if rule.scope != "all" and rule.scope != scope:
                continue
            if _inside(skip, match.start(), match.end()):
                continue
            edits.append((match.start(), match.end(), rule.replacement()))

    edits.sort(key=lambda e: e[0], reverse=True)
    out = text
    applied = 0
    last_start = len(text) + 1
    for start, end, repl in edits:
        if end > last_start:  # 겹치는 치환은 건너뜁니다
            continue
        out = out[:start] + repl + out[end:]
        last_start = start
        applied += 1
    return out, applied


def render(path, findings):
    lines = []
    for finding in findings:
        lines.append(
            "{}:{}:{}  [{}] {} → {}  (§{} {} · {})".format(
                path, finding.line, finding.col, finding.tier,
                finding.found, finding.suggest,
                finding.section, finding.title, finding.rid,
            )
        )
    return "\n".join(lines)


def summarize(findings):
    by_tier = {}
    by_rule = {}
    for finding in findings:
        by_tier[finding.tier] = by_tier.get(finding.tier, 0) + 1
        by_rule[finding.rid] = by_rule.get(finding.rid, 0) + 1
    return {"total": len(findings), "by_tier": by_tier, "by_rule": by_rule}


def main(argv=None):
    parser = argparse.ArgumentParser(description="한국어 글쓰기 규약 검사기")
    parser.add_argument("paths", nargs="+", help="검사할 파일. `-` 는 표준 입력")
    parser.add_argument("--fix", action="store_true", help="고침 갈래를 자동 치환")
    parser.add_argument("--heuristic", action="store_true", help="의심 갈래도 보고")
    parser.add_argument("--json", action="store_true", help="JSON 으로 출력")
    parser.add_argument("--rules", default=str(RULES_PATH), help="규칙 파일 경로")
    args = parser.parse_args(argv)

    rules, exceptions = load_rules(args.rules)
    if not rules:
        print("규칙을 하나도 읽지 못했습니다: {}".format(args.rules), file=sys.stderr)
        return 2

    total = []
    payload = []
    for raw_path in args.paths:
        if raw_path == "-":
            text = sys.stdin.read()
            label = "<stdin>"
            path = None
        else:
            path = pathlib.Path(raw_path)
            text = path.read_text(encoding="utf-8")
            label = str(path)

        if args.fix and path is not None:
            text, applied = apply_fix(text, rules, exceptions)
            path.write_text(text, encoding="utf-8")
            if not args.json and applied:
                print("{}: 고침 {}건을 반영했습니다.".format(label, applied))

        findings = check(text, rules, exceptions, heuristic=args.heuristic)
        total.extend(findings)
        if args.json:
            payload.append(
                {"file": label, "findings": [f.as_dict() for f in findings]}
            )
        elif findings:
            print(render(label, findings))

    if args.json:
        print(json.dumps(
            {"files": payload, "summary": summarize(total)},
            ensure_ascii=False, indent=2,
        ))
    elif not total:
        print("문체 규약 위반 없음")
    else:
        summary = summarize(total)
        order = [t for t in TIERS if t in summary["by_tier"]]
        print("")
        print(" · ".join(
            "{} {}".format(tier, summary["by_tier"][tier]) for tier in order
        ))
        print("인용이 꼭 필요하면 백틱이나 「」 로 감싸거나 "
              "줄 끝에 <!-- write-exempt --> 를 답니다.")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
