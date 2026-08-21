#!/usr/bin/env python3
"""youtube-music-download 후처리: 앨범커버 정사각 크롭 + 음악 정보(태그) 정리 + 파일명 정리.

yt-dlp 가 임베드해 주는 커버는 유튜브 썸네일 그대로다. 썸네일은 16:9 나 4:3 이라
앨범아트 좌우(또는 위아래)에 검은 띠가 붙어 있는 경우가 대부분이고, 그 상태로 두면
음악 앱의 정사각 아트워크 자리에 띠까지 같이 박힌다. 그래서 검은 띠를 실제 픽셀로
찾아내 잘라내고 정사각으로 다시 임베드한다.

태그도 마찬가지다. yt-dlp 가 넣는 것은 유튜브 영상 제목·업로더·설명이라
"Pokémon Movie10 BGM - Oración" / "PocketMonstersMusic" 같은 값이 들어간다.
곡 정보(제목·아티스트·앨범·발매일·장르)는 사람이 조사해서 넘겨야 하고,
이 스크립트는 그 값을 손실 없이(오디오 재인코딩 없이) 파일에 써 넣는 일을 맡는다.

동작
- 커버: --cover 로 준 이미지, 없으면 파일에 이미 붙어 있는 커버를 꺼내 쓴다.
  검은 띠를 찾아 잘라내고 정사각으로 맞춘 뒤 임베드한다(--no-crop 이면 크롭 생략).
- 오디오: 항상 -c:a copy. 태그를 고치려고 mp3 를 다시 인코딩하면 음질만 깎인다.
- 태그: 넘긴 값만 덮어쓰고 나머지(purl 등 출처)는 그대로 둔다.
- 파일명: --rename 이면 "아티스트 - 제목.mp3" 로 바꾼다. 괄호 안 로마자 표기는
  태그에는 남기고 파일명에서만 뗀다("타루 (Taru)" -> "타루").
- 마지막에 결과를 다시 읽어 태그와 커버 크기를 출력한다. 한글이 깨졌는지
  눈으로 확인하는 절차라 생략하지 않는다.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

# 텍스트 태그: CLI 옵션 이름 -> ffmpeg 메타데이터 키
TEXT_TAGS = [
    ("title", "title"),
    ("artist", "artist"),
    ("album", "album"),
    ("album_artist", "album_artist"),
    ("date", "date"),
    ("genre", "genre"),
    ("track", "track"),
    ("disc", "disc"),
    ("composer", "composer"),
    ("publisher", "publisher"),
    ("comment", "comment"),
    ("description", "description"),
]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def probe(path, stream_args):
    """ffprobe 로 한 줄짜리 값을 뽑는다. 실패하면 빈 문자열."""
    cmd = ["ffprobe", "-v", "error"] + stream_args + [path]
    r = run(cmd)
    return r.stdout.strip()


def video_size(path):
    """이미지/첨부커버의 (width, height). 없으면 None."""
    out = probe(path, [
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
    ])
    m = re.match(r"^(\d+)x(\d+)$", out)
    return (int(m.group(1)), int(m.group(2))) if m else None


def extract_embedded_cover(mp3_path, dest):
    """파일에 붙어 있는 커버를 그대로 꺼낸다(재인코딩 없음). 없으면 False."""
    r = run(["ffmpeg", "-y", "-v", "error", "-i", mp3_path,
             "-an", "-c:v", "copy", dest])
    return r.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest) > 0


def gray_pixels(img_path, w, h):
    """이미지를 8bit 그레이 raw 로 뽑아 bytes 로 반환. Pillow 없이 밝기를 보려는 것."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", img_path,
         "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        capture_output=True,
    )
    data = r.stdout
    if len(data) < w * h:
        return None
    return data[: w * h]


