"""Verified target map cache, independent of temporary job objects."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

from osu_coach.app.errors import ApiError
from osu_coach.beatmaps.parser import parse_beatmap_bytes, read_metadata
from osu_coach.beatmaps.performance import CALCULATOR_VERSION
from osu_coach.beatmaps.sources import download_osu
from osu_coach.maps.goal_pool import configuration


def target_bytes(cache_dir: Path, beatmap_id: int, libraries: list, online: bool, pool: list[dict]) -> bytes:
    known = next((r["md5"] for r in pool if r["beatmap_id"] == beatmap_id), None)
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
            "This difficulty is not cached. Allow downloading its beatmap or choose a local replay.",
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


def target_configuration(cache_dir: Path, raw: bytes, mods: str, client: str) -> dict:
    md5 = hashlib.md5(raw).hexdigest()
    directory = cache_dir / "play-goals" / "configurations"
    key = f"{md5}-{mods}-{client}-{CALCULATOR_VERSION}-v1"
    path = directory / f"{key}.json"
    if path.is_file():
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ApiError(
                422, "goal_cache_invalid", "The cached target configuration is unreadable. Remove it and assess again."
            ) from exc
        if not isinstance(row, dict) or row.get("md5") != md5 or row.get("mods") != mods or row.get("client") != client:
            raise ApiError(422, "goal_cache_invalid", "The cached target configuration has an invalid identity.")
        return row
    row = configuration(parse_beatmap_bytes(raw), raw, mods, client)
    row = {k: None if isinstance(v, float) and not math.isfinite(v) else v for k, v in row.items()}
    directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(row, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)
    return row
