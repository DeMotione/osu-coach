"""Verified map bytes and versioned per-map configuration statistics cache."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

from osu_coach.domain.beatmaps.features import features_at_rate, object_features
from osu_coach.domain.beatmaps.models import PlayableBeatmap
from osu_coach.domain.maps.skillset import Screened, in_star_window
from osu_coach.domain.maps.suggestions import pattern_stats
from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.player.algorithm import MODEL_VERSION
from osu_coach.domain.replays.configuration import Configuration
from osu_coach.infra.beatmaps import difficulty
from osu_coach.infra.beatmaps.parser import parse_beatmap_bytes
from osu_coach.infra.beatmaps.performance import CALCULATOR_VERSION
from osu_coach.infra.beatmaps.sources import download_osu
from osu_coach.infra.map_stats import finish_stats

CACHE_VERSION = 1
# In a map's file, next to the rows by configuration: the exact stars of the configurations whose other statistics
# no search has needed yet (null: unknown). No configuration has this key, and files without it read as before.
STARS = "stars"


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


def _screen(stars, targets: tuple[float, ...]) -> str | None:
    """Why no goal can rank a configuration of these exact stars ("no_stars", "outside"); None: one can."""
    stars = finite_or_none(stars)
    if stars is None or stars <= 0:
        return "no_stars"
    return None if any(in_star_window(stars, target) for target in targets) else "outside"


def variant_rows(
    cache_dir: Path,
    raw: bytes,
    configs: tuple[Configuration, ...],
    on_unavailable=None,
    targets: tuple[float, ...] | None = None,
):
    """Yield exact rows, saving completed configurations after each map.

    With ``targets`` (the goals' target stars) only the configurations a goal can rank get their rows: the exact
    stars of a configuration are calculated first, and the other statistics, by far most of the work, only inside a
    goal's star window. The rest of the map's configurations are counted in one closing :class:`Screened`; their
    stars are kept under ``STARS`` in the map's file, for the next search to finish if its goals want them.
    """
    md5 = hashlib.md5(raw).hexdigest()
    directory = cache_dir / "recommendations" / "variants"
    filename = f"{md5}-r{CACHE_VERSION}-m{MODEL_VERSION}-rosu{CALCULATOR_VERSION}.json.gz"
    path = directory / filename
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            cached = json.load(fh)
        stars_only = cached.pop(STARS, {})
    except (OSError, ValueError):
        cached, stars_only = {}, {}
    keys = [config.key for config in configs]
    missing = [
        (config, key)
        for config, key in zip(configs, keys)
        if key not in cached and (targets is None or key not in stars_only or _screen(stars_only[key], targets) is None)
    ]
    bm = parse_beatmap_bytes(raw) if missing else None
    parsed_map = difficulty.parse_map(raw) if bm is not None and bm.mode == 0 and len(bm.objects) >= 30 else None
    # what leaves pattern_stats without statistics, known before any is made
    usable = parsed_map is not None and any(o.kind != "spinner" for o in bm.objects)
    templates = {}
    patterns = {}
    for config, key in missing:
        try:
            if not usable:
                stats = None
            else:
                extra = {}
                if targets is not None:
                    attributes = difficulty.attributes(
                        raw, config.mods, rate=config.rate, lazer=config.client == "lazer", parsed_map=parsed_map
                    )
                    stars = attributes.get("stars", math.nan)
                    # 0 stars: not available at all, which the statistics below say as before
                    if stars and _screen(stars, targets) is not None:
                        stars_only[key] = finite_or_none(stars)
                        continue
                    extra = {"attributes": attributes}
                geometry = config.hr
                if geometry not in templates:
                    templates[geometry] = object_features(PlayableBeatmap(bm, 16 if geometry else 0, rate=1.0))
                pattern_key = (geometry, config.rate)
                if pattern_key not in patterns:
                    features = features_at_rate(templates[geometry], config.rate)
                    patterns[pattern_key] = pattern_stats(bm, raw, config.mods, config.rate, features)
                pattern = patterns[pattern_key]
                stats = (
                    finish_stats(
                        pattern,
                        raw,
                        config.mods,
                        config.rate,
                        lazer=config.client == "lazer",
                        parsed_map=parsed_map,
                        **extra,
                    )
                    if pattern is not None
                    else None
                )
        except (OSError, ValueError):
            stats = None
        cached[key] = _clean(stats) if stats and stats.get("stars") else None
        stars_only.pop(key, None)
    if missing:
        directory.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        with gzip.open(temp, "wt", encoding="utf-8") as fh:
            json.dump(
                {**cached, STARS: stars_only} if stars_only else cached, fh, separators=(",", ":"), allow_nan=False
            )
        os.replace(temp, path)
    if on_unavailable is not None:
        on_unavailable(sum(not cached.get(key) and key not in stars_only for key in keys))
    screened = {"outside": 0, "no_stars": 0}
    for config, key in zip(configs, keys):
        row = cached.get(key)
        if targets is not None and (row or key in stars_only):
            reason = _screen(row.get("stars") if row else stars_only[key], targets)
            if reason is not None:
                screened[reason] += 1
                continue
        if row:
            yield {
                **row,
                "configuration_id": key,
                "mods": "".join(part for part, on in (("HD", config.hd), ("HR", config.hr), ("DT", config.dt)) if on)
                or "NM",
                "rate": config.rate,
            }
    if any(screened.values()):
        yield Screened(md5, **screened)


def calculate_variants(
    cache_dir: Path, raw: bytes, configs: tuple[Configuration, ...], targets: tuple[float, ...] | None = None
) -> tuple[list[dict | Screened], int]:
    """Calculate one map in a worker process; that worker owns its cache file."""
    unavailable: list[int] = []
    rows = list(variant_rows(cache_dir, raw, configs, on_unavailable=unavailable.append, targets=targets))
    return rows, unavailable[0]
