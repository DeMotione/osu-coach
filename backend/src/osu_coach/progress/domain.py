"""Progress over time: period keys, per-period skill numbers and per-period play statistics.

Skill scores are measured against ONE miss model fitted on all of the player's replays — 50 = your all-time
average at that difficulty, more = fewer misses than usual in that period — so periods can be compared.
(The profile's own scores compare each skill with the player's level in the same replays, so they can't
show progress.)
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import pandas as pd

from osu_coach.profile.domain import (
    SKILL_LABELS,
    played_notes,
    compute_skills,
    build_profile,
    clean_pass,
    comfort_stars,
)

FEW_PLAYS = 5   # periods with fewer plays are shown, but marked as uncertain
PERIODS = ("month", "week", "day")


def utc(date) -> dt.datetime:
    if isinstance(date, str):
        date = dt.datetime.fromisoformat(date)
    return date.replace(tzinfo=dt.UTC) if date.tzinfo is None else date


def month_of(date, tz=None) -> str:
    """'YYYY-MM' of a replay date (stored in UTC) in ``tz`` — default: this computer's time zone."""
    return utc(date).astimezone(tz).strftime("%Y-%m")


def period_of(date, period: str = "month", tz=None) -> str:
    """The period a replay date falls in, in ``tz``: 'YYYY-MM' (month), 'YYYY-Www' (ISO week) or 'YYYY-MM-DD'."""
    d = utc(date).astimezone(tz)
    if period == "day":
        return d.strftime("%Y-%m-%d")
    if period == "week":
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    return d.strftime("%Y-%m")


def metric_key(period: str, key: str) -> str:
    """Months keep their plain key (older databases); days / weeks are 'day:…' / 'week:…'."""
    return key if period == "month" else f"{period}:{key}"


def full_combo(df: pd.DataFrame) -> pd.Series:
    full = df["map_max_combo"].isna() | (df["max_combo"] >= 0.99 * df["map_max_combo"])
    return df["completed"].astype(bool) & (df["nmiss"] == 0) & full


def period_metrics(analyses, tz=None) -> dict[str, list[tuple[str, float | None, int]] | None]:
    """Skill scores and stream speed per period key (see :func:`metric_key`) as (name, value, n) rows.
    ``None`` for a period with too few plays (stale numbers should go); periods that can't be
    modelled are left out. Empty if the whole history can't be modelled."""
    if not analyses:
        return {}
    try:
        full = build_profile(analyses, weighted=False)   # periods stay comparable: no level weighting
    except Exception:  # noqa: BLE001 - too little data for a model
        return {}
    threshold = full.reading.get("dense_threshold")
    groups = defaultdict(list)
    for a in analyses:
        for period in PERIODS:      # months, ISO weeks and days, each kept under its own key
            groups[metric_key(period, period_of(a.meta["date"], period, tz))].append(a)
    out: dict[str, list[tuple[str, float | None, int]] | None] = {}
    for key, group in groups.items():
        if len(group) < FEW_PLAYS:   # a play or two say little about a period's skill
            out[key] = None
            continue
        try:
            mp = build_profile(group, weighted=False)
            reading = dict(mp.reading)
            if threshold is not None:
                reading["dense_threshold"] = threshold
            skills = compute_skills(played_notes(mp.objects), full.model, mp.tapping, mp.sliders, reading, mp.consistency,
                             level=full.levels.get("level_stars"),   # one stamina yardstick for all periods
                             presses=mp.presses)
        except Exception:  # noqa: BLE001 - a period with too little data keeps no skill numbers
            continue
        rows = [(f"skill_{k}", v.get("score"), int(v.get("n") or 0)) for k, v in skills.items()]
        rows += [("stream_bpm", mp.tapping.get("comfort_bpm"), int(mp.tapping.get("n") or 0)),
                 ("ur_single", mp.tapping.get("ur_single"), 0),
                 ("aim_err", mp.aim.get("aim_err_median"), 0)]
        out[key] = rows
    return out


def summarize_periods(df: pd.DataFrame, metrics: pd.DataFrame, period: str = "month", since: dt.date | None = None,
                      until: dt.date | None = None, tz=None) -> pd.DataFrame:
    """One row per period with plays: counts, star rating, accuracy, skills (``skill_<name>``) etc.
    ``df``: the player's saved plays; ``metrics``: their month_metrics rows (month, name, value).
    Only plays from ``since`` to ``until`` (dates in ``tz``, both included)."""
    if df.empty:
        return pd.DataFrame(columns=["month", "plays"])
    local = pd.to_datetime(df["played_at"], utc=True, format="ISO8601").dt.tz_convert(
        tz or dt.datetime.now().astimezone().tzinfo)
    if since is not None:
        df, local = df[local.dt.date >= since], local[local.dt.date >= since]
    if until is not None:
        df, local = df[local.dt.date <= until], local[local.dt.date <= until]
    if df.empty:
        return pd.DataFrame(columns=["month", "plays"])
    if period != "month":
        df = df.assign(month=[period_of(t.to_pydatetime(), period, tz) for t in local])
    df["completed"] = df["completed"].fillna(0).astype(bool)
    first = df.groupby("beatmap_md5")["month"].min()
    g = df.groupby("month")
    out = pd.DataFrame({"plays": g.size(), "maps": g["beatmap_md5"].nunique()})
    out["new_maps"] = first.value_counts().reindex(out.index, fill_value=0)
    out["minutes"] = g["length_s"].sum() / 60
    out["notes"] = g["n_played"].sum()
    out["avg_stars"] = g.apply(lambda d: (d["stars"] * d["n_objects"]).sum() / max(d["n_objects"].sum(), 1),
                               include_groups=False)
    out["comfort_stars"] = g.apply(comfort_stars, include_groups=False)
    out["max_stars_passed"] = df[clean_pass(df)].groupby("month")["stars"].max()
    out["max_stars_fc"] = df[full_combo(df)].groupby("month")["stars"].max()
    out["accuracy"] = g["accuracy"].mean()
    out["misses_per_100"] = g["head_misses"].sum() / g["n_played"].sum().clip(lower=1) * 100
    out["ur"] = g["ur"].median()
    mm = metrics
    if period != "month":
        prefix = f"{period}:"
        mm = mm[mm["month"].str.startswith(prefix)].assign(month=lambda d: d["month"].str[len(prefix):])
    else:
        mm = mm[~mm["month"].str.contains(":")]
    for name in [f"skill_{k}" for k in SKILL_LABELS] + ["stream_bpm", "ur_single", "aim_err"]:
        vals = mm[mm["name"] == name].set_index("month")["value"]
        out[name] = vals.reindex(out.index).astype(float)
    out["few_plays"] = out["plays"] < FEW_PLAYS
    return out.sort_index().reset_index().rename(columns={"index": "month"})


def mark_full_combos(df: pd.DataFrame) -> pd.DataFrame:
    """Plays with ``completed`` as bool and an ``fc`` column."""
    df["completed"] = df["completed"].fillna(0).astype(bool)
    df["fc"] = full_combo(df)
    return df
