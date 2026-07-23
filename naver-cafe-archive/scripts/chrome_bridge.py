#!/usr/bin/env python3
"""로그인된 Chrome 탭 안에서 JS를 실행해 네이버 카페 내부 API를 호출하는 브리지.

네이버는 외부 fetch/curl을 차단하지만, 로그인된 Chrome 탭의 페이지 컨텍스트에서
fetch를 돌리면 세션 쿠키·올바른 referer/origin이 그대로 붙어 인증 게이트를 통과한다.
`execute javascript`는 Promise를 await하지 못하므로, fetch 결과를 window 변수에
적재한 뒤 짧은 간격으로 폴링해 회수한다(검증된 비동기 회수 패턴).

전제:
  - Chrome > 보기 > 개발자용 > "Apple 이벤트의 JavaScript 허용" 토글 ON
  - 네이버 카페에 로그인된 상태
  - cafe.naver.com / section.cafe.naver.com 탭이 하나 이상 열려 있음
    (apis.naver.com 호출의 origin/referer 제공용)

사용:
  from chrome_bridge import ChromeBridge
  cb = ChromeBridge()              # 자동으로 네이버 카페 탭을 찾음
  data = cb.api_get("https://apis.naver.com/cafe-home-web/cafe-home/v1/secede-cafes?page=1")
"""
import base64
import json
import subprocess
import time


class ChromeError(RuntimeError):
    pass


def _osa(script: str) -> str:
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if p.returncode != 0:
        raise ChromeError(p.stderr.strip() or "osascript failed")
    return p.stdout.rstrip("\n")


class ChromeBridge:
    def __init__(self, url_match: str = "cafe.naver.com"):
        self.url_match = url_match
        # sanity: confirm a cafe tab exists and JS injection works
        href = self.eval("location.href")
        if "cafe.naver.com" not in href:
            raise ChromeError(
                f"선택된 탭이 네이버 카페가 아님: {href}\n"
                "cafe.naver.com 탭을 하나 열어두세요.")
        self.origin = self.eval("location.origin")

    def eval(self, js: str) -> str:
        """동기 JS 실행. 매 호출마다 URL이 url_match를 포함하는 첫 탭을 찾아 실행.

        탭 인덱스를 캐시하지 않으므로 사용자가 탭을 옮기거나 닫아도 안전하다.
        """
        b64 = base64.b64encode(js.encode("utf-8")).decode("ascii")
        m = self.url_match.replace('"', '\\"')
        script = (
            'tell application "Google Chrome"\n'
            'repeat with w in windows\n'
            'repeat with t in tabs of w\n'
            f'if (URL of t) contains "{m}" then '
            f'return execute t javascript "eval(atob(\'{b64}\'))"\n'
            'end repeat\n'
            'end repeat\n'
            'error "NO_CAFE_TAB"\n'
            'end tell')
        return _osa(script)

    def api_get(self, url: str, headers: dict | None = None,
                timeout: float = 30.0, retries: int = 3) -> dict:
        """페이지 컨텍스트에서 GET fetch → JSON 파싱해 반환."""
        text = self.fetch_text(url, headers=headers, timeout=timeout,
                               retries=retries)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise ChromeError(f"JSON 파싱 실패 ({url}): {text[:200]}")

    def fetch_text(self, url: str, headers: dict | None = None,
                   timeout: float = 30.0, retries: int = 3) -> str:
        """페이지 컨텍스트에서 GET fetch → 응답 본문 텍스트 반환(폴링)."""
        hdr = {"X-Cafe-Product": "pc", "Accept": "application/json"}
        if headers:
            hdr.update(headers)
        last_err = ""
        for attempt in range(retries):
            token = f"__R{int(time.time()*1000)}_{attempt}"
            kick = (
                f"window.{token}=undefined;"
                f"fetch({json.dumps(url)},{{credentials:'include',"
                f"headers:{json.dumps(hdr)}}})"
                ".then(function(r){return r.text().then(function(t)"
                "{return {s:r.status,t:t}})})"
                f".then(function(o){{window.{token}={{done:1,status:o.s,body:o.t}}}})"
                f".catch(function(e){{window.{token}={{done:1,status:-1,body:String(e)}}}});"
                "'kick'")
            self.eval(kick)
            deadline = time.time() + timeout
            while time.time() < deadline:
                raw = self.eval(
                    f"window.{token}?JSON.stringify(window.{token}):''")
                if raw:
                    obj = json.loads(raw)
                    self.eval(f"delete window.{token}")
                    status = obj.get("status")
                    body = obj.get("body", "")
                    if status == 200:
                        return body
                    if status in (429, 503):
                        last_err = f"HTTP {status}"
                        time.sleep(2 ** attempt)
                        break
                    raise ChromeError(f"HTTP {status} ({url}): {body[:200]}")
                time.sleep(0.2)
            else:
                last_err = "timeout"
        raise ChromeError(f"fetch 실패 ({url}): {last_err}")


if __name__ == "__main__":
    import sys
    cb = ChromeBridge()
    print(f"[bridge] origin={cb.origin} match={cb.url_match}", file=sys.stderr)
    url = sys.argv[1] if len(sys.argv) > 1 else (
        "https://apis.naver.com/cafe-home-web/cafe-home/v1/member/identifier")
    print(json.dumps(cb.api_get(url), ensure_ascii=False, indent=2))
