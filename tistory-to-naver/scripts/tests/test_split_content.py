"""split_content_into_chunks가 본문 글을 버리지 않는지 확인한다.

fixture는 티스토리 632의 더보기 블록이다. 사진 그리드·낱장 사진·글머리 목록이 섞여 있다.
"""
import pathlib
import sys

from bs4 import BeautifulSoup

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import migrate_from_url as m  # noqa: E402

FIXTURE = (HERE / "fixtures" / "moreless_632.html").read_text()


def _chunks(html, monkeypatch):
    names = iter(f"/tmp/img{i:02d}.jpg" for i in range(100))
    monkeypatch.setattr(m, "download_image", lambda src: next(names))
    soup = BeautifulSoup(f"<div>{html}</div>", "html.parser").div
    return m.split_content_into_chunks(soup)


def _text(chunks):
    html = "".join(c["content"] for c in chunks if c["type"] == "html")
    return BeautifulSoup(html, "html.parser").get_text()


def test_moreless_keeps_text_and_images(monkeypatch):
    chunks = _chunks(FIXTURE, monkeypatch)
    text = _text(chunks)
    for s in ("나무위키의 설명을 가져왔습니다.", "탄환 발사", "낙하 공격", "줄기 공격",
              "덩쿨 채찍", "대폭발", "보호막 캐릭터를 대동하는 것이 좋다"):
        assert s in text, s
    assert sum(c["type"] == "image" for c in chunks) == 6
    # 접기 버튼 글자는 네이버에 접기가 없으므로 옮기지 않는다
    assert "더보기" not in text


def test_moreless_keeps_order(monkeypatch):
    chunks = _chunks(FIXTURE, monkeypatch)
    seq = []
    for c in chunks:
        if c["type"] == "image":
            seq.append("I")
        else:
            t = BeautifulSoup(c["content"], "html.parser").get_text()
            seq.append("T:" + ("탄환" if "탄환 발사" in t else "낙하" if "낙하 공격" in t else ""))
    s = "".join(x if x == "I" else "[" + x + "]" for x in seq)
    # 그리드 2장 -> 탄환 발사 -> 그리드 3장 -> 낙하 공격 -> 낱장 1장
    assert s.index("II") < s.index("탄환") < s.index("III") < s.index("낙하")


def test_grid_rows_become_strips(monkeypatch):
    chunks = _chunks(FIXTURE, monkeypatch)
    strips = [c.get("strip") for c in chunks if c["type"] == "image"]
    assert strips[0] is not None and strips[0] == strips[1]
    assert strips[2] is not None and strips[2] == strips[3] == strips[4]
    assert strips[1] != strips[2]
    assert strips[5] is None


def test_list_items_get_bullets(monkeypatch):
    chunks = _chunks(FIXTURE, monkeypatch)
    html = "".join(c["content"] for c in chunks if c["type"] == "html")
    assert "• " in html
    assert BeautifulSoup(html, "html.parser").get_text().count("•") == 5


def test_figcaption_is_kept(monkeypatch):
    html = ('<figure class="imageblock"><span><img src="https://x/a.jpg"></span>'
            '<figcaption>사진 설명입니다</figcaption></figure>')
    chunks = _chunks(html, monkeypatch)
    assert [c["type"] for c in chunks] == ["image", "html"]
    assert "사진 설명입니다" in _text(chunks)


def test_missing_text_reports_nothing_for_fixture(monkeypatch):
    soup = BeautifulSoup(f"<div>{FIXTURE}</div>", "html.parser").div
    chunks = _chunks(FIXTURE, monkeypatch)
    assert m.missing_text(soup, chunks) == []


def test_missing_text_catches_drop():
    soup = BeautifulSoup("<div><p>첫 문단</p><p>빠진 문단</p></div>", "html.parser").div
    chunks = [{"type": "html", "content": "<p>첫 문단</p>"}]
    assert m.missing_text(soup, chunks) == ["빠진 문단"]


def test_nested_list_indents_and_keeps_source(monkeypatch):
    html = "<ul><li>상위<ul><li>하위</li></ul></li></ul>"
    soup = BeautifulSoup(f"<div>{html}</div>", "html.parser").div
    monkeypatch.setattr(m, "download_image", lambda src: "/tmp/x.jpg")
    chunks = m.split_content_into_chunks(soup)
    text = _text(chunks)
    assert "• 상위" in text and "◦ 하위" in text and "하위" not in text.split("◦")[0]
    assert m.missing_text(soup, chunks) == []
