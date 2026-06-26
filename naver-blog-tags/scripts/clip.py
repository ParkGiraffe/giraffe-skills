#!/usr/bin/env python3
"""추천 태그를 공백 구분 한 줄로 합쳐 macOS 클립보드에 저장한다.

주의: 이 스크립트는 사용자가 "복사할까요?"에 동의한 뒤에만 호출한다(자동 저장 금지).

사용:
    python3 clip.py "#태그1" "#태그2" ...          # 인자로
    echo "#태그1 #태그2 ..." | python3 clip.py       # 표준입력으로

동작: 태그를 한 줄(공백 구분)로 정규화 → pbcopy → pbpaste 로 검증 출력.
"""
import sys, subprocess


def normalize(text):
    # 줄바꿈·중복 공백을 단일 공백으로, 양끝 정리
    return " ".join(text.split())


def main(argv):
    if argv:
        line = normalize(" ".join(argv))
    else:
        line = normalize(sys.stdin.read())
    if not line:
        print("복사할 태그가 없습니다.", file=sys.stderr)
        return 1
    p = subprocess.run(["pbcopy"], input=line, text=True)
    if p.returncode != 0:
        print("pbcopy 실패 (macOS 전용).", file=sys.stderr)
        return p.returncode
    pasted = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
    count = sum(1 for t in pasted.split() if t.startswith("#"))
    print("클립보드 저장 완료 (검증):")
    print(pasted)
    print(f"\n태그 수: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
