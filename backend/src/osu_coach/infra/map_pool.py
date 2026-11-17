"""Practice map pool file: load/save the bundled pool (``data/pool.json.gz``) and compute stats of .osu files.

The pool holds ~50,000 ranked osu!standard difficulties: every one of 6★ and more, and the most played under 5★
and at 5-6★ in equal numbers (``tools/fetch_pool_raw.py``), each analysed with the same pattern detector used on
the player's replays plus osu!'s own difficulty model (rosu-pp).
Rebuild with ``tools/build_pool.py``, then its variant table (the maps with mods: ``osu_coach.infra.variant_table``)
with ``tools/build_variant_table.py``. Map statistics: ``osu_coach.domain.maps.suggestions``; playlists: ``osu_coach.features.maps.playlists``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import threading
from pathlib import Path

import numpy as np
import pandas as pd

from osu_coach.domain.maps.variants import pool_features
from osu_coach.infra.beatmaps.parser import parse_beatmap_bytes
from osu_coach.infra.code_fingerprint import fingerprint
from osu_coach.infra.map_stats import map_stats

POOL_PATH = Path(__file__).parent / "data" / "pool.json.gz"


def stats_from_osu(osu_bytes: bytes) -> dict | None:
    """Parse a .osu file and return its pool statistics (None for broken or unsuitable files)."""
    try:
        bm = parse_beatmap_bytes(osu_bytes)
    except Exception:  # noqa: BLE001 - broken files are skipped
        return None
    return map_stats(bm, osu_bytes)


TEXT_COLUMNS = ("md5", "title", "artist", "version", "creator", "status", "ranked_date")
PARSED_DIR = "pool"  # in the data folder: the pool as read, so a start doesn't parse the whole file again


def _parse(path: str) -> pd.DataFrame:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        rows = json.load(fh)
    df = pd.DataFrame(rows)
    for col in df.columns:
        if df[col].dtype == object and col not in TEXT_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # each map's skill composites, once, instead of in every recommendation (see skillset.PRECOMPUTED)
    cols = {c: df[c].to_numpy(dtype=float) for c in df.columns if c not in TEXT_COLUMNS and df[c].dtype.kind in "fiub"}
    return df.assign(**pool_features(cols, len(df))) if len(df) else df


_READ: dict[tuple, pd.DataFrame] = {}  # the pools read by this process (by file, time and size), at most two
_READ_LOCK = threading.Lock()


def _stored(path: str, mtime_ns: int, size: int, cache_dir: str | None) -> pd.DataFrame:
    """The pool, from the data folder's copy as read last time when it is of this file and this code (reading the
    50k maps' JSON was seconds of every start), else parsed and the copy written."""
    if cache_dir is None:
        return _parse(path)
    tag = hashlib.sha256(f"{path}|{mtime_ns}|{size}|{fingerprint('osu_coach.domain')}".encode()).hexdigest()[:20]
    folder = Path(cache_dir) / PARSED_DIR
    stored = folder / f"{tag}.pkl"
    try:
        df = pd.read_pickle(stored)
        if isinstance(df, pd.DataFrame):
            return df
    except Exception:  # noqa: BLE001 - missing, of another pandas or broken: parsed again
        pass
    df = _parse(path)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.pkl"):  # copies of an earlier pool or code
            old.unlink(missing_ok=True)
        temp = stored.with_suffix(".tmp")
        df.to_pickle(temp)
        temp.replace(stored)
    except OSError:  # a copy only saves time
        pass
    return df


def load_pool(path: Path | str | None = None, cache_dir: Path | str | None = None) -> pd.DataFrame:
    """The pool; ``cache_dir``: the data folder, where the pool is kept as read for the next start."""
    p = Path(path or POOL_PATH)
    if not p.exists():
        return pd.DataFrame()
    st = p.stat()
    key = (str(p), st.st_mtime_ns, st.st_size)
    with _READ_LOCK:
        df = _READ.get(key)
        if df is None:
            df = _stored(*key, str(cache_dir) if cache_dir else None)
            while len(_READ) >= 2:
                _READ.pop(next(iter(_READ)))
            _READ[key] = df
    return df.copy()


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
