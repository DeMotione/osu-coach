"""Fetch raw material for the bundled map pool: popular ranked osu!standard
difficulties (metadata via osu.direct search) + their .osu files.

Usage: python dev_tools/fetch_pool_raw.py OUT_DIR [pages] [total] [core_share]

pages: how many pages of 100 most-played ranked sets to search (default 120).
total: difficulties to keep (default 5000). core_share (default 0.85) of them are 2-8 stars, split evenly
over 0.25-star steps, most played first; the rest go to 0.8-2 and 8-8.5 stars. Steps short of maps are
topped up with the next most played 2-8 star difficulties.
"""
import json
import math
import sys
import time
from pathlib import Path

from osu_coach.infrastructure.http import sources

out = Path(sys.argv[1])
pages = int(sys.argv[2]) if len(sys.argv) > 2 else 120
total = int(sys.argv[3]) if len(sys.argv) > 3 else 5000
core_share = float(sys.argv[4]) if len(sys.argv) > 4 else 0.85
CORE = (2.0, 8.0)
(out / "osu").mkdir(parents=True, exist_ok=True)
meta_path = out / "sets.json"

if meta_path.exists():
    sets = json.loads(meta_path.read_text())
else:
    sets = []
    for page in range(pages):
        batch = sources.search_sets(sort="play_count:desc", status="ranked", amount=100, offset=page * 100)
        print("page", page, len(batch), flush=True)
        if not batch:
            break
        sets.extend(batch)
    meta_path.write_text(json.dumps(sets))
print("sets:", len(sets), flush=True)

diffs = []
for s in sets:
    for b in s.get("beatmaps", []):
        if b.get("mode_int") != 0 or b.get("convert"):
            continue
        sr = b.get("difficulty_rating") or 0
        if not 0.8 <= sr <= 8.5:
            continue
        diffs.append({
            "beatmap_id": b["id"], "beatmapset_id": s["id"], "md5": b.get("checksum"),
            "artist": s.get("artist"), "title": s.get("title"), "creator": s.get("creator"),
            "version": b.get("version"), "status": b.get("status"), "stars": sr,
            "ar": b.get("ar"), "od": b.get("accuracy"), "cs": b.get("cs"), "hp": b.get("drain"),
            "bpm": b.get("bpm"), "length": b.get("total_length"), "drain_length": b.get("hit_length"),
            "n_circles": b.get("count_circles"), "n_sliders": b.get("count_sliders"),
            "n_spinners": b.get("count_spinners"), "max_combo": b.get("max_combo"),
            "playcount": b.get("playcount") or 0, "passcount": b.get("passcount") or 0,
            "set_playcount": s.get("play_count") or 0, "favourites": s.get("favourite_count") or 0,
            "ranked_date": s.get("ranked_date"),
        })
# most played difficulties per 0.25* step: core steps (2-8*) share core_share of the total, the rest the remainder
bins: dict[int, list] = {}
for d in diffs:
    bins.setdefault(int(d["stars"] * 4), []).append(d)
is_core = {k: CORE[0] <= k / 4 < CORE[1] for k in bins}
n_core = sum(is_core.values()) or 1
n_outer = (len(bins) - n_core) or 1
quota = {k: math.ceil((core_share if is_core[k] else 1 - core_share) * total / (n_core if is_core[k] else n_outer))
         for k in bins}
chosen, spare = [], []
for k, lst in sorted(bins.items()):
    lst.sort(key=lambda d: -d["playcount"])
    chosen.extend(lst[:quota[k]])
    if is_core[k]:
        spare.extend(lst[quota[k]:])
spare.sort(key=lambda d: -d["playcount"])
chosen.extend(spare[:max(0, total - len(chosen))])
extra = len(chosen) - total                       # quotas are rounded up: drop the least played 2-8* ones
if extra > 0:
    core_idx = sorted((i for i, d in enumerate(chosen) if CORE[0] <= d["stars"] < CORE[1]),
                      key=lambda i: chosen[i]["playcount"])[:extra]
    drop = set(core_idx)
    chosen = [d for i, d in enumerate(chosen) if i not in drop]
core_n = sum(CORE[0] <= d["stars"] < CORE[1] for d in chosen)
print("difficulties available", len(diffs), "chosen", len(chosen), f"({core_n} in 2-8*)", flush=True)
(out / "chosen.json").write_text(json.dumps(chosen))

t0 = time.time()
ok = fail = 0
failed_path = out / "failed.json"
failed = set(json.loads(failed_path.read_text())) if failed_path.exists() else set()


def fetch(d) -> bool:
    """The .osu file for one difficulty (already there, or downloaded); False if no mirror has it."""
    p = out / "osu" / f"{d['beatmap_id']}.osu"
    if p.exists():
        return True
    if d["beatmap_id"] in failed:
        return False
    data = sources.download_osu(d["beatmap_id"], expected_md5=d["md5"])
    if data is None:
        data = sources.download_osu(d["beatmap_id"])  # map updated since metadata snapshot
    if data:
        p.write_bytes(data)
        return True
    failed.add(d["beatmap_id"])
    return False


for i, d in enumerate(chosen):
    if fetch(d):
        ok += 1
    else:
        fail += 1
    if i % 100 == 0:
        print(f"{i}/{len(chosen)} ok={ok} fail={fail} {time.time() - t0:.0f}s", flush=True)
print("done", ok, fail, flush=True)

# replace what no mirror had by the next most played difficulty of the same 0.25* step
have = [d for d in chosen if (out / "osu" / f"{d['beatmap_id']}.osu").exists()]
have_ids = {d["beatmap_id"] for d in have}
taken = {d["beatmap_id"] for d in chosen}
missing: dict[int, int] = {}
for d in chosen:
    if d["beatmap_id"] not in have_ids:
        missing[int(d["stars"] * 4)] = missing.get(int(d["stars"] * 4), 0) + 1
for k, n in sorted(missing.items()):
    for d in bins[k]:
        if n <= 0:
            break
        if d["beatmap_id"] in taken:
            continue
        taken.add(d["beatmap_id"])
        if fetch(d):
            have.append(d)
            n -= 1
failed_path.write_text(json.dumps(sorted(failed)))
(out / "chosen.json").write_text(json.dumps(have))
print(f"final: {len(have)} difficulties with .osu files "
      f"({sum(CORE[0] <= d['stars'] < CORE[1] for d in have)} in 2-8*)", flush=True)
