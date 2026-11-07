"""The profile's records as pandas data frames, for the pages' table and chart code. Each frame is built once per
profile and shared, so callers must not change it in place."""

from __future__ import annotations

import dataclasses
import weakref
from collections.abc import Callable

import pandas as pd

from osu_coach.domain.player import Profile
from osu_coach.domain.player.measures.aim import ANGLE_BINS, DIST_LABELS
from osu_coach.domain.player.records import AimStats

STREAM_PROFILE_COLUMNS = [
    "bpm_bin", "objects", "miss_rate", "tap_miss_rate", "speed_aim_rate", "non300_rate", "ur", "ur_best", "ur_plays",
    "ur_pooled", "mean_err", "ur_trend", "weak",
]  # fmt: skip
FALL_CURVES = {
    "curves": ["group", "pos", "abs_err", "err", "miss_rate", "n"],
    "curve": ["pos", "abs_err", "err", "n"],
    "curves_bpm": ["group", "pos", "rel_err", "abs_err", "miss_rate", "n"],
}

_built: weakref.WeakKeyDictionary[Profile, dict[str, object]] = weakref.WeakKeyDictionary()


def _memo(p: Profile, name: str, make: Callable[[], object]):
    cache = _built.setdefault(p, {})
    if name not in cache:
        cache[name] = make()
    return cache[name]


def replays(p: Profile) -> pd.DataFrame:
    """One row per play: its meta, and its ``weight``."""

    def make():
        R = pd.DataFrame([m.to_dict() for m in p.replays])
        R["weight"] = list(p.weights)
        return R

    return _memo(p, "replays", make)


def objects(p: Profile) -> pd.DataFrame:
    """The played notes of every play (``replay_key``, weight ``w``) with the play's star rating, AR, rate and date."""

    def make():
        O = pd.DataFrame(p.notes.to_columns())
        O["played"] = True
        meta = {m.key: m for m in p.replays}
        keys = O["replay_key"]
        for column, field in (("stars", "stars"), ("map_ar", "ar"), ("rate", "rate"), ("date", "date")):
            O[column] = keys.map(lambda k, f=field: getattr(meta[k], f) if k in meta else None)
        return O

    return _memo(p, "objects", make)


def presses(p: Profile) -> pd.DataFrame:
    return _memo(p, "presses", lambda: pd.DataFrame(p.presses.to_columns()))


def _aim(rows: tuple[AimStats, ...], index: str, columns: list[str], categories=None) -> pd.DataFrame:
    frame = pd.DataFrame([{c: getattr(r, c) for c in columns} for r in rows], columns=columns)
    names = [r.name for r in rows]
    frame.index = (
        pd.CategoricalIndex(names, categories=categories, ordered=True, name=index)
        if categories
        else pd.Index(names, name=index)
    )
    return frame


def quadrants(p: Profile) -> pd.DataFrame:
    cols = ["objects", "misses", "miss_rate", "aim_misses", "aim_miss_rate", "mean_dx", "mean_dy", "along"]
    return _memo(p, "quadrants", lambda: _aim(p.quadrants, "quadrant", cols))


def grid(p: Profile) -> pd.DataFrame:
    return _memo(p, "grid", lambda: _aim(p.grid, "grid", ["objects", "misses", "miss_rate"]))


def directions(p: Profile) -> pd.DataFrame:
    cols = ["objects", "miss_rate", "aim_miss_rate", "along", "cross"]
    return _memo(p, "directions", lambda: _aim(p.directions, "direction", cols))


def angles(p: Profile) -> pd.DataFrame:
    labels = [label for _, _, label in ANGLE_BINS]
    return _memo(p, "angles", lambda: _aim(p.angles, "abin", ["objects", "miss_rate", "along"], labels))


def distances(p: Profile) -> pd.DataFrame:
    cols = ["objects", "miss_rate", "along", "aim_err"]
    return _memo(p, "distances", lambda: _aim(p.distances, "dbin", cols, list(DIST_LABELS)))


def stream_profile(p: Profile) -> pd.DataFrame:
    return _memo(
        p,
        "stream_profile",
        lambda: pd.DataFrame([dataclasses.asdict(r) for r in p.stream_profile], columns=STREAM_PROFILE_COLUMNS),
    )


def fall_behind(p: Profile) -> dict:
    """The fall-behind numbers with their curves as data frames."""
    fb = (
        {}
        if p.fall_behind is None
        else {f.name: getattr(p.fall_behind, f.name) for f in dataclasses.fields(p.fall_behind)}
    )
    return _memo(
        p,
        "fall_behind",
        lambda: {**fb, **{k: pd.DataFrame(fb.get(k) or [], columns=c) for k, c in FALL_CURVES.items()}},
    )


def ar_table(p: Profile) -> pd.DataFrame:
    """Weighted notes and miss rate per approach rate (0.5 steps)."""
    rows = p.reading.ar_table or []
    return _memo(
        p, "ar_table", lambda: pd.DataFrame(rows, columns=["ar_bin", "objects", "miss_rate"]).set_index("ar_bin")
    )
