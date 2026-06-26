#!/usr/bin/env python3
"""네이버·구글 연관검색어(자동완성) 조회.

태그 후보를 실제 검색 수요와 대조하기 위한 스크립트.
- 네이버: ac.search.naver.com 자동완성 (타깃 플랫폼이므로 1순위 신호)
- 구글: suggestqueries.google.com (보조)

사용:
    python3 related_keywords.py "포코피아 지라치" "하이퍼버닝 MAX" ...

각 쿼리마다 네이버/구글 연관검색어를 출력한다. 출력된 멀티키워드 조합이
합성 태그(예: #포코피아지라치서식지)의 근거가 된다.
"""
import sys, json, urllib.parse, subprocess

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")


def _get(url, charset="utf-8"):
    # urllib 은 일부 환경에서 SSL 검증이 막힘 → curl 사용(워크플로 공통 의존성)
    return subprocess.run(["curl", "-s", "-A", UA, url],
                          capture_output=True, timeout=15).stdout.decode(charset, "replace")


def naver(q):
    url = ("https://ac.search.naver.com/nx/ac?"
           + urllib.parse.urlencode({"q": q, "r_format": "json", "st": "100",
                                     "frm": "mobile", "ans": "2", "con": "0"}))
    try:
        data = json.loads(_get(url))
    except Exception as e:
        return [], f"(naver error: {e})"
    out = []
    for group in data.get("items", []):
        for item in group:
            if item and isinstance(item, list) and item[0]:
                out.append(item[0])
    return _dedup(out), None


def google(q):
    # client=firefox 는 ie/oe 를 안 주면 latin-1 로 떨어진다 → utf-8 강제
    url = ("https://suggestqueries.google.com/complete/search?"
           + urllib.parse.urlencode({"client": "firefox", "hl": "ko",
                                     "ie": "UTF-8", "oe": "UTF-8", "q": q}))
    try:
        data = json.loads(_get(url))
    except Exception as e:
        return [], f"(google error: {e})"
    return _dedup(data[1] if len(data) > 1 else []), None


def _dedup(seq):
    seen = []
    for x in seq:
        x = (x or "").strip()
        if x and x not in seen:
            seen.append(x)
    return seen


def main(argv):
    if not argv:
        print("usage: related_keywords.py <query> [query ...]", file=sys.stderr)
        return 1
    for q in argv:
        print(f"\n### {q}")
        nv, err = naver(q)
        print("  [네이버] " + (" · ".join(nv) if nv else (err or "(없음)")))
        gg, err = google(q)
        print("  [구글]   " + (" · ".join(gg) if gg else (err or "(없음)")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
