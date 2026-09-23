import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import se_doc  # noqa: E402

MD = """---
title: "t"
---

## 도입

![](images/001.jpg)

첫 문단입니다.

![](images/002.jpg) ![](images/003.jpg)

[영상 자리 : images/01_v01_첫 영상.mp4]

<!-- 감상 -->

![](images/004.jpg)
"""


def test_plan_counts_pairs_as_two_images():
    plan = se_doc.plan_from_markdown(MD)
    assert plan["expect_images"] == 4
    assert plan["pairs"] == [1]
    assert plan["sequence"] == ["I", "S2", "V", "I"]


def test_plan_video_title_falls_back_to_filename():
    plan = se_doc.plan_from_markdown(MD)
    assert plan["videos"] == [{"title": "첫 영상", "after": 3}]


def test_plan_video_title_from_meta():
    plan = se_doc.plan_from_markdown(MD, {"images/01_v01_첫 영상.mp4": "다른 제목"})
    assert plan["videos"][0]["title"] == "다른 제목"


def test_skeleton_groups_text_and_marks_images():
    ops = [("blank", 2), ("hr",), ("h", 2, "절"), ("img", "/x/001.jpg"),
           ("p", "본문 **굵게** 끝"), ("img", "/x/002.jpg")]
    comps = se_doc.skeleton_from_ops(ops)
    kinds = [c.get("@ctype") or "img" for c in comps]
    assert kinds == ["text", "horizontalLine", "text", "img", "text", "img", "text"]
    assert comps[1]["layout"] == "line3"
    heading = comps[2]["value"][0]["nodes"][0]
    assert heading["style"]["backgroundColor"] == "#fff593"
    assert heading["style"]["fontSizeCode"] == "fs24"
    nodes = comps[4]["value"][0]["nodes"]
    assert [n["value"] for n in nodes] == ["본문 ", "굵게", " 끝"]
    assert [n["style"]["bold"] for n in nodes] == [False, True, False]
    assert comps[3] == {"__img": 0} and comps[5] == {"__img": 1}
