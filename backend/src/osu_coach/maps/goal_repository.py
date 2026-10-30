"""Versioned offline configuration data; old practice pool stays unchanged."""

from __future__ import annotations

import gzip
import json
from functools import lru_cache
from pathlib import Path

from osu_coach.beatmaps.performance import CALCULATOR_VERSION

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
