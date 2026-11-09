"""Synthetic analysis tables for rating tests: the few columns a test cares about, the rest filled with neutral values."""

from __future__ import annotations

import dataclasses
import datetime as dt
import math

import numpy as np
import pandas as pd

from osu_coach.domain.analysis.notes import HitObjects
from osu_coach.domain.player.algorithm import timing_evidence_eligible
from osu_coach.domain.player.engines.comfort import skill_values as sv
from osu_coach.domain.player.engines.comfort.ratings import combine_ratings, rating_inputs
from osu_coach.domain.player.profile import FallBehind
from osu_coach.domain.replays.configuration import from_meta

# a hit single circle that tests no skill in particular
DEFAULTS = {
    "kind": "circle",
    "played": True,
    "completed": True,
    "head_hit": True,
    "head_result": 300,
    "miss_reason": None,
    "pattern": "single",
    "spaced_stream": False,
    "run_id": -1,
    "run_len": 1,
    "run_pos": 0,
    "stream_bpm": np.nan,
    "velocity_real": np.nan,
    "radius": 32.0,
    "rate": 1.0,
    "map_ar": 9.0,
    "accuracy": 0.95,
    "broke": False,
}


def rate(rows: list[dict], theta: float = 6.0, **meta) -> dict[str, dict]:
    """:func:`ratings` of these object rows at comfort ``theta``. Each ``replay_key`` is one play of the map in its
    ``map_md5`` column (the key itself when there is none); ``meta`` overrides every play's meta (mods, accuracy, ...)."""
    O = pd.DataFrame(rows)
    for column, value in DEFAULTS.items():
        if column not in O:
            O[column] = value
    if "time" not in O:  # notes 100 ms apart within a play
        O["time"] = O.groupby("replay_key").cumcount() * 100.0
    if "stars" not in O:
        O["stars"] = theta
    keys = list(dict.fromkeys(O["replay_key"]))
    md5 = O.groupby("replay_key")["map_md5"].first() if "map_md5" in O else pd.Series(keys, index=keys)
    metas = pd.DataFrame(
        {
            "key": keys,
            "beatmap_md5": [str(md5[k]) for k in keys],
            "mods": 0,
            "rate": 1.0,
            "client": "stable",
            "accuracy": 0.95,
            "od": 8.0,
            "stars": theta,
            "completed": True,
            "head_misses": 0,
            "n_objects": [int((O["replay_key"] == k).sum()) for k in keys],
            "date": "2026-10-01T12:00:00+00:00",
        }
    )
    for column, value in meta.items():
        metas[column] = value
    return ratings(O, metas, theta)


def _first(d: pd.DataFrame, column: str, default):
    if column not in d:
        return default
    value = d[column].iloc[0]
    return default if value is None or (isinstance(value, float) and math.isnan(value)) else value


def plays(O: pd.DataFrame, maps: dict | None = None) -> list[tuple[HitObjects, sv.PlayContext]]:
    """The played notes of every ``replay_key`` of these rows, with the play's context read from its first row."""
    if "played" in O:
        O = O[O["played"].astype(bool)]
    if "kind" in O:
        O = O[O["kind"] != "spinner"]
    keys = O["replay_key"].astype(str) if "replay_key" in O else pd.Series("all", index=O.index)
    out = []
    for key, d in O.groupby(keys, sort=False):
        d = d.reset_index(drop=True)
        rate = float(_first(d, "rate", 1.0))
        map_key = (maps or {}).get(key) or (
            f"{_first(d, 'map_md5', key)}@{format(rate, '.17g')}" if "map_md5" in d else key
        )
        ctx = sv.PlayContext(
            key=key,
            map=str(map_key),
            completed=bool(_first(d, "completed", True)),
            combo_ratio=float(_first(d, "combo_ratio", math.nan)),
            ar=float(_first(d, "map_ar", math.nan)),
            accuracy=float(_first(d, "accuracy", math.nan)),
            stars=float(_first(d, "stars", math.nan)),
            rate=rate,
            hidden=bool(_first(d, "hidden", False)),
            hidden_custom=bool(_first(d, "hidden_custom", False)),
            flashlight=bool(_first(d, "flashlight", False)),
        )
        out.append((HitObjects.from_columns(d), ctx))
    return out


def _frame(rows: list[dict], cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=cols)


def aim_values(O: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"replay_key": c.key, "map": c.map, **dataclasses.asdict(v)} for n, c in plays(O) if (v := sv.aim_value(n, c))
    ]
    return _frame(rows, ["replay_key", "map", "intensity", "combo", "value", "jumps"])


def speed_values(O: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"replay_key": c.key, "map": c.map, **dataclasses.asdict(v)} for n, c in plays(O) if (v := sv.speed_value(n))
    ]
    return _frame(rows, ["replay_key", "map", "bpm", "runs", "clean"])


def reading_values(O: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"replay_key": c.key, "map": c.map, **dataclasses.asdict(v)}
        for n, c in plays(O)
        if (v := sv.reading_value(n, c))
    ]
    return _frame(
        rows,
        ["replay_key", "map", "ar", "nps", "ar_factor", "bpm_changes", "bpm_hit", "bpm_factor", "accuracy", "value"],
    )


def tempo_curve(O: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"replay_key": c.key, "map": c.map, "window": w, "bpm": bpm}
        for n, c in plays(O)
        for w, bpm in sv.tempo_curve(n, c.rate).items()
    ]
    return _frame(rows, ["replay_key", "map", "window", "bpm"])


