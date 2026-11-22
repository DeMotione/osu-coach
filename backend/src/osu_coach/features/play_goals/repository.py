"""The play goals' data: the target map (from a replay's map, a library or a download) and its row in the goal's
configuration, both cached in the data folder. The maps to recommend come from the pool's tables
(:mod:`osu_coach.features.play_goals.candidates`)."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

from osu_coach.common.errors import ApiError
from osu_coach.domain.beatmaps.models import Beatmap
from osu_coach.domain.play_goals.pool import CONFIGS, config_key, standard_rate, valid_rate
from osu_coach.infra.beatmaps.parser import parse_beatmap_bytes, read_metadata
from osu_coach.infra.beatmaps.performance import CALCULATOR_VERSION
from osu_coach.infra.beatmaps.sources import download_osu
from osu_coach.infra.map_stats import map_stats

ROW_VERSION = 2  # 2: with the configuration's speed, without the pp


def configuration(
    bm: Beatmap, osu_bytes: bytes, mods: str, client: str, rate: float | None = None, status: str = "unknown"
) -> dict:
    """The map's row in the combination ``mods`` at ``rate`` (default: the combination's own speed)."""
    rate = standard_rate(mods) if rate is None else rate
    if mods not in CONFIGS or client not in ("stable", "lazer") or not valid_rate(mods, rate):
        raise ValueError("Unsupported play-goal configuration.")
    stats = map_stats(bm, osu_bytes, CONFIGS[mods], rate)
    if not stats or not stats.get("stars"):
        raise ValueError("The map has no supported difficulty or too few playable objects.")
    return {
        **stats,
        "config": config_key(mods, rate),
        "mods": mods,
        "rate": rate,
        "client": client,
        "status": status,
        "length_s": stats["drain_length"],
    }


def target_bytes(cache_dir: Path, beatmap_id: int, libraries: list, online: bool, known: str | None = None) -> bytes:
    """The .osu file of a difficulty: from a library, the data folder or a download. ``known``: its MD5 when the
    pool has it (a file must then be that one)."""
    if known:
        for library in libraries:
            path = library.maps.get(known)
            if path and Path(path).is_file():
                data = Path(path).read_bytes()
                if hashlib.md5(data).hexdigest() == known:
                    return data
    else:
        for library in libraries:
            for path in dict.fromkeys(library.maps.values()):
                metadata = read_metadata(path)
                if str(metadata.get("BeatmapID")) == str(beatmap_id):
                    return Path(path).read_bytes()
    directory = cache_dir / "play-goals" / "maps"
    path = directory / f"{beatmap_id}.osu"
    if path.is_file():
        data = path.read_bytes()
        if known is None or hashlib.md5(data).hexdigest() == known:
            return data
    if not online:
        raise ApiError(
            409,
            "goal_map_offline",
            "This difficulty is not cached. Turn on downloading missing beatmaps in Settings, or choose a local "
            "replay.",
        )
    data = download_osu(beatmap_id, expected_md5=known)
    if data is None:
        raise ApiError(
            422,
            "goal_map_unavailable",
            "Could not download a verified beatmap. Check the link and your connection.",
        )
    directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)
    return data


def target_configuration(cache_dir: Path, raw: bytes, mods: str, client: str, rate: float | None = None) -> dict:
    """The target's row in the combination at ``rate`` (default: its own speed), cached by map, configuration,
    client and calculator."""
    md5 = hashlib.md5(raw).hexdigest()
    config = config_key(mods, rate)
    directory = cache_dir / "play-goals" / "configurations"
    key = f"{md5}-{config.replace(' ', '-')}-{client}-{CALCULATOR_VERSION}-v{ROW_VERSION}"
    path = directory / f"{key}.json"
    if path.is_file():
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ApiError(
                422, "goal_cache_invalid", "The cached target configuration is unreadable. Remove it and assess again."
            ) from exc
        if (
            not isinstance(row, dict)
            or row.get("md5") != md5
            or row.get("config") != config
            or row.get("client") != client
        ):
            raise ApiError(422, "goal_cache_invalid", "The cached target configuration has an invalid identity.")
        return row
    row = configuration(parse_beatmap_bytes(raw), raw, mods, client, rate)
    row = {k: None if isinstance(v, float) and not math.isfinite(v) else v for k, v in row.items()}
    directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(row, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)
    return row
