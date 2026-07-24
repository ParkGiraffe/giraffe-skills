#!/usr/bin/env python3
"""youtube-music-download: 유튜브 URL(들)을 오디오(mp3)로 ~/Downloads에 저장.

핵심 동작
- 재생목록/라디오 파라미터(&list=, start_radio 등)가 붙은 URL이라도
  --no-playlist 로 그 URL이 가리키는 개별 영상 한 개만 받는다.
- 최고 음질 오디오만 추출해 mp3 로 변환하고, 썸네일과 메타데이터를 파일에 임베드한다.
- 이미 같은 제목의 파일이 있으면 --no-overwrites 로 건너뛴다(재실행이 안전).

403 자동 대응 (이 스킬의 존재 이유 중 하나)
- 유튜브는 주기적으로 스트리밍 방식(SABR 등)을 바꾼다. 설치된 yt-dlp 가 그 변경보다
  오래되면 모든 다운로드가 "HTTP Error 403: Forbidden" 으로 실패한다.
- 그래서 403 이 감지되면 yt-dlp 를 최신 pre-release 로 한 번 자동 업데이트하고
  같은 명령을 재시도한다(이미 받은 파일은 --no-overwrites 로 건너뜀).
"""
import argparse
import os
import subprocess
import sys


def build_cmd(urls, outdir, batch_file, audio_format):
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-x",
        "--audio-format", audio_format,
        "--audio-quality", "0",
        "--embed-thumbnail",
        "--embed-metadata",
        "--no-overwrites",
        "-o", os.path.join(outdir, "%(title)s.%(ext)s"),
    ]
    if batch_file:
        cmd += ["-a", batch_file]
    cmd += urls
    return cmd


def run_streaming(cmd):
    """yt-dlp 를 실행하며 출력을 실시간으로 흘려보내고, 동시에 버퍼에 모아 반환한다."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    captured = []
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        captured.append(line)
    proc.wait()
    return proc.returncode, "".join(captured)


def looks_like_403(output):
    return "HTTP Error 403" in output or "403: Forbidden" in output


def update_ytdlp():
    print("\n[youtube-music-download] 403 감지 → yt-dlp 를 최신 pre-release 로 업데이트합니다...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", "--pre", "yt-dlp[default]"],
        check=False,
    )


def main():
    ap = argparse.ArgumentParser(
        description="유튜브 URL(들)을 mp3(기본)로 ~/Downloads 에 저장. 재생목록/라디오 URL은 개별 영상만 받는다.",
    )
    ap.add_argument("urls", nargs="*", help="유튜브 영상 URL (여러 개 나열 가능)")
    ap.add_argument("-a", "--batch-file", help="URL을 한 줄에 하나씩 적은 텍스트 파일")
    ap.add_argument("--out", default=os.path.expanduser("~/Downloads"),
                    help="저장 폴더 (기본 ~/Downloads)")
    ap.add_argument("--format", dest="audio_format", default="mp3",
                    help="오디오 포맷 (mp3 기본. m4a 등 yt-dlp 지원 포맷)")
    args = ap.parse_args()

    if not args.urls and not args.batch_file:
        ap.error("URL을 하나 이상 주거나 --batch-file 을 지정하세요.")

    os.makedirs(args.out, exist_ok=True)
    cmd = build_cmd(args.urls, args.out, args.batch_file, args.audio_format)

    rc, output = run_streaming(cmd)

    if rc != 0 and looks_like_403(output):
        update_ytdlp()
        print("[youtube-music-download] 업데이트 완료 → 같은 명령으로 재시도합니다.\n")
        rc, output = run_streaming(cmd)

    if rc == 0:
        print("\n[youtube-music-download] 완료.")
    else:
        print("\n[youtube-music-download] 일부 항목이 실패했습니다. 위 로그의 ERROR 줄을 확인하세요.")
        if looks_like_403(output):
            print("403 이 업데이트 후에도 반복되면 쿠키(--cookies-from-browser)나 "
                  "player_client 우회가 필요할 수 있습니다.")
    sys.exit(rc)


if __name__ == "__main__":
    main()
