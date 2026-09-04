#!/usr/bin/env python3
"""Set the Naver SmartEditor category and publish the open postwrite draft.

Reuses osascript helpers from inject_code_blocks. Naver blocks both
claude-in-chrome and computer-use (browser tier), so in-page JS via
`Google Chrome ... execute javascript` is the only working route.

Usage:
  python3 publish_with_category.py <categoryTestId> [expectedNameSubstring] [--private]
  e.g. python3 publish_with_category.py 142   # GoodWishes 제작기
       python3 publish_with_category.py 147 "JavaScript 강의실"
       python3 publish_with_category.py 177 "로스트아크" --private
  --private     공개 설정을 '비공개'로 바꾼 뒤 발행한다. 카테고리 선택과 같은
                IIFE 안에서 처리하고, 발행 직전에 비공개가 실제로 선택됐는지
                확인한다. 확인이 안 되면 발행하지 않고 exit 2 로 멈춘다.
  --dump-open   공개 설정 컨트롤 목록만 출력하고 종료한다 (발행하지 않음).
                셀렉터가 바뀌었을 때 실측용.

Flow (single in-page IIFE with chained polling, to survive the
window-raise blur that closes floating layers between osascript calls):
  1. open the 발행 layer (publish_btn__)
  2. open the category selectbox (selectbox_button__)
  3. poll until the dropdown list renders, click the matching radio label
     (data-testid=categoryItemText_<id>)
  4. verify the selectbox label changed
  5. click the confirm 발행 button (confirm_btn__)
Then confirm the postwrite tab navigated away (publish redirect = success).
"""
import json
import sys
import time

from inject_code_blocks import find_postwrite_tab, chrome_js, osa

_FLAGS = [a for a in sys.argv[1:] if a.startswith("--")]
_POS = [a for a in sys.argv[1:] if not a.startswith("--")]

PRIVATE = "--private" in _FLAGS      # 공개 설정을 '비공개'로 두고 발행
DUMP_ONLY = "--dump-open" in _FLAGS  # 공개 설정 컨트롤만 덤프하고 종료 (발행 안 함)

CAT_ID = _POS[0] if len(_POS) > 0 else "142"
# optional 2nd arg: expected category label substring used to verify the
# selection before publishing (default "제작기" for back-compat).
# e.g. python3 publish_with_category.py 147 "JavaScript 강의실"
EXPECT = _POS[1] if len(_POS) > 1 else "제작기"


def front_tab():
    loc = find_postwrite_tab()
    if not loc:
        return None
    win, tab = loc
    osa(f'tell application "Google Chrome" to set active tab index of window {win} to {tab}')
    osa(f'tell application "Google Chrome" to set index of window {win} to 1')
    tab = int(osa('tell application "Google Chrome" to get active tab index of window 1'))
    return 1, tab


def run(js):
    loc = front_tab()
    if not loc:
        return None
    return chrome_js(loc[0], loc[1], js)


# 공개 설정 컨트롤(전체공개/이웃공개/서로이웃공개/비공개)을 찾는 공용 JS 조각.
# 라디오가 <input type=radio>일 수도, role=radio 인 커스텀 요소일 수도 있어서
# 둘 다 훑고, 체크 여부는 input.checked 와 aria-checked 를 모두 본다.
OPEN_HELPERS = """
  var OPEN_LABELS=["전체공개","이웃공개","서로이웃공개","비공개"];
  function vis(e){return e && e.offsetParent!==null;}
  function norm(e){return (e.textContent||"").replace(/\\s/g,"");}
  function openControls(){
    var out=[];
    Array.from(document.querySelectorAll("label,button,[role=radio]")).forEach(function(e){
      var t=norm(e);
      if(OPEN_LABELS.indexOf(t)>=0 && vis(e)) out.push(e);
    });
    return out;
  }
  // 공개 설정은 <input id="open_private"> 과 <label for="open_private"> 이
  // 형제로 놓인 구조라(2026-09-04 실측), label.closest / label 안 querySelector
  // 로는 input 을 못 찾는다. for 속성으로 id 를 따라가는 것이 정답이다.
  function inputOf(e){
    if(e.tagName==="INPUT") return e;
    var f=e.getAttribute && e.getAttribute("for");
    if(f){ var byId=document.getElementById(f); if(byId) return byId; }
    var nested=e.querySelector?e.querySelector("input[type=radio]"):null;
    if(nested) return nested;
    return e.parentElement?e.parentElement.querySelector("input[type=radio]"):null;
  }
  function isOn(e){
    var i=inputOf(e);
    if(i) return !!i.checked;
    var a=e.getAttribute("aria-checked");
    if(a!==null) return a==="true";
    return false;
  }
  function currentOpen(){
    var on=openControls().filter(isOn);
    return on.length? norm(on[0]) : ("none/"+openControls().length);
  }
"""

