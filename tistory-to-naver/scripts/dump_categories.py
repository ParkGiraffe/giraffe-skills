#!/usr/bin/env python3
"""Dump Naver SmartEditor blog categories (testid -> name).

Reuses migrate.py helpers so it opens/raises the postwrite tab itself
(same as a migration run). Read-only: opens the publish layer + category
selectbox and lists every category item. Does NOT publish.

Usage: python3 dump_categories.py [--blog-id op5321]
"""
import sys
import time

import migrate as m

DUMP_JS = """(function(){
  window.__cats="pending";
  if(!document.querySelector("[class*=option_category__]")){
    var pb=Array.from(document.querySelectorAll("button")).find(function(e){return e.className.indexOf("publish_btn__")>=0 && e.textContent.trim()==="발행";});
    if(pb) pb.click();
  }
  setTimeout(function(){
    var sb=document.querySelector(".selectbox_button__jb1Dt");
    if(sb && sb.getAttribute("aria-expanded")!=="true") sb.click();
    var tries=0;
    (function wait(){
      tries++;
      // category rows can carry testid categoryItemText_<id> OR categoryItem_<id>
      var els=Array.from(document.querySelectorAll("[data-testid^=categoryItem]"));
      // de-dup by id, prefer text-bearing node
      var map={};
      els.forEach(function(el){
        var tid=el.getAttribute("data-testid");
        var mm=tid.match(/categoryItem(?:Text)?_(\\d+)/);
        if(!mm) return;
        var id=mm[1]; var txt=el.textContent.trim();
        if(!map[id] || txt.length>map[id].length) map[id]=txt;
      });
      var ids=Object.keys(map);
      if(ids.length>1 || tries>30){
        window.__cats=JSON.stringify(ids.map(function(id){return {id:id,name:map[id]};}));
        return;
      }
      setTimeout(wait,200);
    })();
  },700);
  return "start";
})()"""


def main():
    blog_id = m.BLOG_ID
    if "--blog-id" in sys.argv:
        blog_id = sys.argv[sys.argv.index("--blog-id") + 1]

    print("[dump] opening/raising postwrite tab...")
    m.ensure_postwrite_tab(blog_id)
    m.chrome_js(m.JS_DISMISS_DIALOG)
    time.sleep(0.5)
    if not m.wait_for_window_focus():
        print("[ERROR] Chrome window never got OS focus")
        sys.exit(1)

    m.chrome_js(DUMP_JS)
    result = None
    for _ in range(15):
        time.sleep(0.6)
        result = m.chrome_js("window.__cats")
        if result and (result.startswith("[") or result == "list-never"):
            break
    if not result or result == "list-never":
        print(f"[ERROR] category list never rendered (result={result})")
        sys.exit(2)
    print(result)


if __name__ == "__main__":
    main()
