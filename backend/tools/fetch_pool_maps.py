"""Fetch the .osu file of every map of the bundled pool (for tools/build_variants.py).

Usage: python tools/fetch_pool_maps.py OUT_DIR [--from-end]
Writes OUT_DIR/osu/<beatmap id>.osu, each checked against the pool's MD5. Files already there are kept, so an
interrupted run goes on where it stopped; maps that can't be fetched (updated or removed since the pool was built)
are listed in OUT_DIR/missing.json.
--from-end: a second run to have next to the first one, twice as fast together: it takes the maps from the end of
the pool backwards and only from the osu.direct mirror (its own rate limit), and leaves missing.json to the first.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

from osu_coach.infra.beatmaps import sources
from osu_coach.infra.map_pool import load_pool

out = Path(sys.argv[1])
(out / "osu").mkdir(parents=True, exist_ok=True)
pool = load_pool()
rows = [(int(b), str(m)) for b, m in zip(pool["beatmap_id"], pool["md5"], strict=True) if b and b > 0]
from_end = "--from-end" in sys.argv
if from_end:
    rows.reverse()


def download(beatmap_id: int, md5: str) -> bytes | None:
    if not from_end:
        return sources.download_osu(beatmap_id, expected_md5=md5)
    r = sources._get(f"https://osu.direct/api/osu/{beatmap_id}", "osu.direct")
    ok = r is not None and r.status_code == 200 and hashlib.md5(r.content).hexdigest() == md5
    return r.content if ok else None


missing, fetched, started = [], 0, time.monotonic()
for i, (beatmap_id, md5) in enumerate(rows):
    path = out / "osu" / f"{beatmap_id}.osu"
    if path.exists() and (from_end or hashlib.md5(path.read_bytes()).hexdigest() == md5):
        continue
    data = download(beatmap_id, md5)
    if data is None:
        missing.append(beatmap_id)
    else:
        temp = path.with_suffix(".end" if from_end else ".tmp")
        temp.write_bytes(data)
        temp.replace(path)
        fetched += 1
    if (fetched + len(missing)) % 200 == 0:
        print(
            f"{i + 1}/{len(rows)} fetched {fetched} missing {len(missing)} {time.monotonic() - started:.0f}s",
            flush=True,
        )
        if not from_end:
            (out / "missing.json").write_text(json.dumps(missing))
if not from_end:
    (out / "missing.json").write_text(json.dumps(missing))
print(f"done: fetched {fetched}, missing {len(missing)} of {len(rows)}", flush=True)
