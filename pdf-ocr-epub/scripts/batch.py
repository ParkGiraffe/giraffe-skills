# -*- coding: utf-8 -*-
"""폴더 하나를 통째로 처리합니다. 원본은 읽기만 하고 결과는 새 폴더에 만듭니다.

사용법:
  python3 batch.py ocr  <입력폴더> <출력폴더> [--jobs 3]
  python3 batch.py epub <입력폴더> <출력폴더> [--jobs 3]

ocr  : 텍스트가 없는 쪽에 Vision OCR 층을 얹은 PDF를 만듭니다.
       이미 텍스트가 있는 쪽은 그대로 통과하므로, 스캔본과 텍스트 PDF를 섞어 돌려도 됩니다.
epub : 텍스트 레이어가 있는 PDF만 EPUB으로 바꿉니다. 스캔본은 건너뜁니다.

내용이 똑같은 파일(SHA-256 일치)은 한 번만 처리합니다.
"""
import fitz, hashlib, json, os, subprocess, sys, time, unicodedata as ud
from concurrent.futures import ThreadPoolExecutor

SCRIPTS = os.path.dirname(os.path.abspath(__file__))


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def clean_name(fname):
    """'책.pdf의 사본' 같은 이름에서 확장자를 바로잡습니다."""
    n = ud.normalize("NFC", fname)
    low = n.lower()
    i = low.rfind(".pdf")
    return (n[:i] if i >= 0 else os.path.splitext(n)[0]).strip()


def has_text_layer(path, samples=10):
    d = fitz.open(path)
    n = d.page_count
    idx = [int(i * (n - 1) / (samples - 1)) for i in range(samples)] if n > 1 else [0]
    hit = sum(1 for i in set(idx) if len(d[i].get_text("text").strip()) > 40)
    d.close()
    return hit >= len(set(idx)) * 0.7


def collect(root, mode):
    jobs, seen = [], {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith((".", "_"))]
        for f in sorted(fn):
            if f.startswith("._") or f.endswith(".part"):
                continue
            if ".pdf" not in ud.normalize("NFC", f).lower():
                continue
            p = os.path.join(dp, f)
            try:
                textual = has_text_layer(p)
            except Exception as e:
                print(f"  [열기 실패] {f}: {type(e).__name__}")
                continue
            if mode == "epub" and not textual:
                continue
            h = sha(p)
            if h in seen:
                print(f"  [중복 건너뜀] {clean_name(f)}  == {seen[h]}")
                continue
            seen[h] = clean_name(f)
            jobs.append({"src": p, "rel": os.path.relpath(dp, root), "base": clean_name(f)})
    return jobs


def main():
    if len(sys.argv) < 4 or sys.argv[1] not in ("ocr", "epub"):
        print(__doc__)
        sys.exit(2)
    mode, root, out = sys.argv[1], sys.argv[2], sys.argv[3]
    jobs_n = 3
    if "--jobs" in sys.argv:
        jobs_n = int(sys.argv[sys.argv.index("--jobs") + 1])

    jobs = collect(root, mode)
    print(f"\n{mode} 대상 {len(jobs)}건\n")
    if not jobs:
        return

    ext = ".pdf" if mode == "ocr" else ".epub"
    script = os.path.join(SCRIPTS, "ocr_pdf.py" if mode == "ocr" else "pdf2epub.py")

    def one(j):
        dst = os.path.join(out, j["rel"], j["base"] + ext)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        cmd = [sys.executable, script, j["src"], dst]
        if mode == "epub":
            cmd.append(j["base"])
        r = subprocess.run(cmd, capture_output=True)
        ok = r.returncode == 0
        msg = r.stdout.decode("utf-8", "replace").strip() if ok else \
            r.stderr.decode("utf-8", "replace").strip()[:300]
        print(f"  [{'완료' if ok else '실패'}] {j['base'][:48]}  {msg[:120]}")
        return {"base": j["base"], "ok": ok, "out": msg}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=jobs_n) as ex:
        res = list(ex.map(one, jobs))
    okn = sum(1 for r in res if r["ok"])
    print(f"\n완료 {okn}/{len(res)}, {round(time.time()-t0,1)}초")
    with open(os.path.join(out, "_결과.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
