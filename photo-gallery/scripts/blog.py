#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""네이버 블로그에서 글 목록과 발행 이미지 파일명을 받아옵니다.

네이버는 발행 이미지 URL 경로에 업로드 당시 원본 파일명을 보존합니다.
그래서 로컬 사진과 파일명만으로 대조할 수 있습니다.

JSON은 invalid escape 때문에 json.loads가 깨집니다. 정규식으로 파싱합니다.
"""
import html
import os
import re
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
LIST_URL = ("https://blog.naver.com/PostTitleListAsync.naver"
            "?blogId={blog_id}&currentPage={page}&countPerPage=30")
VIEW_URL = "https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"

_ROW = re.compile(r'"logNo":"(\d+)","title":"(.*?)",.*?"addDate":"(.*?)"')
_TAG = re.compile(r"^\s*\[([^\]]+)\]\s*(.*)$")
_IMG = re.compile(r'<img[^>]+class="[^"]*se-image-resource[^"]*"[^>]*>', re.IGNORECASE)
_SRC = re.compile(r'(?:data-lazy-src|src)="([^"]+)"', re.IGNORECASE)
_EXT = re.compile(r"\.(jpg|jpeg|png|gif|webp|heic)$", re.IGNORECASE)

# 행사명 뒤에 붙는 군더더기
_SUFFIX = re.compile(
    r"\s*(방문기|방문후기|후기|리뷰|다녀왔습니다|다녀옴)?\s*(\(\d+/\d+\))?\s*$")


def parse_post_list(text):
    """목록 API 응답에서 글들을 뽑습니다."""
    out, seen = [], set()
    for log_no, title, added in _ROW.findall(text):
        if log_no in seen:
            continue
        seen.add(log_no)
        # unquote_plus 다음에 html.unescape 를 한 번 더 겁니다. 제목에 &#39; 같은
        # HTML 엔티티가 그대로 들어오는 글이 758편 중 22편 있습니다. 이 제목이
        # 이벤트 폴더 이름이 되므로 풀지 않으면 폴더명에 &#39; 가 박힙니다.
        out.append({"log_no": log_no,
                    "title": html.unescape(urllib.parse.unquote_plus(title)),
                    "posted_at": added})
    return out


def split_tag(title):
    """제목 앞 대괄호 태그를 떼어냅니다."""
    m = _TAG.match(title)
    if not m:
        return None, title.strip()
    return m.group(1).strip(), m.group(2).strip()


def event_name(title):
    """행사명만 남깁니다. 대괄호 태그, 콜론 뒤 부제, 방문기 같은 접미를 뗍니다."""
    _tag, rest = split_tag(title)
    # 이 블로그는 부제 구분자로 콜론과 슬래시를 둘 다 씁니다. 슬래시를 안 자르면
    # "생애 첫 국전 방문기 / 피규어와 가챠샵 털기 / 2026.01" 이 통째로 폴더 이름이
    # 됩니다. 공백이 양쪽에 있는 " / " 만 자릅니다. "집 앞마당/집터" 처럼 붙은
    # 슬래시는 한 단어의 일부일 수 있습니다.
    rest = rest.split(" : ")[0].split(" :")[0].split(" / ")[0]
    rest = re.split(r"\.\.|!!|\?\?", rest)[0]
    rest = _SUFFIX.sub("", rest)
    return rest.strip(" .,!?")


def parse_image_names(html):
    """발행 이미지의 원본 파일명 목록입니다. 순서를 지키고 중복을 없앱니다."""
    out, seen = [], set()
    for tag in _IMG.findall(html):
        m = _SRC.search(tag)
        if not m:
            continue
        path = urllib.parse.urlparse(m.group(1)).path
        name = urllib.parse.unquote(os.path.basename(path))
        if not _EXT.search(name) or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def parse_image_urls(html):
    """(파일명, 원본화질 URL) 목록입니다. dHash 폴백이 이미지를 받을 때 씁니다."""
    out, seen = [], set()
    for tag in _IMG.findall(html):
        m = _SRC.search(tag)
        if not m:
            continue
        base = m.group(1).split("?")[0]
        name = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(base).path))
        if not _EXT.search(name) or name in seen:
            continue
        seen.add(name)
        out.append((name, base + "?type=w3840"))
    return out


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def fetch_bytes(url):
    """이미지 바이트를 받습니다."""
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def fetch_all(blog_id, pages=30, sleep=0.3):
    """글 목록 전체를 받아옵니다. 페이지가 비면 멈춥니다."""
    out, seen = [], set()
    for page in range(1, pages + 1):
        rows = parse_post_list(_get(LIST_URL.format(blog_id=blog_id, page=page)))
        if not rows:
            break
        fresh = [r for r in rows if r["log_no"] not in seen]
        if not fresh:
            break
        for r in fresh:
            seen.add(r["log_no"])
        out.extend(fresh)
        time.sleep(sleep)
    return out


def fetch_post_html(blog_id, log_no):
    return _get(VIEW_URL.format(blog_id=blog_id, log_no=log_no))
