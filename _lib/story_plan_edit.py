"""story_plan_edit.py: scan이 만든 plan.json을 사진 번호 기준 지시 파일로 다시 짠다.

    story_plan_edit.py <작업 폴더> <지시.json>

지시 파일 키: section_title, section_breaks {"25": "두 개의 생각"}, headings {"6": "미넬의 제안"},
videos_after {"25": {"file": "...mp4", "title": "..."}}, crop {"6": "scroll_wide"}, skip {"1": "이유"},
strips [[lead, ...]], strip_band {"lead": "dialog"}. 번호는 편 폴더 파일명 앞 세 자리다.
자동 묶음은 전부 풀고 지시대로만 다시 만든다. 2026-09-03 2~4편 제작에 사용.
"""
import sys, json, pathlib, re
work = pathlib.Path(sys.argv[1]); spec = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
plan = json.loads((work / "plan.json").read_text(encoding="utf-8"))
def idx_of(src):
    m = re.match(r"(\d{3})_#", pathlib.Path(src).name)
    if m: return int(m.group(1))
    stamp = re.search(r"(\d{16})", pathlib.Path(src).name).group(1)
    ep = pathlib.Path(plan["source"])
    return int(next(p.name[:3] for p in ep.iterdir() if stamp in p.name and not p.name.startswith(".")))
photos = []  # (idx, src, guess, hand_crop)
for sec in plan["sections"]:
    for it in sec["items"]:
        if it["type"] in ("video", "heading"): continue
        srcs = [it["lead"]] + it["src"] if it["type"] == "strip" else [it["src"]]
        for s in srcs: photos.append((idx_of(s), s, it.get("guess", ""), it.get("hand_crop")))
photos.sort()
skip = {int(k): v for k, v in spec.get("skip", {}).items()}
crop = {int(k): v for k, v in spec.get("crop", {}).items()}
headings = {int(k): v for k, v in spec.get("headings", {}).items()}
videos = {int(k): v for k, v in spec.get("videos_after", {}).items()}
strips = {s[0]: s for s in spec.get("strips", [])}  # lead idx -> [lead, ...]
in_strip = {i for s in spec.get("strips", []) for i in s[1:]}
sections = []; cur = {"title": spec["section_title"], "items": []}
sec_breaks = {int(k): v for k, v in spec.get("section_breaks", {}).items()}
by_idx = {p[0]: p for p in photos}
for idx, src, guess, hc in photos:
    if idx in sec_breaks:
        sections.append(cur); cur = {"title": sec_breaks[idx], "items": []}
    if idx in headings: cur["items"].append({"type": "heading", "title": headings[idx]})
    if idx in in_strip: pass
    elif idx in skip: cur["items"].append({"type": "skip", "src": src, "guess": guess, "reason": skip[idx]})
    elif idx in crop: cur["items"].append({"type": "crop", "src": src, "preset": crop[idx], "guess": guess})
    elif idx in strips:
        band = spec.get("strip_band", {}).get(str(idx), "subtitle")
        rec = {"type": "strip", "lead": src, "src": [by_idx[i][1] for i in strips[idx][1:]], "band": band, "guess": guess}
        cur["items"].append(rec)
    else:
        rec = {"type": "photo", "src": src, "guess": guess}
        if hc: rec["hand_crop"] = hc
        cur["items"].append(rec)
    if idx in videos: cur["items"].append({"type": "video", **videos[idx]})
sections.append(cur)
plan["sections"] = sections
(work / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
n_photo = sum(1 for s in sections for it in s["items"] if it["type"] in ("photo", "crop")) + sum(2 for s in sections for it in s["items"] if it["type"] == "strip")
print("sections", [(s["title"], len(s["items"])) for s in sections], "image components", n_photo)
