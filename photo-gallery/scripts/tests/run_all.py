#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""photo-gallery 전체 회귀.

    python3 photo-gallery/scripts/tests/run_all.py
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
FILES = sorted(p for p in HERE.glob("test_*.py"))

# unittest 는 "OK (skipped=5)" 를 stderr 마지막 줄에 찍습니다.
SKIPPED = re.compile(r"skipped=(\d+)")

failed = []
skipped = {}
for path in FILES:
    # flush 가 없으면 파이썬의 print 버퍼가 자식 프로세스의 출력보다 늦게
    # 비워져서, 제목이 전부 맨 끝에 몰려 찍힙니다. 어느 파일이 터졌는지
    # 화면으로 알 수 없게 됩니다.
    print(f"=== {path.name} ===", flush=True)
    res = subprocess.run([sys.executable, str(path)], stderr=subprocess.PIPE, text=True)
    sys.stderr.write(res.stderr)
    sys.stderr.flush()
    if res.returncode != 0:
        failed.append(path.name)
    m = SKIPPED.search(res.stderr)
    if m and int(m.group(1)):
        skipped[path.name] = int(m.group(1))

print()

# 건너뛴 검사를 세어 함께 찍습니다. 종료코드만 보면 exiftool 이 없는 기계에서
# 키워드 쓰기 검사가 조용히 빠진 채로 "전부 통과" 가 찍힙니다. 하필 이
# 프로젝트에서 사용자 사진 파일을 실제로 고치는 유일한 경로입니다.
#
# 실패가 있을 때도 먼저 찍습니다. 실패 때문에 안 보이면, 고치고 다시 돌릴
# 때까지 건너뛴 것이 있다는 사실 자체를 모릅니다.
if skipped:
    total = sum(skipped.values())
    print(f"건너뛴 검사 {total}개입니다. 이유는 위 출력에 적혀 있습니다.")
    for name, n in sorted(skipped.items()):
        print(f"  {name}: {n}개")
    print("exiftool 이 없으면 키워드 쓰기 검사가 통째로 빠집니다.")

if failed:
    print(f"실패: {', '.join(failed)}")
    raise SystemExit(1)
if skipped:
    print(f"{len(FILES)}개 파일 통과. 다만 위의 검사는 안 돌았습니다.")
else:
    print(f"{len(FILES)}개 파일 전부 통과")
