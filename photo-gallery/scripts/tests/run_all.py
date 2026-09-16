#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""photo-gallery 전체 회귀.

    python3 photo-gallery/scripts/tests/run_all.py
"""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
FILES = sorted(p for p in HERE.glob("test_*.py"))

failed = []
for path in FILES:
    print(f"=== {path.name} ===")
    res = subprocess.run([sys.executable, str(path)])
    if res.returncode != 0:
        failed.append(path.name)

print()
if failed:
    print(f"실패: {', '.join(failed)}")
    raise SystemExit(1)
print(f"{len(FILES)}개 파일 전부 통과")