def content_box(img_path, threshold=16, min_bar_ratio=0.02):
    """검은 띠를 뺀 실제 그림 영역 (x0, y0, x1, y1)을 찾는다. x1,y1 은 포함 좌표.

    행/열 단위 평균 밝기가 threshold 이하로 연속되는 구간을 띠로 본다. 평균을 쓰는
    이유: 어두운 앨범아트에도 밝게 튀는 픽셀이 있어서 최댓값 기준으로는 띠와 그림을
    구분하지 못한다.

    핵심 방어가 둘 있다.
    - **대칭성**: 레터박스/필러박스는 양쪽 폭이 같다. 그래서 좌우(상하) 중 좁은 쪽을
      띠 폭으로 채택한다. 한쪽만 어두운 것은 띠가 아니라 그냥 어두운 그림이므로,
      이렇게 하면 밤하늘이나 검은 배경의 앨범아트를 잘라먹지 않는다.
    - **최소 폭**: 가장자리 1~2픽셀이 어두운 것은 JPEG 압축 흔적이지 띠가 아니다.
      변 길이의 min_bar_ratio 미만이면 띠가 없는 것으로 본다. 이 방어가 없으면
      이미 정사각인 커버가 1픽셀씩 깎이면서 의미 없이 재인코딩된다.
    """
    size = video_size(img_path)
    if not size:
        return None
    w, h = size
    px = gray_pixels(img_path, w, h)
    if px is None:
        return None

    row_mean = [sum(px[y * w:(y + 1) * w]) / w for y in range(h)]
    col_mean = [sum(px[y * w + x] for y in range(h)) / h for x in range(w)]

    def dark_run(means):
        """앞쪽/뒤쪽에서 연속으로 어두운 줄 수를 센다."""
        lead = 0
        while lead < len(means) and means[lead] <= threshold:
            lead += 1
        if lead == len(means):
            return 0, 0  # 전부 어두우면 띠 판정을 포기한다
        trail = 0
        while trail < len(means) and means[-1 - trail] <= threshold:
            trail += 1
        return lead, trail

    def bar_width(means):
        lead, trail = dark_run(means)
        bar = min(lead, trail)
        return bar if bar >= max(2, int(len(means) * min_bar_ratio)) else 0

    bx = bar_width(col_mean)
    by = bar_width(row_mean)
    return bx, by, w - 1 - bx, h - 1 - by


def square_crop_rect(img_path):
    """정사각 크롭 영역 (w, h, x, y)을 계산한다. 크롭이 필요 없으면 None."""
    size = video_size(img_path)
    if not size:
        return None
    W, H = size
    box = content_box(img_path)
    if box is None:
        cx0, cy0, cx1, cy1 = 0, 0, W - 1, H - 1
    else:
        cx0, cy0, cx1, cy1 = box
    bw = cx1 - cx0 + 1
    bh = cy1 - cy0 + 1

    side = min(bw, bh)
    side -= side % 2  # 짝수로 맞춰 인코더 경고를 피한다
    x = cx0 + (bw - side) // 2
    y = cy0 + (bh - side) // 2

    if x == 0 and y == 0 and side == W == H:
        return None  # 이미 정사각이고 띠도 없다. 다시 인코딩할 이유가 없다
    return side, side, x, y


def make_cover(src_img, workdir, do_crop):
    """임베드할 커버 파일 경로를 만든다. 크롭이 필요 없으면 원본을 그대로 쓴다."""
    if not do_crop:
        return src_img, None
    rect = square_crop_rect(src_img)
    if rect is None:
        return src_img, None
    w, h, x, y = rect
    dest = os.path.join(workdir, "cover_square.jpg")
    r = run(["ffmpeg", "-y", "-v", "error", "-i", src_img,
             "-vf", f"crop={w}:{h}:{x}:{y}", "-q:v", "2", dest])
    if r.returncode != 0:
        print(f"[tagfix] 커버 크롭 실패, 원본 커버를 그대로 씁니다: {r.stderr.strip()}",
              file=sys.stderr)
        return src_img, None
    return dest, (w, h, x, y)


def filename_part(value):
    """파일명용으로 다듬는다: 끝의 괄호 표기 제거 + 경로 문자 치환."""
    if not value:
        return ""
    s = re.sub(r"\s*[（(][^()（）]*[)）]\s*$", "", value).strip()
    s = s.replace("/", "-").replace(":", "-").strip()
    return re.sub(r"\s+", " ", s)


def build_ffmpeg_cmd(src, cover, args, dest):
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", src]
    if cover:
        cmd += ["-i", cover]
        cmd += ["-map", "0:a", "-map", "1:v",
                "-c:a", "copy", "-c:v", "copy",
                "-disposition:v", "attached_pic",
                "-metadata:s:v", "title=Cover",
                "-metadata:s:v", "comment=Cover (front)"]
    else:
        cmd += ["-map", "0:a", "-c:a", "copy"]

    for opt, key in TEXT_TAGS:
        value = getattr(args, opt)
        if value is not None:
            cmd += ["-metadata", f"{key}={value}"]
    for key in args.clear or []:
        cmd += ["-metadata", f"{key}="]

    cmd += ["-id3v2_version", "3", "-write_id3v1", "1", dest]
    return cmd


