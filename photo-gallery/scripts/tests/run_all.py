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
    # flush 가 없으면 파이썬의 print 버퍼가 자식 프로세스의 출력보다 늦게
    # 비워져서, 제목이 전부 맨 끝에 몰려 찍힙니다. 어느 파일이 터졌는지
    # 화면으로 알 수 없게 됩니다.
    print(f"=== {path.name} ===", flush=True)
    res = subprocess.run([sys.executable, str(path)])
    if res.returncode != 0:
        failed.append(path.name)

print()
if failed:
    print(f"실패: {', '.join(failed)}")
    raise SystemExit(1)
print(f"{len(FILES)}개 파일 전부 통과")
