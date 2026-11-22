"""Build the pp table of the bundled map pool: the pp of a full combo at the play goals' accuracies for every pool map
in each of their mod combinations, on stable and on lazer, so Farm PP needs no .osu file and no calculation.

Usage: python tools/build_pp_table.py RAW_DIR [POOL] [OUT]
RAW_DIR is the output of tools/fetch_pool_raw.py (osu/<beatmap_id>.osu); the defaults are the bundled pool and
osu_coach/infra/data/pool_pp.npz. Run it after tools/build_pool.py and after a new rosu-pp
(backend/tests/infra/test_pp_table.py fails while the table is stale). A few minutes on all cores; what is done is
kept in RAW_DIR/pp/ (by calculator version), so a stopped run goes on where it was.
"""

import hashlib
import multiprocessing as mp
import pickle
import sys
import time
from pathlib import Path

import numpy as np

from osu_coach.infra.beatmaps.performance import CALCULATOR_VERSION
from osu_coach.infra.map_pool import POOL_PATH, load_pool
from osu_coach.infra.pp_table import POOL_PP_PATH, map_pp, save_pp_table

BLOCK = 1024  # maps a file of finished work


def work(args):
    raw_dir, beatmap_id, md5 = args
    try:
        raw = (Path(raw_dir) / "osu" / f"{beatmap_id}.osu").read_bytes()
    except OSError:
        return None
    if hashlib.md5(raw).hexdigest() != md5:
        return None
    return map_pp(raw)


def main(argv: list[str]) -> int:
    raw = Path(argv[0])
    pool = load_pool(argv[1] if len(argv) > 1 else POOL_PATH)
    out = Path(argv[2]) if len(argv) > 2 else POOL_PP_PATH
    done_dir = raw / "pp"
    done_dir.mkdir(exist_ok=True)
    maps = [(str(raw), int(b), str(m)) for b, m in zip(pool["beatmap_id"].fillna(0), pool["md5"])]
    t0 = time.monotonic()
    parts: list = []
    with mp.Pool(max(1, mp.cpu_count() - 1)) as workers:
        for start in range(0, len(maps), BLOCK):
            block = maps[start : start + BLOCK]
            # a block is the work of these maps, in this order, with this calculator
            name = hashlib.md5((CALCULATOR_VERSION + "".join(m for _, _, m in block)).encode()).hexdigest()[:16]
            path = done_dir / f"{name}.pickle"
            if path.exists():
                done = pickle.loads(path.read_bytes())
            else:
                done = workers.map(work, block, chunksize=8)
                temp = path.with_suffix(".tmp")
                temp.write_bytes(pickle.dumps(done))
                temp.replace(path)
                print(f"{start + len(block)}/{len(maps)} {time.monotonic() - t0:.0f}s", flush=True)
            parts += done
    found = [p for p in parts if p is not None]
    whole = sum(bool(np.isfinite(p).all()) for p in found)
    note = {"maps": len(parts), "found": len(found), "complete": whole}
    p = save_pp_table(out, [m for _, _, m in maps], parts, note)
    print(
        f"wrote {len(parts)} maps to {p} ({p.stat().st_size / 2**20:.1f} MiB) in {time.monotonic() - t0:.0f}s:"
        f" {len(parts) - len(found)} without a file, {len(found) - whole} without every value"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
