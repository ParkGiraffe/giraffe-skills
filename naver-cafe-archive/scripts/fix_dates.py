#!/usr/bin/env python3
"""완전본문 글의 writeDate가 epoch ms(int)로 들어간 것을 사람이 읽는 KST 문자열로 정리.

index.json + posts/**/*.md 프론트매터를 in-place 수정. Chrome 불필요(캐시만 사용).
"""
import json
import pathlib
import re
import sys
import datetime


def fmt(v):
    """epoch ms(int 또는 숫자문자열) → 'YYYY.MM.DD. HH:MM' (KST). 그 외는 그대로."""
    s = str(v)
    if re.fullmatch(r"\d{12,13}", s):
        ms = int(s)
        dt = datetime.datetime.utcfromtimestamp(ms / 1000) + datetime.timedelta(hours=9)
        return dt.strftime("%Y.%m.%d. %H:%M")
    return v


def main():
    corpus = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                          else "./.claude/cafe-corpus").resolve()
    idx_path = corpus / "index.json"
    idx = json.loads(idx_path.read_text())
    fixed = 0
    for r in idx:
        new = fmt(r.get("writeDate", ""))
        if new != r.get("writeDate"):
            r["writeDate"] = new
            md = corpus / r.get("md", "")
            if md.exists():
                txt = md.read_text(encoding="utf-8")
                txt2 = re.sub(r'(?m)^writeDate:.*$', f'writeDate: "{new}"', txt, count=1)
                if txt2 != txt:
                    md.write_text(txt2, encoding="utf-8")
            fixed += 1
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2))
    print(f"[fix_dates] {fixed} records normalized", file=sys.stderr)


if __name__ == "__main__":
    main()
