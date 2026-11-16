"""Build the pool's table of mod and rate configurations (osu_coach.features.maps.variant_table).

Usage: python tools/build_variants.py RAW_DIR [OUT] [--workers N] [--follow]
RAW_DIR is the output of tools/fetch_pool_maps.py (osu/<beatmap id>.osu, missing.json). The table is made in parts
of 500 maps, kept in RAW_DIR/variants (a run that was stopped goes on with the parts not made yet), and written to
OUT (default: next to the bundled pool) once all are there. A map without its file is left out of the table: a
search then says it has no data for it.
--follow: while fetch_pool_maps.py is still running, make each part as soon as its maps are fetched.
About a second a map and worker; the whole pool takes a few hours.
"""

import json
import multiprocessing as mp
import sys
import time
from functools import partial
from pathlib import Path

from osu_coach.features.maps import variant_table as vt
from osu_coach.infra.map_pool import load_pool


def entry(raw: Path, item: tuple[int, str]):
    beatmap_id, md5 = item
    return vt.build_file(str(raw / "osu" / f"{beatmap_id}.osu"), md5)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    raw = Path(args[0])
    out = Path(args[1]) if len(args) > 1 else vt.TABLE_PATH
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else max(1, mp.cpu_count() - 1)
    follow = "--follow" in sys.argv
    pool = load_pool()
    maps = [(int(b or 0), str(m)) for b, m in zip(pool["beatmap_id"], pool["md5"], strict=True)]
    chunks = [maps[i : i + vt.CHUNK] for i in range(0, len(maps), vt.CHUNK)]
    parts = raw / "variants"
    parts.mkdir(parents=True, exist_ok=True)
    stamp = parts / "versions.json"
    if stamp.exists() and json.loads(stamp.read_text()) != vt.versions():
        sys.exit(f"{parts} holds parts of another version of the calculations: remove it to build again")
    stamp.write_text(json.dumps(vt.versions()))
    started = time.monotonic()

    def fetched(chunk) -> bool:
        """Whether every map of the part has its file, or is known not to have one."""
        missing_file = raw / "missing.json"
        missing = set(json.loads(missing_file.read_text())) if missing_file.exists() else set()
        return all(b in missing or (raw / "osu" / f"{b}.osu").exists() for b, _ in chunk)

    with mp.get_context("spawn").Pool(workers) as procs:
        while True:
            left = [i for i in range(len(chunks)) if not (parts / f"{i:05d}.npz").exists()]
            ready = [i for i in left if not follow or fetched(chunks[i])]
            for i in ready:
                entries = procs.map(partial(entry, raw), chunks[i], chunksize=4)
                temp = parts / f"{i:05d}.tmp"
                temp.write_bytes(vt.pack_chunk([m for _, m in chunks[i]], entries))
                temp.replace(parts / f"{i:05d}.npz")
                without = sum(e is None for e in entries)
                print(
                    f"part {i + 1}/{len(chunks)} ({without} maps without a file) {time.monotonic() - started:.0f}s",
                    flush=True,
                )
            if not left or not follow:
                break
            if not ready:
                time.sleep(60)
    vt.write_table(out, [(parts / f"{i:05d}.npz").read_bytes() for i in range(len(chunks))], len(maps))
    print(f"wrote {out} ({out.stat().st_size / 2**20:.1f} MiB)", flush=True)


if __name__ == "__main__":
    main()
