"""Progress over time: period keys, per-period skill numbers and per-period play statistics.

Skill scores are the Overview's skill ratings (``experimental_skills``: 50 = expected performance at a comfort
level), each period's measured against ONE reference — the comfort level of all of the player's replays, the
one the Overview uses — so periods can be compared: playing better than that level expects shows as a rise.
(Rating each period at its own comfort level would put every period near 50.)

Besides months, weeks and days, every day with plays also gets a *rolling* score: rated over the plays of the
``ROLLING_DAYS`` days up to it. One day's plays are few and swing a lot; the goals chart follows this steadier line,
whose last point is close to the score of all plays a goal starts from.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

import pandas as pd

from osu_coach.profile.domain import SKILL_LABELS, build_profile, clean_pass, comfort_stars
from osu_coach.profile.domain.experimental import comfort as experimental_comfort

FEW_PLAYS = 5  # periods with fewer plays are shown, but marked as uncertain
PERIODS = ("month", "week", "day")
ROLLING = "rolling"  # metric key prefix of the rolling day scores ("rolling:YYYY-MM-DD")
ROLLING_DAYS = 7
# Saved with a period's skill scores: the comfort level (★) they were rated at. Its presence also marks scores of
# this rating scale; scores saved by older versions (a miss model) have none and are not shown.
SKILL_REFERENCE = "skill_reference_stars"


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
    """Skill scores and stream speed per period key (see :func:`metric_key`) as (name, value, n) rows; for a skill
    ``n`` is how many map/mod configurations it was measured on. ``None`` for a period with too few plays (stale
    numbers should go); periods that can't be analysed are left out."""
    if not analyses:
        return {}
    metas = pd.DataFrame([a.meta for a in analyses])
    reference = experimental_comfort(metas)  # the Overview's comfort level: one yardstick for every period
    groups = defaultdict(list)
    by_day = defaultdict(list)
    for a in analyses:
        for period in PERIODS:  # months, ISO weeks and days, each kept under its own key
            groups[metric_key(period, period_of(a.meta["date"], period, tz))].append(a)
        by_day[dt.date.fromisoformat(period_of(a.meta["date"], "day", tz))].append(a)
    for day in by_day:  # each day with plays: the plays of the last ROLLING_DAYS days up to it
        first = day - dt.timedelta(days=ROLLING_DAYS - 1)
        groups[metric_key(ROLLING, day.isoformat())] = [
            a for d, items in by_day.items() if first <= d <= day for a in items
        ]
    out: dict[str, list[tuple[str, float | None, int]] | None] = {}
    for key, group in groups.items():
        if len(group) < FEW_PLAYS:  # a play or two say little about a period's skill
            out[key] = None
            continue
        try:
            # level=reference: the ratings are measured against it, not against the period's own comfort
            mp = build_profile(group, level=reference, weighted=False, experimental=reference is not None)
        except Exception:  # noqa: BLE001 - a period with too little data keeps no skill numbers
            continue
        ratings = mp.experimental_skills
        rows = [
            (f"skill_{k}", (ratings.get(k) or {}).get("score"), int((ratings.get(k) or {}).get("maps") or 0))
            for k in SKILL_LABELS
        ]
        rows += [
            (SKILL_REFERENCE, reference, 0),
            ("stream_bpm", mp.tapping.get("comfort_bpm"), int(mp.tapping.get("n") or 0)),
            ("ur_single", mp.tapping.get("ur_single"), 0),
            ("aim_err", mp.aim.get("aim_err_median"), 0),
        ]
        out[key] = rows
    return out


def summarize_periods(
    df: pd.DataFrame,
    metrics: pd.DataFrame,
    period: str = "month",
    since: dt.date | None = None,
    until: dt.date | None = None,
    tz=None,
    rolling: bool = False,
) -> pd.DataFrame:
    """One row per period with plays: counts, star rating, accuracy, skills (``skill_<name>``) etc.
    ``df``: the player's saved plays; ``metrics``: their month_metrics rows (month, name, value).
    Only plays from ``since`` to ``until`` (dates in ``tz``, both included). ``rolling`` (days only): the skills
    are the rolling scores of the last ``ROLLING_DAYS`` days, or the day's own until those have been saved."""
    if df.empty:
        return pd.DataFrame(columns=["month", "plays"])
    local = pd.to_datetime(df["played_at"], utc=True, format="ISO8601").dt.tz_convert(
        tz or dt.datetime.now().astimezone().tzinfo
    )
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
    out["avg_stars"] = g.apply(
        lambda d: (d["stars"] * d["n_objects"]).sum() / max(d["n_objects"].sum(), 1), include_groups=False
    )
    out["comfort_stars"] = g.apply(comfort_stars, include_groups=False)
    out["max_stars_passed"] = df[clean_pass(df)].groupby("month")["stars"].max()
    out["max_stars_fc"] = df[full_combo(df)].groupby("month")["stars"].max()
    out["accuracy"] = g["accuracy"].mean()
    out["misses_per_100"] = g["head_misses"].sum() / g["n_played"].sum().clip(lower=1) * 100
    out["ur"] = g["ur"].median()
    mm = _keyed(metrics, None if period == "month" else period)
    sm = _keyed(metrics, ROLLING) if rolling and period == "day" else mm
    if (sm["name"] == SKILL_REFERENCE).sum() == 0:  # rolling scores not saved yet (analysed by an older version)
        sm = mm
    rated = set(sm.loc[sm["name"] == SKILL_REFERENCE, "month"])  # skill scores of this rating scale
    for name in [f"skill_{k}" for k in SKILL_LABELS] + [SKILL_REFERENCE, "stream_bpm", "ur_single", "aim_err"]:
        src = sm if name.startswith("skill_") else mm
        vals = src[src["name"] == name].set_index("month")["value"]
        if name.startswith("skill_"):
            vals = vals[vals.index.isin(rated)]
        out[name] = vals.reindex(out.index).astype(float)
    out["few_plays"] = out["plays"] < FEW_PLAYS
    return out.sort_index().reset_index().rename(columns={"index": "month"})


def _keyed(metrics: pd.DataFrame, kind: str | None) -> pd.DataFrame:
    """The metric rows of one kind of period (None: months, whose keys have no prefix), keyed without the prefix."""
    if kind is None:
        return metrics[~metrics["month"].str.contains(":")]
    prefix = f"{kind}:"
    return metrics[metrics["month"].str.startswith(prefix)].assign(month=lambda d: d["month"].str[len(prefix) :])


def mark_full_combos(df: pd.DataFrame) -> pd.DataFrame:
    """Plays with ``completed`` as bool and an ``fc`` column."""
    df["completed"] = df["completed"].fillna(0).astype(bool)
    df["fc"] = full_combo(df)
    return df
