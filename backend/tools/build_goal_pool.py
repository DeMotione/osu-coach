"""Build deterministic offline goal data from cached public .osu files.

python backend/tools/build_goal_pool.py RAW_DIR [--fetch] [--count 64] [--output PATH]
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from pathlib import Path

from osu_coach.beatmaps.parser import parse_beatmap_bytes
from osu_coach.beatmaps.performance import CALCULATOR_VERSION, calculate
from osu_coach.beatmaps.sources import download_osu
from osu_coach.maps.goal_pool import CONFIGS, configuration
from osu_coach.maps.goal_repository import GOAL_POOL, SCHEMA_VERSION
from osu_coach.maps.repository import load_pool


def clean(value):
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: clean(v) for key, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--count", type=int, default=64)
    parser.add_argument("--output", type=Path, default=GOAL_POOL)
    args = parser.parse_args()
    pool = load_pool().sort_values(["stars", "md5"])
    # Even difficulty coverage, with two distinct pattern emphases per band.
    chosen = []
    for _, band in pool.groupby((pool["stars"] * 4).astype(int)):
        for skill in ("s_speed", "s_aim"):
            record = band.sort_values([skill, "playcount"], ascending=False).iloc[0].to_dict()
            if record["md5"] not in {r["md5"] for r in chosen}:
                chosen.append(record)
    chosen = chosen[:args.count]
    args.raw.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, record in enumerate(chosen):
        path = args.raw / f"{int(record['beatmap_id'])}.osu"
        if not path.exists() and args.fetch:
            data = download_osu(int(record["beatmap_id"]), record["md5"])
            if data is None:
                raise RuntimeError(f"Could not download verified map {record['beatmap_id']}; rerun to resume.")
            path.write_bytes(data)
        if not path.exists():
            raise FileNotFoundError(f"{path}: provide raw maps or use --fetch.")
        data = path.read_bytes()
        bm = parse_beatmap_bytes(data)
        for mods in CONFIGS:
            stable = configuration(bm, data, mods, "stable", record["status"])
            if stable["md5"] != record["md5"]:
                raise ValueError(f"{path}: checksum changed.")
            stable["beatmap_id"] = int(record["beatmap_id"])
            stable["beatmapset_id"] = int(record["beatmapset_id"])
            rows.append(stable)
            rows.append({**stable, "client": "lazer", "pp_curve": [
                {"accuracy": point["accuracy"], "pp": calculate(
                    data, CONFIGS[mods], "lazer", point["accuracy"])} for point in stable["pp_curve"]
            ]})
        print(f"{i + 1}/{len(chosen)} {record['stars']:.2f}* {record['title']}", flush=True)
    document = clean({"schema_version": SCHEMA_VERSION, "calculator_version": CALCULATOR_VERSION,
                      "coverage_maps": len(chosen), "rows": sorted(rows, key=lambda r: (r["md5"], r["client"], r["mods"]))})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(), mtime=0))
    print(f"Wrote {len(rows)} configurations to {args.output}", flush=True)


if __name__ == "__main__":
    main()
