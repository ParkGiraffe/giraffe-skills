#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""switch_clips.py: 스위치 캡처 클립을 촬영 건으로 묶고, 프레임 띠를 뽑고, 최종 영상을 만든다.

    switch_clips.py scan   <원본 폴더> --out <작업 폴더> [--gap 3.0]
    switch_clips.py strips <작업 폴더> [--session S51 --session S60] [--step 1.0]
    switch_clips.py render <작업 폴더> <videos.json> --out <출력 폴더> [--episode N]

스위치는 저장 버튼을 누른 시점까지의 최대 30초를 파일명 시각(저장 시각)으로 남긴다.
이어서 누르면 직전 저장 이후 구간만 담기므로, 앞 클립 종료와 다음 클립 시작의 틈이
gap초 이내면 같은 촬영으로 본다. 같은 촬영의 클립은 재인코딩 없이 이어 붙일 수 있다.
2026-09-03 젤다무쌍 봉인전기 클립 103개로 검증했다. 병합본은 원본과 비트레이트가 같았다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import tempfile

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
STAMP_RE = re.compile(r"(\d{14})")
VIDEO_EXTS = {".mp4", ".mov"}


def parse_stamp(name: str) -> dt.datetime:
    """파일명의 첫 14자리 숫자를 저장 시각으로 읽는다."""
    m = STAMP_RE.search(name)
    if not m:
        raise ValueError(f"파일명에 14자리 시각이 없습니다: {name}")
    return dt.datetime.strptime(m.group(1), "%Y%m%d%H%M%S")


def probe_duration(path: pathlib.Path) -> float:
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def list_clips(folder: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in folder.iterdir()
                  if p.suffix.lower() in VIDEO_EXTS and not p.name.startswith("."))


def probe_dir(folder: pathlib.Path) -> list[dict]:
    clips = []
    for p in list_clips(folder):
        clips.append({"file": p.name,
                      "end": parse_stamp(p.name).isoformat(),
                      "dur": round(probe_duration(p), 3),
                      "mb": round(p.stat().st_size / 1048576, 1)})
    return clips


def group_sessions(clips: list[dict], gap: float = 3.0) -> list[dict]:
    """클립을 저장 시각 순으로 늘어놓고 틈이 gap초 이내인 것을 한 촬영으로 묶는다."""
    ordered = sorted(clips, key=lambda c: c["end"])
    groups: list[list[dict]] = []
    for c in ordered:
        end = dt.datetime.fromisoformat(c["end"])
        start = end - dt.timedelta(seconds=c["dur"])
        if groups:
            prev_end = dt.datetime.fromisoformat(groups[-1][-1]["end"])
            if (start - prev_end).total_seconds() <= gap:
                groups[-1].append(c)
                continue
        groups.append([c])
    sessions = []
    for i, g in enumerate(groups, 1):
        first_end = dt.datetime.fromisoformat(g[0]["end"])
        start = first_end - dt.timedelta(seconds=g[0]["dur"])
        sessions.append({
            "id": f"S{i:02d}",
            "files": [c["file"] for c in g],
            "durs": [c["dur"] for c in g],
            "start": start.replace(microsecond=0).isoformat(),
            "end": g[-1]["end"],
            "total": round(sum(c["dur"] for c in g), 3),
        })
    return sessions


def read_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_scan(args) -> None:
    raw = pathlib.Path(args.raw_dir).expanduser().resolve()
    out = pathlib.Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    clips = probe_dir(raw)
    sessions = group_sessions(clips, args.gap)
    write_json(out / "sessions.json",
               {"raw_dir": str(raw), "gap": args.gap, "clips": clips, "sessions": sessions})
    for s in sessions:
        print(f"{s['id']} {s['start'][5:19]} 클립 {len(s['files']):2d} {s['total']:7.1f}s")
    print(f"클립 {len(clips)}개 -> 촬영 {len(sessions)}건 -> {out / 'sessions.json'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="원본 폴더를 훑어 sessions.json을 만든다")
    p.add_argument("raw_dir")
    p.add_argument("--out", required=True)
    p.add_argument("--gap", type=float, default=3.0)
    p.set_defaults(func=cmd_scan)

    args = ap.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
