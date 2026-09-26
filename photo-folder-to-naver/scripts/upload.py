#!/usr/bin/env python3
"""폴더 사진을 새 네이버 글쓰기 탭에 파일명 순서대로 올린다. 저장·발행은 하지 않는다.

- 새 탭은 방송(치지직 등)이 없는 크롬 창에 연다(_lib/chrome_window). 기존 글쓰기 탭은
  건드리지 않는다.
- 사진은 에디터 API로 넣는다(_lib/se_doc.append_images). 키보드·클립보드를 안 쓰므로
  업로드 중에 컴퓨터를 써도 된다.
- 순서는 파일명 순이다. organize.py가 붙인 NNN_ 번호가 곧 순서다.

사용:
  upload.py <사진폴더>                 예: .../포켓몬 고풍상점/watermark
  upload.py <사진폴더> --chrome-window 2   창을 직접 지정(사용자가 말하는 번호, 1부터)
"""
import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_lib"))
import chrome_window  # noqa: E402
import se_doc  # noqa: E402

EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--chrome-window", type=int)
    ap.add_argument("--blog-id", default="op5321")
    a = ap.parse_args()

    folder = os.path.abspath(a.folder)
    names = sorted(n for n in os.listdir(folder)
                   if not n.startswith(".") and n.lower().endswith(EXTS))
    if not names:
        sys.exit("사진 없음")
    print(f"사진 {len(names)}장: {names[0]} ... {names[-1]}", flush=True)

    try:
        tab_id, js = chrome_window.open_postwrite_tab(a.blog_id, a.chrome_window)
    except RuntimeError as e:
        sys.exit(f"[ABORT] {e}")

    try:
        final = se_doc.append_images(js, [os.path.join(folder, n) for n in names],
                                     log=lambda m: print(m, flush=True))
    except (RuntimeError, ValueError) as e:
        sys.exit(f"[ABORT] {e}\n  탭 {tab_id}은 그대로 둔다. 이어 올리지 말고 원인을 고친 뒤 새 탭으로 다시 실행")
    print(f"완료: 탭 {tab_id}에 사진 {len(final)}장, 파일명 순서 확인됨 "
          f"({final[0]} ... {final[-1]})", flush=True)


if __name__ == "__main__":
    main()