DUMP_OPEN_JS = """(function(){
  window.__od="pending";
  if(!document.querySelector("[class*=option_category__]")){
    var pb=Array.from(document.querySelectorAll("button")).find(function(e){return e.className.indexOf("publish_btn__")>=0 && e.textContent.trim()==="발행";});
    if(pb) pb.click();
  }
  setTimeout(function(){
    __HELPERS__
    var rows=openControls().map(function(e){
      return {tag:e.tagName, text:norm(e), on:isOn(e),
              testid:e.getAttribute("data-testid"), cls:(e.className||"").slice(0,60)};
    });
    var radios=Array.from(document.querySelectorAll("input[type=radio]")).map(function(r){
      var l=r.closest("label");
      return {name:r.name, value:r.value, checked:r.checked,
              testid:r.getAttribute("data-testid"),
              label:l?norm(l).slice(0,24):""};
    });
    window.__od=JSON.stringify({controls:rows, radios:radios.slice(0,40)});
  },900);
  return "start";
})()""".replace("__HELPERS__", OPEN_HELPERS)

SELECT_JS = """(function(){
  window.__pr="pending";
  var WANT_PRIVATE=__PRIVATE__;
  __HELPERS__
  function done(v){window.__pr=v;}
  if(!document.querySelector("[class*=option_category__]")){
    var pb=Array.from(document.querySelectorAll("button")).find(function(e){return e.className.indexOf("publish_btn__")>=0 && e.textContent.trim()==="발행";});
    if(pb) pb.click();
  }
  function afterCategory(){
    var cur=document.querySelector(".selectbox_button__jb1Dt .text__sraQE");
    cur=cur?cur.textContent.trim():"nocur";
    if(!WANT_PRIVATE){ done("DONE|"+cur+"|open="+currentOpen()); return; }
    var target=openControls().filter(function(e){return norm(e)==="비공개";})[0];
    if(!target){ done("no-private-control|"+cur+"|open="+currentOpen()); return; }
    target.click();
    setTimeout(function(){ done("DONE|"+cur+"|open="+currentOpen()); },600);
  }
  setTimeout(function(){
    var sb=document.querySelector(".selectbox_button__jb1Dt");
    var expanded=sb && sb.getAttribute("aria-expanded")==="true";
    if(!expanded && sb) sb.click();
    var tries=0;
    (function waitList(){
      tries++;
      var el=document.querySelector("[data-testid=categoryItemText___CAT__]");
      if(el && vis(el)){
        var lab=el.closest("label");
        (lab||el).click();
        setTimeout(afterCategory,500);
        return;
      }
      if(tries>25){done("list-never|tries="+tries); return;}
      setTimeout(waitList,200);
    })();
  },400);
  return "start";
})()""".replace("__HELPERS__", OPEN_HELPERS) \
       .replace("__CAT__", CAT_ID) \
       .replace("__PRIVATE__", "true" if PRIVATE else "false")

CONFIRM_JS = """(function(){
  var b=document.querySelector("[class*=confirm_btn__]");
  if(b){ b.click(); return "published-click"; }
  return "no-confirm-btn";
})()"""


def main():
    if DUMP_ONLY:
        print("[dump] opening publish layer and listing 공개 설정 controls ...")
        if run(DUMP_OPEN_JS) is None:
            print("[ERROR] no postwrite tab found")
            sys.exit(1)
        for _ in range(15):
            time.sleep(0.6)
            out = run("window.__od")
            if out and out.startswith("{"):
                print(json.dumps(json.loads(out), ensure_ascii=False, indent=2))
                return
        print("[ERROR] 공개 설정 컨트롤을 찾지 못했습니다 (레이어가 안 열렸을 수 있음)")
        sys.exit(2)

    mode = "비공개" if PRIVATE else "전체공개(기본)"
    print(f"[publish] selecting category testid={CAT_ID}, 공개설정={mode} ...")
    if run(SELECT_JS) is None:
        print("[ERROR] no postwrite tab found")
        sys.exit(1)
    # poll the select result
    result = None
    for _ in range(15):
        time.sleep(0.6)
        result = run("window.__pr")
        if result and result.startswith("DONE"):
            break
        if result and (result.startswith("list-never")
                       or result.startswith("no-private-control")):
            break
    print(f"[publish] category result: {result}")
    if not (result and result.startswith("DONE") and EXPECT in result):
        print(f"[ERROR] category not selected as expected (want '{EXPECT}'); aborting before publish")
        sys.exit(2)
    # 비공개를 요청했으면 실제로 비공개가 선택됐는지 확인하고 나서만 발행한다.
    # 확인 없이 누르면 전체공개로 나가고, 발행 후에는 되돌려도 이미 노출된 뒤다.
    if PRIVATE and "|open=비공개" not in result:
        print(f"[ERROR] 비공개가 선택되지 않았습니다 ({result}); aborting before publish")
        sys.exit(2)

    print("[publish] clicking confirm 발행 ...")
    res = run(CONFIRM_JS)
    print(f"[publish] confirm: {res}")
    time.sleep(4)
    # success = postwrite tab gone (redirected) OR url no longer /postwrite
    loc = find_postwrite_tab()
    if loc is None:
        print("[publish] OK — postwrite tab redirected away (publish complete)")
    else:
        url = run("location.href")
        if url and "/postwrite" not in url:
            print(f"[publish] OK — navigated to {url}")
        else:
            print(f"[WARN] still on postwrite ({url}); publish may not have completed")
            sys.exit(3)


if __name__ == "__main__":
    main()
