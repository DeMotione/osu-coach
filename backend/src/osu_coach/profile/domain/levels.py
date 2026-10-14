"""The player's level and the weight of each replay by how far its star rating is from it; comfort stars."""
from __future__ import annotations

import datetime as _dt
import math

import numpy as np
import pandas as pd

LEVEL_BAND = 0.5         # ★: replays within ± this of the player's level count fully
LEVEL_SIGMA = 0.5        # ★: Gaussian fall-off outside the band
RECENT_DAYS = 30         # the level is measured on the replays of the last 30 days (before the newest one) ...
RECENT_MIN = 15          # ... or on the newest 15 if there are fewer
MIN_WEIGHT = 1e-6


# ------------------------------------------------------------------ difficulty weighting
def replay_weight(stars, level: float, band: float = LEVEL_BAND, sigma: float = LEVEL_SIGMA) -> np.ndarray:
    """Weight of a replay by the distance of its star rating (with mods) from the player's level: 1 within
    ± ``band``, then a Gaussian tail (``sigma``): 1★ off ≈ 0.61, 1.5★ ≈ 0.14, 2★ ≈ 0.01, 3★ ≈ 0.00004.
    Unknown star rating or level = 1."""
    s = np.asarray(stars, dtype=float)
    if level is None or not np.isfinite(level):
        return np.ones_like(s)
    d = np.maximum(np.abs(s - level) - band, 0.0)
    w = np.exp(-0.5 * (np.nan_to_num(d) / sigma) ** 2)
    return np.where(np.isfinite(s), np.maximum(w, MIN_WEIGHT), 1.0)


def _utc(v) -> _dt.datetime | None:
    try:
        t = pd.Timestamp(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(t):
        return None
    return (t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")).to_pydatetime()


def detect_level(metas: pd.DataFrame) -> dict:
    """The player's level: comfort star rating (see :func:`comfort_stars`) of the recent replays — the last
    ``RECENT_DAYS`` days before the newest one, or the newest ``RECENT_MIN`` if there are fewer."""
    out = {"level": math.nan, "recent_n": 0, "recent_since": None}
    if metas is None or metas.empty or "stars" not in metas:
        return out
    dates = metas["date"] if "date" in metas else pd.Series([None] * len(metas), index=metas.index)
    m = metas.assign(_t=[_utc(d) for d in dates])
    m = m.sort_values("_t", ascending=False, na_position="last")
    dated = m[m["_t"].notna()]
    if len(dated):
        since = dated["_t"].iloc[0] - _dt.timedelta(days=RECENT_DAYS)
        recent = dated[dated["_t"] >= since]
        if len(recent) < RECENT_MIN:
            recent = m.head(RECENT_MIN)
    else:
        recent = m
    out["level"] = comfort_stars(recent.drop(columns="_t"))
    out["recent_n"] = int(len(recent))
    t = recent["_t"].dropna()
    out["recent_since"] = t.min() if len(t) else None
    return out


def weight_table(level: float, band: float = LEVEL_BAND, sigma: float = LEVEL_SIGMA) -> list[tuple[float, float]]:
    """(★ off the level, weight) pairs for explanations."""
    return [(d, float(replay_weight([level + d], level, band, sigma)[0])) for d in (0.5, 1.0, 1.5, 2.0, 3.0)]


CLEAN_PASS_MISSES_PER_100 = 5.0


def clean_pass(metas: pd.DataFrame) -> pd.Series:
    """Finished plays with at most 5 misses per 100 notes: getting through a map with many more (lazer
    lets you) is no real pass of it."""
    per_100 = metas["head_misses"] / metas["n_objects"].clip(lower=1) * 100
    return metas["completed"].astype(bool) & (per_100 <= CLEAN_PASS_MISSES_PER_100)


def comfort_stars(metas: pd.DataFrame) -> float:
    """Star rating you play comfortably: 75th percentile of finished plays with at most 2 misses per 100
    notes (columns stars, head_misses, n_objects, completed)."""
    if metas.empty or "stars" not in metas:
        return math.nan
    m = metas.dropna(subset=["stars"])
    if m.empty:
        return math.nan
    m = m.assign(miss_per_100=m["head_misses"] / m["n_objects"].clip(lower=1) * 100)
    good = m[(m["miss_per_100"] <= 2.0) & (m["completed"].astype(bool))]
    if len(good):
        return float(good["stars"].quantile(0.75))
    return float(m["stars"].quantile(0.25) - 0.4)


def _levels(metas: pd.DataFrame, P: pd.DataFrame, model) -> dict:
    """Difficulty levels (star rating units) used to pick practice maps."""
    out = {"comfort_stars": math.nan, "aim_level": math.nan, "speed_level": math.nan}
    if metas.empty or "stars" not in metas:
        return out
    out["comfort_stars"] = comfort_stars(metas)
    # skill levels: local star-equivalent where predicted miss chance reaches 5%
    coef = getattr(model, "coef", None)
    for skill, col in (("aim_level", "aim_eq"), ("speed_level", "speed_eq")):
        d = P.dropna(subset=[col])
        if len(d) < 300:
            continue
        bins = np.arange(0, d[col].max() + 0.25, 0.25)
        d = d.assign(b=pd.cut(d[col], bins=bins, labels=bins[:-1]))
        g = d.groupby("b", observed=True)["head_hit"].agg(["size", lambda s: float((~s).mean())])
        g.columns = ["n", "miss"]
        g = g[g["n"] >= 40]
        ok = g[g["miss"] <= 0.05]
        if len(ok):
            out[skill] = float(ok.index.max()) + 0.25
    out["model_coef"] = coef
    return out
