#!/usr/bin/env python3
"""네이버 SmartEditor 스타일 패스: 모든 사진 가운데 정렬 + 모든 구분선 line3(가운데 꺾임)+center.
migrate.py의 JS_STYLE_NEXT_IMG / JS_STYLE_NEXT_HR 를 그대로 복제. 순수 합성 JS(osascript)."""
import subprocess, base64, time, sys

def chrome_js(js):
    b64 = base64.b64encode(js.encode("utf-8")).decode()
    wrapped = "eval(decodeURIComponent(escape(atob('%s'))))" % b64
    r = subprocess.run(
        ["osascript", "-e",
         'tell application "Google Chrome" to execute active tab of window 1 javascript "%s"' % wrapped],
        capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()

JS_STYLE_NEXT_HR = """
(() => {
  const hr = Array.from(document.querySelectorAll('.se-component.se-horizontalLine'))
    .find(c => { const s = c.querySelector('.se-section').className;
      return !(s.includes('se-l-line3') && s.includes('se-section-align-center')); });
  if (!hr) return 'done';
  hr.scrollIntoView({block: 'center'});
  const mod = hr.querySelector('.se-module-horizontalLine') || hr.querySelector('hr') || hr;
  ['mousedown','mouseup','click'].forEach(t =>
    mod.dispatchEvent(new MouseEvent(t, {bubbles:true,cancelable:true,view:window,button:0})));
  window.__sr = 'pending';
  setTimeout(() => {
    const lay = Array.from(document.querySelectorAll('button[data-name=horizontal-line-layout]'))
      .find(b => b.getAttribute('data-value') === 'line3' && b.offsetParent);
    if (lay) lay.click();
    setTimeout(() => {
      const al = Array.from(document.querySelectorAll('button[data-name=align]'))
        .find(b => b.getAttribute('data-value') === 'center' && b.offsetParent);
      if (al) al.click();
      setTimeout(() => { const s = hr.querySelector('.se-section').className;
        window.__sr = (s.includes('se-l-line3') && s.includes('se-section-align-center')) ? 'ok' : 'failed:' + s;
      }, 250);
    }, 300);
  }, 450);
  return 'working';
})()"""

JS_STYLE_NEXT_IMG = """
(() => {
  const img = Array.from(document.querySelectorAll('.se-component.se-image'))
    .find(c => !c.querySelector('.se-section').className.includes('se-section-align-center'));
  if (!img) return 'done';
  img.scrollIntoView({block: 'center'});
  const mod = img.querySelector('.se-module-image') || img;
  ['mousedown','mouseup','click'].forEach(t =>
    mod.dispatchEvent(new MouseEvent(t, {bubbles:true,cancelable:true,view:window,button:0})));
  window.__sr = 'pending';
  setTimeout(() => {
    const al = Array.from(document.querySelectorAll('button[data-name=align]'))
      .find(b => b.getAttribute('data-value') === 'center' && b.offsetParent);
    if (al) al.click();
    setTimeout(() => { const s = img.querySelector('.se-section').className;
      window.__sr = s.includes('se-section-align-center') ? 'ok' : 'failed:' + s;
    }, 250);
  }, 450);
  return 'working';
})()"""

JS_DESELECT = """
(() => { const tm = document.querySelector('.se-component.se-text .se-module-text');
  if (tm) ['mousedown','mouseup','click'].forEach(t =>
    tm.dispatchEvent(new MouseEvent(t, {bubbles:true,cancelable:true,view:window,button:0})));
  return 'ok'; })()"""

JS_COUNT = """JSON.stringify({img: document.querySelectorAll('.se-component.se-image').length,
  imgC: Array.from(document.querySelectorAll('.se-component.se-image')).filter(c=>c.querySelector('.se-section').className.includes('se-section-align-center')).length,
  hr: document.querySelectorAll('.se-component.se-horizontalLine').length,
  hrC: Array.from(document.querySelectorAll('.se-component.se-horizontalLine')).filter(c=>{var s=c.querySelector('.se-section').className;return s.includes('se-l-line3')&&s.includes('se-section-align-center');}).length})"""

def loop(js, label):
    done = 0
    for _ in range(120):
        r = chrome_js(js)
        if r == 'done':
            break
        if not r.startswith('working'):
            print(f"  {label} unexpected: {r[:60]}")
        for _ in range(10):
            time.sleep(0.35)
            sr = chrome_js("window.__sr || 'none'")
            if sr.startswith('ok') or sr.startswith('failed'):
                if sr.startswith('failed'):
                    print(f"  {label} FAILED: {sr[:70]}")
                break
        done += 1
    print(f"{label}: {done} 처리")

subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'])
time.sleep(0.5)
print("before:", chrome_js(JS_COUNT))
loop(JS_STYLE_NEXT_IMG, "이미지 가운데정렬")
loop(JS_STYLE_NEXT_HR, "구분선 line3+center")
chrome_js(JS_DESELECT)
print("after :", chrome_js(JS_COUNT))
