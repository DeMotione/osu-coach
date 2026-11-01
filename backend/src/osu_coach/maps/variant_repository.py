"""Verified map bytes and versioned per-map configuration statistics cache."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

from osu_coach.beatmaps.parser import parse_beatmap_bytes
from osu_coach.beatmaps.performance import CALCULATOR_VERSION
from osu_coach.beatmaps.sources import download_osu
from osu_coach.maps.domain import map_stats
from osu_coach.profile.domain.algorithm import MODEL_VERSION
from osu_coach.replays.configuration import Configuration

CACHE_VERSION = 1


def verified_bytes(cache_dir: Path, row: dict, libraries: list) -> bytes | None:
    md5 = str(row.get("md5") or "")
    local = [Path(lib.maps[md5]) for lib in libraries if md5 in lib.maps]
    local.append(cache_dir / "play-goals" / "maps" / f"{row.get('beatmap_id')}.osu")
    own = cache_dir / "recommendations" / "maps" / f"{md5}.osu"
    local.append(own)
    for path in local:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if hashlib.md5(data).hexdigest() == md5:
            return data
    beatmap_id = row.get("beatmap_id")
    if not isinstance(beatmap_id, (int, float)) or not math.isfinite(beatmap_id) or beatmap_id <= 0:
        return None
    data = download_osu(int(beatmap_id), expected_md5=md5)
    if data is None:
        return None
    own.parent.mkdir(parents=True, exist_ok=True)
    temp = own.with_suffix(".tmp")
    temp.write_bytes(data)
    os.replace(temp, own)
    return data


def _clean(value):
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def variant_rows(cache_dir: Path, raw: bytes, configs: tuple[Configuration, ...], on_unavailable=None):
    """Yield exact rows, saving completed configurations after each map."""
    md5 = hashlib.md5(raw).hexdigest()
    directory = cache_dir / "recommendations" / "variants"
    filename = f"{md5}-r{CACHE_VERSION}-m{MODEL_VERSION}-rosu{CALCULATOR_VERSION}.json.gz"
    path = directory / filename
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            cached = json.load(fh)
    except (OSError, ValueError):
        cached = {}
    missing = [config for config in configs if config.key not in cached]
    bm = parse_beatmap_bytes(raw) if missing else None
    for config in missing:
        try:
            stats = map_stats(bm, raw, config.mods, config.rate, lazer=config.client == "lazer")
        except (OSError, ValueError):
            stats = None
        cached[config.key] = _clean(stats) if stats and stats.get("stars") else None
    if missing:
        directory.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        with gzip.open(temp, "wt", encoding="utf-8") as fh:
            json.dump(cached, fh, separators=(",", ":"), allow_nan=False)
        os.replace(temp, path)
    if on_unavailable is not None:
        on_unavailable(sum(not cached.get(config.key) for config in configs))
    for config in configs:
        row = cached.get(config.key)
        if row:
            yield {
                **row,
                "configuration_id": config.key,
                "mods": "".join(part for part, on in (("HD", config.hd), ("HR", config.hr), ("DT", config.dt)) if on)
                or "NM",
                "rate": config.rate,
            }
