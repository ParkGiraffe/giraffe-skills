"""Fetch full Korean Pokedex (Gens 1-9, #1-1025) from PokeAPI.

Output: .claude/data/pokedex.json
Schema per entry:
  {
    "no": int,                 # National Dex number
    "ko": str,                 # Korean official name
    "en": str,                 # English name
    "generation": int,         # 1..9
    "types": [str, ...],       # Korean type names (current)
    "past_types": [            # Per-generation overrides (empty if unchanged)
      {"until_generation": int, "types": [str, ...]},
      ...
    ]
  }
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "https://pokeapi.co/api/v2"
WORKERS = 32
TOTAL = 1025
TYPE_COUNT = 18  # Stellar (#19) is not a real Pokemon type

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".claude" / "data" / "pokedex.json"


def fetch_json(url: str, retries: int = 4) -> dict:
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "giraffe-skills/pokedex-builder"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Failed after {retries} retries: {url} :: {last_err}")


def pick_ko(names: list[dict]) -> str | None:
    for n in names:
        if n["language"]["name"] == "ko":
            return n["name"]
    return None


def gen_to_int(slug: str) -> int:
    # "generation-iii" -> 3
    roman = slug.removeprefix("generation-").upper()
    table = {"I": 1, "V": 5, "X": 10}
    total = 0
    prev = 0
    for ch in reversed(roman):
        val = table[ch]
        if val < prev:
            total -= val
        else:
            total += val
        prev = val
    return total


def fetch_type_map() -> dict[str, str]:
    """Return {english_slug: korean_name} for all 18 base types."""
    result: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(fetch_json, f"{API}/type/{i}/"): i for i in range(1, TYPE_COUNT + 1)}
        for fut in as_completed(futs):
            data = fut.result()
            slug = data["name"]
            ko = pick_ko(data["names"]) or slug
            result[slug] = ko
    return result


def fetch_species(i: int) -> tuple[int, dict]:
    data = fetch_json(f"{API}/pokemon-species/{i}/")
    return i, {
        "ko": pick_ko(data["names"]),
        "generation": gen_to_int(data["generation"]["name"]),
        "en_species": data["name"],
    }


def fetch_pokemon(i: int) -> tuple[int, dict]:
    data = fetch_json(f"{API}/pokemon/{i}/")
    types = [t["type"]["name"] for t in sorted(data["types"], key=lambda t: t["slot"])]
    past = []
    for pt in data.get("past_types", []):
        # generation slug like "generation-v" means: in this gen and earlier, types were X
        until = gen_to_int(pt["generation"]["name"])
        past_types = [t["type"]["name"] for t in sorted(pt["types"], key=lambda t: t["slot"])]
        past.append({"until_generation": until, "types_en": past_types})
    return i, {"en": data["name"], "types_en": types, "past_types": past}


def bulk_fetch(fetch_one, label: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    done = 0
    last_print = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(fetch_one, i): i for i in range(1, TOTAL + 1)}
        for fut in as_completed(futs):
            idx, payload = fut.result()
            out[idx] = payload
            done += 1
            if time.time() - last_print > 2.0 or done == TOTAL:
                print(f"  [{label}] {done}/{TOTAL}", file=sys.stderr, flush=True)
                last_print = time.time()
    return out


def main() -> None:
    t0 = time.time()
    print("[1/3] type map (18 types)...", file=sys.stderr)
    type_map = fetch_type_map()
    print(f"      types ko sample: grass={type_map.get('grass')} fire={type_map.get('fire')}", file=sys.stderr)

    print(f"[2/3] species (1..{TOTAL})...", file=sys.stderr)
    species = bulk_fetch(fetch_species, "species")

    print(f"[3/3] pokemon (1..{TOTAL})...", file=sys.stderr)
    pokemon = bulk_fetch(fetch_pokemon, "pokemon")

    print("[merge] building pokedex.json...", file=sys.stderr)
    entries = []
    missing_ko = []
    for i in range(1, TOTAL + 1):
        sp = species[i]
        pk = pokemon[i]
        types_ko = [type_map.get(t, t) for t in pk["types_en"]]
        past_types_ko = [
            {
                "until_generation": p["until_generation"],
                "types": [type_map.get(t, t) for t in p["types_en"]],
                "types_en": p["types_en"],
            }
            for p in pk["past_types"]
        ]
        if not sp["ko"]:
            missing_ko.append(i)
        entries.append({
            "no": i,
            "ko": sp["ko"],
            "en": pk["en"],
            "generation": sp["generation"],
            "types": types_ko,
            "types_en": pk["types_en"],
            "past_types": past_types_ko,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "PokeAPI v2 (pokeapi.co)",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generations": "1-9",
        "count": len(entries),
        "type_map_ko": type_map,
        "entries": entries,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    dt = time.time() - t0
    print(f"[done] wrote {OUT} ({len(entries)} entries) in {dt:.1f}s", file=sys.stderr)
    if missing_ko:
        print(f"[warn] {len(missing_ko)} entries missing Korean name: {missing_ko[:10]}{'...' if len(missing_ko) > 10 else ''}", file=sys.stderr)


if __name__ == "__main__":
    main()