def show_result(path):
    out = probe(path, ["-show_format", "-show_streams"])
    tags = []
    cover = None
    for line in out.splitlines():
        if line.startswith("TAG:") and not line.startswith("TAG:encoder="):
            key, _, value = line[4:].partition("=")
            if key in ("title", "comment") and value in ("Cover", "Cover (front)"):
                continue
            tags.append((key, value))
    size = video_size(path)
    if size:
        cover = f"{size[0]}x{size[1]}"
    dur = probe(path, ["-show_entries", "format=duration", "-of", "csv=p=0"])

    print(f"\n[tagfix] 결과: {os.path.basename(path)}")
    if cover:
        print(f"  커버      {cover}")
    if dur:
        try:
            secs = float(dur)
            print(f"  재생시간  {int(secs) // 60}분 {int(secs) % 60}초")
        except ValueError:
            pass
    seen = set()
    for key, value in tags:
        if key in seen:
            continue
        seen.add(key)
        print(f"  {key:9} {value}")
    print("  (한글 고유명사와 조사가 깨지지 않았는지 위 목록을 눈으로 확인하세요.)")


def main():
    ap = argparse.ArgumentParser(
        description="mp3 의 앨범커버를 정사각으로 자르고 음악 정보를 정리한다. 오디오는 재인코딩하지 않는다.",
    )
    ap.add_argument("file", help="대상 오디오 파일 (mp3 등)")
    ap.add_argument("--cover", help="쓸 커버 이미지. 생략하면 파일에 붙어 있는 커버를 사용")
    ap.add_argument("--no-crop", action="store_true", help="정사각 크롭 생략(커버를 그대로 임베드)")
    ap.add_argument("--rename", action="store_true", help='"아티스트 - 제목.mp3" 로 파일명 변경')
    ap.add_argument("--clear", action="append", metavar="KEY",
                    help="비울 태그 키 (여러 번 지정 가능. 예: --clear synopsis)")
    ap.add_argument("--dry-run", action="store_true", help="실행할 명령만 출력하고 파일은 건드리지 않음")
    for opt, _ in TEXT_TAGS:
        ap.add_argument(f"--{opt.replace('_', '-')}", dest=opt, default=None)
    args = ap.parse_args()

    src = os.path.abspath(os.path.expanduser(args.file))
    if not os.path.exists(src):
        ap.error(f"파일이 없습니다: {src}")

    workdir = tempfile.mkdtemp(prefix="tagfix-")
    try:
        cover_src = None
        if args.cover:
            cover_src = os.path.abspath(os.path.expanduser(args.cover))
            if not os.path.exists(cover_src):
                ap.error(f"커버 이미지가 없습니다: {cover_src}")
        else:
            candidate = os.path.join(workdir, "embedded.jpg")
            if extract_embedded_cover(src, candidate):
                cover_src = candidate
            else:
                print("[tagfix] 파일에 붙어 있는 커버가 없습니다. --cover 로 이미지를 주면 넣어 줍니다.")

        cover = None
        if cover_src:
            cover, rect = make_cover(cover_src, workdir, not args.no_crop)
            before = video_size(cover_src)
            after = video_size(cover)
            if rect:
                print(f"[tagfix] 커버 크롭 {before[0]}x{before[1]} -> {after[0]}x{after[1]} "
                      f"(crop={rect[0]}:{rect[1]}:{rect[2]}:{rect[3]})")
            elif before:
                print(f"[tagfix] 커버 {before[0]}x{before[1]} 그대로 사용")

        ext = os.path.splitext(src)[1] or ".mp3"
        dest = os.path.join(workdir, "out" + ext)
        cmd = build_ffmpeg_cmd(src, cover, args, dest)

        if args.dry_run:
            print("[tagfix] --dry-run: 실행할 명령")
            print(" ".join(f"'{c}'" if " " in c else c for c in cmd))
            return 0

        r = run(cmd)
        if r.returncode != 0:
            print(f"[tagfix] ffmpeg 실패:\n{r.stderr}", file=sys.stderr)
            return 1

        final = src
        if args.rename:
            artist = filename_part(args.artist)
            title = filename_part(args.title)
            if artist and title:
                final = os.path.join(os.path.dirname(src), f"{artist} - {title}{ext}")
            else:
                print("[tagfix] --rename 은 --artist 와 --title 이 둘 다 있어야 합니다. 파일명은 그대로 둡니다.")

        shutil.move(dest, final)
        if final != src and os.path.exists(src):
            os.remove(src)
        if final != src:
            print(f"[tagfix] 파일명 변경 -> {os.path.basename(final)}")

        show_result(final)
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
