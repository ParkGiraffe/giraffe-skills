"""story_read_sheet.py: plan.json 항목마다 썸네일과 자막 띠(또는 전투 대사 박스)를 크게 붙인 판독용 시트.

    story_read_sheet.py <작업 폴더>

캡션을 쓰려면 자막 글자가 읽혀야 하는데 콘택트 시트의 썸네일로는 안 읽힌다. 자막 띠를
1152px 폭으로 붙이면 읽힌다. 결과는 <작업 폴더>/read_NN.jpg (10줄씩). 2026-09-03 2~4편 제작에 사용.
"""
import sys, json, pathlib, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from PIL import Image, ImageDraw, ImageOps
import story_frames as sf
work = pathlib.Path(sys.argv[1]); per = 10
plan = json.loads((work / "plan.json").read_text(encoding="utf-8"))
font = sf.load_font(22); TH = (384, 216); BW = 1152
rows = []
idx = 0
for sec in plan["sections"]:
    for it in sec["items"]:
        idx += 1
        if it["type"] in ("video", "heading"): continue
        srcs = [it["lead"]] + it["src"] if it["type"] == "strip" else [it["src"]]
        for k, src in enumerate(srcs):
            name = pathlib.Path(src).name
            m = re.match(r"(\d{3})_#", name); orig = m.group(1) if m else name[:16]
            label = f"{idx:03d} {it['type']} {it.get('guess','')}" + (f" +{k}" if k else "") + (" 손크롭" if it.get("hand_crop") else "") + f"\n{orig}"
            rows.append((label, src, it.get("guess", "")))
def band_for(img, guess):
    if img.size != sf.FRAME: return None
    box = sf.DIALOG_BOX if guess == "dialog" else sf.SUBTITLE_BAND
    b = img.crop(box); h = round(BW * b.height / b.width); return b.resize((BW, h))
out = []
for n in range(0, len(rows), per):
    chunk = rows[n:n+per]
    sheet = Image.new("RGB", (260 + TH[0] + 12 + BW, len(chunk) * (TH[1] + 8)), (20, 20, 20)); d = ImageDraw.Draw(sheet)
    for r, (label, src, guess) in enumerate(chunk):
        y = r * (TH[1] + 8)
        d.multiline_text((4, y + 4), label, fill=(255, 255, 255), font=font)
        with Image.open(src) as im:
            im = im.convert("RGB")
            sheet.paste(ImageOps.fit(im, TH), (260, y))
            b = band_for(im, guess)
            if b is not None: sheet.paste(b, (260 + TH[0] + 12, y + (TH[1] - b.height) // 2))
            else:
                w = min(BW, im.width); h = round(w * im.height / im.width)
                if h > TH[1]: h = TH[1]; w = round(h * im.width / im.height)
                sheet.paste(im.resize((w, h)), (260 + TH[0] + 12, y))
    p = work / f"read_{n//per+1:02d}.jpg"; sheet.save(p, quality=85); out.append(p.name)
print(work.name, "rows", len(rows), "sheets", out)
