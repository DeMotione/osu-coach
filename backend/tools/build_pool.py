"""Build the bundled practice pool from raw .osu files.

Usage: python dev_tools/build_pool.py RAW_DIR [OUT]
RAW_DIR is the output of dev_tools/fetch_pool_raw.py (chosen.json + osu/<id>.osu).
"""
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

from osu_coach.maps.repository import POOL_PATH, save_pool, stats_from_osu

META_KEYS = ("beatmap_id", "beatmapset_id", "status", "playcount", "passcount", "favourites", "set_playcount",
             "ranked_date")


def work(args):
    raw, d = args
    p = Path(raw) / "osu" / f"{d['beatmap_id']}.osu"
    if not p.exists():
        return None
    s = stats_from_osu(p.read_bytes())
    if not s:
        return None
    for k in META_KEYS:
        if d.get(k) is not None:
            s[k] = d[k]
    return s


if __name__ == "__main__":
    raw = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else POOL_PATH
    chosen = json.loads((raw / "chosen.json").read_text())
    t0 = time.time()
    rows = []
    with mp.Pool(max(1, mp.cpu_count())) as pool:
        for i, r in enumerate(pool.imap_unordered(work, [(str(raw), d) for d in chosen], chunksize=8)):
            if r:
                rows.append(r)
            if i % 250 == 0:
                print(f"{i}/{len(chosen)} ok={len(rows)} {time.time() - t0:.0f}s", flush=True)
    rows.sort(key=lambda r: (r.get("stars") or 0))
    p = save_pool(rows, out)
    print(f"wrote {len(rows)} maps to {p} ({p.stat().st_size / 1024:.0f} KiB) in {time.time() - t0:.0f}s")
