"""Fetch raw material for the bundled map pool: popular ranked osu!standard
difficulties (metadata via osu.direct search) + their .osu files.

Usage: python dev_tools/fetch_pool_raw.py OUT_DIR [pages] [per_bin]
"""
import json
import sys
import time
from pathlib import Path

from osu_coach import sources

out = Path(sys.argv[1])
pages = int(sys.argv[2]) if len(sys.argv) > 2 else 40
per_bin = int(sys.argv[3]) if len(sys.argv) > 3 else 100
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
# keep the most played difficulties per 0.25* bin
bins: dict[int, list] = {}
for d in diffs:
    bins.setdefault(int(d["stars"] * 4), []).append(d)
chosen = []
for k, lst in sorted(bins.items()):
    lst.sort(key=lambda d: -d["playcount"])
    chosen.extend(lst[:per_bin])
print("difficulties available", len(diffs), "chosen", len(chosen), flush=True)
(out / "chosen.json").write_text(json.dumps(chosen))

t0 = time.time()
ok = fail = 0
for i, d in enumerate(chosen):
    p = out / "osu" / f"{d['beatmap_id']}.osu"
    if p.exists():
        ok += 1
        continue
    data = sources.download_osu(d["beatmap_id"], expected_md5=d["md5"])
    if data is None:
        data = sources.download_osu(d["beatmap_id"])  # map updated since metadata snapshot
    if data:
        p.write_bytes(data)
        ok += 1
    else:
        fail += 1
    if i % 100 == 0:
        print(f"{i}/{len(chosen)} ok={ok} fail={fail} {time.time() - t0:.0f}s", flush=True)
print("done", ok, fail, flush=True)
