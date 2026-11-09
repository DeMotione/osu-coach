"""The play goals' data: the bundled goal pool (versioned offline map data) and the cached target maps and their
configurations, independent of temporary job objects."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
from functools import lru_cache
from pathlib import Path

from osu_coach.common.errors import ApiError
from osu_coach.domain.beatmaps.models import Beatmap
from osu_coach.domain.play_goals.pool import ACCURACIES, CONFIGS
from osu_coach.infra.beatmaps.parser import parse_beatmap_bytes, read_metadata
from osu_coach.infra.beatmaps.performance import CALCULATOR_VERSION, calculate
from osu_coach.infra.beatmaps.sources import download_osu
from osu_coach.infra.map_stats import map_stats

GOAL_POOL = Path(__file__).parent / "data" / "goals_pool.json.gz"
SCHEMA_VERSION = 1


@lru_cache(maxsize=2)
def _load(path: str, mtime: int) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as file:
        document = json.load(file)
    if document["schema_version"] != SCHEMA_VERSION or document["calculator_version"] != CALCULATOR_VERSION:
        raise ValueError("The Play Goals map data must be rebuilt for this calculator version.")
    return document["rows"]


def load_goal_pool(path: Path = GOAL_POOL) -> list[dict]:
    if not path.is_file():
        raise ValueError("The bundled Play Goals map data is missing.")
    return _load(str(path), path.stat().st_mtime_ns)


def configuration(bm: Beatmap, osu_bytes: bytes, mods: str, client: str, status: str = "unknown") -> dict:
    if mods not in CONFIGS or client not in ("stable", "lazer"):
        raise ValueError("Unsupported play-goal configuration.")
    stats = map_stats(bm, osu_bytes, CONFIGS[mods])
    if not stats or not stats.get("stars"):
        raise ValueError("The map has no supported difficulty or too few playable objects.")
    return {
        **stats,
        "mods": mods,
        "client": client,
        "status": status,
        "length_s": stats["drain_length"],
        "pp_curve": [{"accuracy": acc, "pp": calculate(osu_bytes, CONFIGS[mods], client, acc)} for acc in ACCURACIES],
    }


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