def slider_difficulty(S: pd.DataFrame) -> pd.Series:
    return pd.Series(sv.slider_difficulty(HitObjects.from_columns(S)), index=S.index)


def ratings(O: pd.DataFrame, metas: pd.DataFrame, theta: float | None) -> dict[str, dict]:
    """The ratings of these note rows (``replay_key`` naming the play; ``metas``: one row per play)."""
    if not isinstance(metas, pd.DataFrame):
        metas = pd.DataFrame([m.to_dict() for m in metas])
    if O.empty or theta is None or not math.isfinite(theta):
        return combine_ratings([], records(metas), theta)
    unique = metas.drop_duplicates("key", keep="last").set_index("key")
    maps = {k: from_meta(row.to_dict()).key for k, row in unique.iterrows()}
    inputs = []
    for notes, ctx in plays(O, maps):
        ctx = dataclasses.replace(ctx, map=maps.get(ctx.key, "unknown"))
        meta = unique.loc[ctx.key] if ctx.key in unique.index else {}
        eligible = timing_evidence_eligible(int(meta.get("mods") or 0), meta.get("accuracy"))
        inputs.append(rating_inputs(notes, ctx, eligible, float(meta.get("od", math.nan))))
    return combine_ratings(inputs, records(metas), theta)


# ---- the per-note statistics of synthetic note rows, through the per-play summaries the profile adds up
def weighted(O: pd.DataFrame, summary) -> list[tuple]:
    """``(summary(notes), weight)`` of every play of these rows (weight: its ``w`` column, else 1)."""
    out = []
    for notes, ctx in plays(O):
        rows = O[O["replay_key"].astype(str) == ctx.key] if "replay_key" in O else O
        out.append((summary(notes), float(_first(rows, "w", 1.0))))
    return out


def quadrant_stats(O: pd.DataFrame):
    from osu_coach.domain.player.measures.aim import aim_summary, quadrant_table

    return quadrant_table(weighted(O, aim_summary))


def aim_regression(O: pd.DataFrame):
    from osu_coach.domain.player.measures.aim import jump_summary, regression
    from osu_coach.domain.player.summary import miss_causes

    return regression(weighted(O, lambda n: jump_summary(n, miss_causes(n))))


def stream_speed_profile(O: pd.DataFrame, raw: bool = False):
    from osu_coach.common.frames import STREAM_PROFILE_COLUMNS
    from osu_coach.domain.player.measures.streams import speed_profile, stream_summary

    rows = speed_profile(weighted(O, stream_summary))
    if raw:
        return rows
    return pd.DataFrame([dataclasses.asdict(r) for r in rows], columns=STREAM_PROFILE_COLUMNS)


def stream_limits(prof: pd.DataFrame, base_ur: float) -> dict:
    from osu_coach.domain.player.measures.streams import stream_limits as limits
    from osu_coach.domain.player.records import SpeedRow

    return limits([SpeedRow(**r) for r in prof.to_dict("records")], base_ur)


def stream_fall_behind(O: pd.DataFrame, reach_bpm: float | None = None, raw: bool = False) -> dict:
    """The fall-behind numbers with their curves as data frames (``raw``: as the profile keeps them, lists of rows)."""
    from osu_coach.domain.player.measures.streams import fall_behind, stream_summary

    fb = fall_behind(weighted(O, stream_summary), reach_bpm)
    return FallBehind(**fb) if raw else fall_behind_frames(fb)


def fall_behind_frames(fb: dict) -> dict:
    """The fall-behind numbers with their curves as data frames (what the pages read)."""
    from osu_coach.common.frames import FALL_CURVES

    return {**fb, **{k: pd.DataFrame(fb.get(k) or [], columns=c) for k, c in FALL_CURVES.items()}}


def miss_causes(O: pd.DataFrame) -> list:
    from osu_coach.domain.player import summary

    return list(summary.miss_causes(HitObjects.from_columns(O)))


def fit_miss_model(df: pd.DataFrame):
    from osu_coach.domain.player.measures import miss_notes

    return miss_notes.fit_miss_model(
        df["local_eq"].to_numpy(float), (~df["head_hit"].astype(bool)).to_numpy(), np.ones(len(df))
    )


def miss_chain_ratio(df: pd.DataFrame) -> float:
    from osu_coach.domain.player.measures import miss_notes
    from osu_coach.domain.player.summary import fast_pattern
    from osu_coach.domain.player.summary import miss_causes as causes

    parts = []
    for _, d in df.groupby("replay_key", sort=False) if "replay_key" in df else [("all", df)]:
        notes = HitObjects.from_columns(d.assign(aim_eq=d["local_eq"]).reset_index(drop=True))
        parts.append(miss_notes.miss_notes(notes, math.nan, math.nan, False, causes(notes), fast_pattern(notes)))
    return miss_notes.miss_chain_ratio(miss_notes.MissNotes.concat(parts))


def records(metas) -> list:
    """Replay metas from a data frame of meta rows (or a list of dicts); NaN and None fields keep their defaults."""
    from osu_coach.domain.analysis.models import ReplayMeta

    rows = metas.to_dict("records") if isinstance(metas, pd.DataFrame) else list(metas or [])
    out = []
    for r in rows:
        clean = {k: v for k, v in r.items() if not (isinstance(v, float) and math.isnan(v))}
        if isinstance(clean.get("date"), str):
            clean["date"] = dt.datetime.fromisoformat(clean["date"])
        if hasattr(clean.get("date"), "to_pydatetime"):
            clean["date"] = clean["date"].to_pydatetime()
        out.append(ReplayMeta.from_dict(clean))
    return out
