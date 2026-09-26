"""organize.py가 카톡·스크린샷·카메라 사진을 찍은 시각순으로 줄 세우는지 확인한다.

사례는 2026-09-21 포켓몬 고풍상점 폴더의 실제 파일명 형식을 따른다.
"""
import os
import pathlib
import subprocess
import sys

from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import organize as O  # noqa: E402


def _img(path, exif_time=None):
    im = Image.new("RGB", (40, 30), "white")
    kw = {}
    if exif_time:
        e = Image.Exif()
        e.get_ifd(0x8769)[36867] = exif_time
        kw["exif"] = e.tobytes()
    im.save(path, **kw)


def _folder(tmp_path):
    d = tmp_path / "shop"
    d.mkdir()
    # 카메라: EXIF 있음 / 얼굴 가리다 EXIF가 날아간 사진(파일명으로)
    _img(d / "20260921_121301.jpg", "2026:09:21 12:13:01")
    _img(d / "20260921_112814.jpg")
    # 카톡: 이름은 받은 시각(19:00), EXIF는 찍은 시각
    _img(d / "1789984824666.jpg", "2026:09:21 12:13:00")
    _img(d / "1789984824607.jpg", "2026:09:21 12:13:02")
    # 카톡인데 EXIF가 없음 -> 받은 시각으로 추정
    _img(d / "1789984899999.jpg")
    # 스크린샷(공백 들어간 앱 이름), IMG_ 형식
    _img(d / "Screenshot_20260921_113111_Pokmon GO.jpg")
    _img(d / "IMG_2026-09-21-12153467.jpg")
    (d / "20260921_121035.mp4").write_bytes(b"v")
    sub = d / "얼굴가리기"
    sub.mkdir()
    _img(sub / "20260921_112814.jpg", "2026:09:21 11:28:14")
    return d


def test_orders_by_capture_time(tmp_path):
    photos, videos, subdirs = O.plan(str(_folder(tmp_path)))
    assert [p["name"] for p in photos] == [
        "20260921_112814.jpg",
        "Screenshot_20260921_113111_Pokmon GO.jpg",
        "1789984824666.jpg",
        "20260921_121301.jpg",
        "1789984824607.jpg",
        "IMG_2026-09-21-12153467.jpg",
        "1789984899999.jpg",          # 받은 시각(추정)이라 맨 뒤
    ]
    assert videos == ["20260921_121035.mp4"]
    assert subdirs == ["얼굴가리기"]


def test_marks_guessed_times(tmp_path):
    photos, _, _ = O.plan(str(_folder(tmp_path)))
    src = {p["name"]: p["source"] for p in photos}
    assert src["1789984824666.jpg"] == "EXIF"
    assert src["20260921_112814.jpg"] == "파일명"
    assert src["IMG_2026-09-21-12153467.jpg"] == "파일명"
    assert src["1789984899999.jpg"].startswith("추정")


def test_kinds(tmp_path):
    photos, _, _ = O.plan(str(_folder(tmp_path)))
    k = {p["name"]: p["kind"] for p in photos}
    assert k["1789984824666.jpg"] == "카톡"
    assert k["Screenshot_20260921_113111_Pokmon GO.jpg"] == "스크린샷"
    assert k["20260921_121301.jpg"] == "카메라"


def test_run_numbers_watermarks_and_moves_videos(tmp_path):
    d = _folder(tmp_path)
    r = subprocess.run([sys.executable, str(HERE.parent / "organize.py"), str(d)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = sorted(n for n in os.listdir(d / "watermark") if not n.startswith("."))
    assert out[0] == "001_20260921_112814.jpg"
    assert out[1] == "002_Screenshot_20260921_113111_Pokmon GO.jpg"
    assert len(out) == 7                                  # 하위 폴더 사진은 안 섞임
    assert os.listdir(d / "movies") == ["20260921_121035.mp4"]
    assert not (d / "20260921_121035.mp4").exists()
    # 워터마크본에도 촬영 시각이 남는다
    e = Image.open(d / "watermark" / "004_20260921_121301.jpg").getexif()
    assert e.get_ifd(0x8769).get(36867) == "2026:09:21 12:13:01"


def test_refuses_nonempty_output(tmp_path):
    d = _folder(tmp_path)
    (d / "watermark").mkdir()
    _img(d / "watermark" / "old.jpg")
    r = subprocess.run([sys.executable, str(HERE.parent / "organize.py"), str(d)],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "비어 있지 않음" in r.stderr
