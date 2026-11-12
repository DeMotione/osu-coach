"""Fetch raw material for the bundled map pool: ranked osu!standard
difficulties (metadata via osu.direct search) + their .osu files.

Usage: python tools/fetch_pool_raw.py OUT_DIR [pages] [total] [--select-only]

pages: how many pages of 100 most-played ranked sets to search (default 500; the search stops at the last one).
total: difficulties to keep (default 50000): every one of 6 stars and more, and the rest in two equal halves,
under 5 stars and 5-6 stars, most played first. A half short of maps leaves its places to the other.
--select-only: stop after the search and the choice (sets.json, chosen.json), without downloading .osu files.
"""

import json
import sys
import time
from pathlib import Path

from osu_coach.infra.beatmaps import sources

args = [a for a in sys.argv[1:] if not a.startswith("--")]
select_only = "--select-only" in sys.argv
out = Path(args[0])
pages = int(args[1]) if len(args) > 1 else 500
total = int(args[2]) if len(args) > 2 else 50000
MIN_STARS = 0.8
GROUPS = ("under 5*", "5-6*", "6* and more")
(out / "osu").mkdir(parents=True, exist_ok=True)
meta_path = out / "sets.json"


def group(d) -> str:
    return GROUPS[0] if d["stars"] < 5 else GROUPS[1] if d["stars"] < 6 else GROUPS[2]


def shares(found: dict[str, int], total: int) -> dict[str, int]:
    """How many difficulties of each group to keep: all of the top one, the rest of ``total`` in two halves."""
    top = min(found[GROUPS[2]], total)
    rest = total - top
    low = min(found[GROUPS[0]], rest - rest // 2)
    mid = min(found[GROUPS[1]], rest - low)
    low = min(found[GROUPS[0]], rest - mid)  # what 5-6* could not fill
    return {GROUPS[0]: low, GROUPS[1]: mid, GROUPS[2]: top}


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
seen = set()
for s in sets:
    for b in s.get("beatmaps", []):
        if b.get("mode_int") != 0 or b.get("convert") or b["id"] in seen:
            continue
        sr = b.get("difficulty_rating") or 0
        if sr < MIN_STARS:
            continue
        seen.add(b["id"])
        diffs.append(
            {
                "beatmap_id": b["id"],
                "beatmapset_id": s["id"],
                "md5": b.get("checksum"),
                "artist": s.get("artist"),
                "title": s.get("title"),
                "creator": s.get("creator"),
                "version": b.get("version"),
                "status": b.get("status"),
                "stars": sr,
                "ar": b.get("ar"),
                "od": b.get("accuracy"),
                "cs": b.get("cs"),
                "hp": b.get("drain"),
                "bpm": b.get("bpm"),
                "length": b.get("total_length"),
                "drain_length": b.get("hit_length"),
                "n_circles": b.get("count_circles"),
                "n_sliders": b.get("count_sliders"),
                "n_spinners": b.get("count_spinners"),
                "max_combo": b.get("max_combo"),
                "playcount": b.get("playcount") or 0,
                "passcount": b.get("passcount") or 0,
                "set_playcount": s.get("play_count") or 0,
                "favourites": s.get("favourite_count") or 0,
                "ranked_date": s.get("ranked_date"),
            }
        )
# the most played difficulties of each group
groups: dict[str, list] = {name: [] for name in GROUPS}
for d in diffs:
    groups[group(d)].append(d)
for lst in groups.values():
    lst.sort(key=lambda d: -d["playcount"])
keep = shares({name: len(lst) for name, lst in groups.items()}, total)
chosen = [d for name in GROUPS for d in groups[name][: keep[name]]]
print("difficulties available", len(diffs), "chosen", len(chosen), flush=True)
for name in GROUPS:
    print(f"  {name}: {keep[name]} of {len(groups[name])}", flush=True)
(out / "chosen.json").write_text(json.dumps(chosen))
if select_only:
    sys.exit(0)

t0 = time.monotonic()
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
        print(f"{i}/{len(chosen)} ok={ok} fail={fail} {time.monotonic() - t0:.0f}s", flush=True)
    if i % 1000 == 0:
        failed_path.write_text(json.dumps(sorted(failed)))  # a stopped run starts again where it was
print("done", ok, fail, flush=True)

# replace what no mirror had by the next most played difficulty of the same group
have = [d for d in chosen if (out / "osu" / f"{d['beatmap_id']}.osu").exists()]
have_ids = {d["beatmap_id"] for d in have}
taken = {d["beatmap_id"] for d in chosen}
missing: dict[str, int] = {}
for d in chosen:
    if d["beatmap_id"] not in have_ids:
        missing[group(d)] = missing.get(group(d), 0) + 1
for name, n in missing.items():
    for d in groups[name]:
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
print(f"final: {len(have)} difficulties with .osu files", flush=True)
for name in GROUPS:
    print(f"  {name}: {sum(group(d) == name for d in have)}", flush=True)
