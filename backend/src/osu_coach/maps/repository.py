"""Practice map pool file: load/save the bundled pool (``data/pool.json.gz``) and compute stats of .osu files.

The pool holds ~5,000 popular ranked osu!standard difficulties, 9 in 10 of them between 2★ and 8★
(most-played per 0.25★ step, from the 12,000 most-played ranked sets), each analysed with the same
pattern detector used on the player's replays plus osu!'s own difficulty model (rosu-pp).
Rebuild with ``tools/build_pool.py``. Selection logic lives in ``domain.map_recommendations``.
"""
from __future__ import annotations

import gzip
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from osu_coach.beatmaps.parser import parse_beatmap_bytes
from osu_coach.maps.domain import map_stats

POOL_PATH = Path(__file__).parent / "data" / "pool.json.gz"


def stats_from_osu(osu_bytes: bytes) -> dict | None:
    """Parse a .osu file and return its pool statistics (None for broken or unsuitable files)."""
    try:
        bm = parse_beatmap_bytes(osu_bytes)
    except Exception:  # noqa: BLE001 - broken files are skipped
        return None
    return map_stats(bm, osu_bytes)


@lru_cache(maxsize=2)
def _load_cached(path: str, mtime: float) -> pd.DataFrame:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        rows = json.load(fh)
    df = pd.DataFrame(rows)
    for col in df.columns:
        if df[col].dtype == object and col not in ("md5", "title", "artist", "version", "creator", "status",
                                                    "ranked_date"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_pool(path: Path | str | None = None) -> pd.DataFrame:
    p = Path(path or POOL_PATH)
    if not p.exists():
        return pd.DataFrame()
    return _load_cached(str(p), p.stat().st_mtime).copy()


def save_pool(rows: list[dict], path: Path | str = POOL_PATH) -> Path:
    def clean(v):
        if isinstance(v, (np.floating, float)):
            v = float(v)
            return None if math.isnan(v) or math.isinf(v) else round(v, 4)
        if isinstance(v, np.integer):
            return int(v)
        return v
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump([{k: clean(v) for k, v in r.items()} for r in rows], fh, separators=(",", ":"))
    return p
