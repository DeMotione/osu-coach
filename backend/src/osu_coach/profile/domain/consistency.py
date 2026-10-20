"""Consistency: how steady the plays are, and the consistency score."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.profile.domain.constants import FEW_MISSES, FEW_MISSES_NOTES
from osu_coach.profile.domain.misses import TYPICAL_CHAIN_RATIO, miss_chain_ratio
from osu_coach.profile.domain.ranking import _weighted
from osu_coach.profile.domain.stats import _clip, _rate, _w


def _consistency_metrics(P: pd.DataFrame, metas: pd.DataFrame) -> dict:
    out = {}
    if P.empty:
        return out
    W = _w(P)
    miss = (~P["head_hit"]).astype(float) * W
    out["miss_after_miss_ratio"] = miss_chain_ratio(P)
    end = P["time_frac"] >= 0.8
    out["end_miss_share"] = float(miss[end].sum() / miss.sum()) if miss.sum() > 0 else 0.0
    out["end_object_share"] = _rate(end, W)
    first, second = P["time_frac"] < 0.5, P["time_frac"] >= 0.5
    out["first_half_miss_rate"] = _rate(~P.loc[first, "head_hit"], W[first])
    out["second_half_miss_rate"] = _rate(~P.loc[second, "head_hit"], W[second])
    if len(metas) >= 3:
        out["accuracy_std"] = float(metas["accuracy"].std())
    return out


# ------------------------------------------------------------------ consistency
STEADY_TYPICAL = 2.0  # misses / 100 notes: typical spread between plays of the same difficulty (std) ...
STEADY_POINTS = 30.0  # ... half the spread = +30, like the miss-chain part
STEADY_MIN_PLAYS = 5


def play_steadiness(P: pd.DataFrame) -> dict:
    """How steady your plays are from one to the next: per passed play, misses per 100 notes minus what your
    other plays of a similar star rating (±0.5*) average; ``spread`` = the standard deviation of that (misses /
    100 notes). A steady player stays close to their usual result on every map; an unsteady one has great
    and terrible plays at the same difficulty."""
    out = {"spread": math.nan, "plays": 0}
    if P is None or P.empty or "replay_key" not in P:
        return out
    D = P[P["completed"].astype(bool)] if "completed" in P else P
    g = D.groupby("replay_key").agg(
        miss=("head_hit", lambda h: float((~h.astype(bool)).mean() * 100)),
        stars=("stars", "first") if "stars" in D else ("head_hit", "size"),
    )
    g = g.dropna()
    if len(g) < STEADY_MIN_PLAYS:
        return out
    st_ = g["stars"].to_numpy(float)
    m = g["miss"].to_numpy(float)
    dev = []
    for i in range(len(g)):
        near = (np.abs(st_ - st_[i]) <= 0.5) & (np.arange(len(g)) != i)
        if near.sum() >= 2:
            dev.append(m[i] - m[near].mean())
    if len(dev) < STEADY_MIN_PLAYS:
        return out
    out["spread"] = float(np.std(dev))
    out["plays"] = int(len(dev))
    return out


def consistency_score(P: pd.DataFrame, weights: pd.Series, n_total: int) -> dict:
    """Consistency = the average of what can be measured of: **miss chains** (does one miss make you miss more?
    :func:`miss_chain_ratio`, 50 = typical 2×, half = +30) and **steadiness** (:func:`play_steadiness`: how much
    your plays of the same difficulty differ, 50 = a spread of 2 misses / 100 notes, half = +30). Either part
    alone is enough, so the score exists as soon as there are 5+ passed plays."""
    out = {
        "score": None,
        "n": int(len(P)),
        "miss_after_miss_ratio": math.nan,
        "chain_score": None,
        "steady_score": None,
        "spread": math.nan,
    }
    if P is None or P.empty:
        return out
    ratio = miss_chain_ratio(_weighted(P, weights))
    out["miss_after_miss_ratio"] = ratio
    if ratio and not math.isnan(ratio):
        out["chain_score"] = _clip(50 + 30 * math.log2(TYPICAL_CHAIN_RATIO / ratio))
    sd = play_steadiness(P)
    out["spread"], out["steady_plays"] = sd["spread"], sd["plays"]
    if np.isfinite(sd["spread"]):
        out["steady_score"] = _clip(50 + STEADY_POINTS * math.log2(STEADY_TYPICAL / max(sd["spread"], 0.05)))
    parts = [x for x in (out["chain_score"], out["steady_score"]) if x is not None]
    if parts:
        out["score"] = float(np.mean(parts))
    misses = float((~P["head_hit"].astype(bool)).sum())
    if out["score"] is None and len(P) >= FEW_MISSES_NOTES and misses < FEW_MISSES:
        out["too_few_misses"] = True  # nothing to chain: no misses to follow a miss
    return out


# ------------------------------------------------------------------ consistency around the comfort level
COMFORT_RANGE = 1.0  # stars (with mods) either side of the comfort level whose plays count
COMFORT_MIN_MAPS = 8  # different maps needed in that range before there is a score
ACC_BAD, ACC_GOOD = 0.93, 0.99  # accuracy scale: 93% → 0, 99% → 1
BEST_WEIGHT = 0.7  # the better of combo and accuracy carries the score; both good = top score
FULL_COMBO = 0.98  # share of the map's max combo (no misses) that counts as a full combo


def _held(x: np.ndarray) -> float:
    """Usual level minus how much it swings from map to map (one standard deviation), clipped to 0–1."""
    return float(np.clip(x.mean() - x.std(), 0, 1))


def held_score(combo: float, accuracy: float) -> float:
    """0–100: the better of combo and accuracy held carries the score, both good = top score, both bad = low."""
    return 100 * (BEST_WEIGHT * max(combo, accuracy) + (1 - BEST_WEIGHT) * min(combo, accuracy))


def _plays_near(metas: pd.DataFrame | None, low: float, high: float) -> pd.DataFrame:
    """The plays (star rating with mods) from ``low`` to ``high``, with their combo share and accuracy scale."""
    need = {"stars", "max_combo", "map_max_combo", "accuracy", "beatmap_md5"}
    if metas is None or metas.empty or not need <= set(metas.columns):
        return pd.DataFrame()
    m = metas.drop_duplicates("key") if "key" in metas else metas
    m = m.assign(
        stars=pd.to_numeric(m["stars"], errors="coerce"),
        accuracy=pd.to_numeric(m["accuracy"], errors="coerce"),
        top=pd.to_numeric(m["map_max_combo"], errors="coerce"),
    )
    m = m[m["stars"].between(low, high) & m["accuracy"].notna() & (m["top"] > 0)]
    if m.empty:
        return m
    combo = (pd.to_numeric(m["max_combo"], errors="coerce").fillna(0) / m["top"]).clip(0, 1)
    misses = pd.to_numeric(m["nmiss"], errors="coerce").fillna(0) if "nmiss" in m else pd.Series(0, index=m.index)
    return m.assign(
        combo=combo,
        acc_scale=((m["accuracy"] - ACC_BAD) / (ACC_GOOD - ACC_BAD)).clip(0, 1),
        full=((combo >= FULL_COMBO) & (misses == 0)).astype(float),
    )


def comfort_consistency(metas: pd.DataFrame | None, comfort: float | None) -> dict:
    """How steadily combo and accuracy hold from map to map around the comfort level: the plays (star rating with
    mods) within ``COMFORT_RANGE`` stars of it, each map once (the average of its plays, so retrying one map can't
    carry the score). Scored from ``COMFORT_MIN_MAPS`` different maps; until then ``needs`` says what to play."""
    out = {"score": None, "maps": 0, "plays": 0, "min_maps": COMFORT_MIN_MAPS, "low": None, "high": None, "needs": None}
    if comfort is None or not math.isfinite(comfort):
        out["needs"] = (
            "First your comfort level: pass 3 different maps (with at most 2 misses per 100 notes) and analyse your "
            f"replays. Then play {COMFORT_MIN_MAPS} different maps within ±{COMFORT_RANGE:g}★ of it."
        )
        return {**out, "reason": "Not enough data"}
    low, high = max(0.0, comfort - COMFORT_RANGE), comfort + COMFORT_RANGE
    m = _plays_near(metas, low, high)
    per_map = (
        m.groupby(m["beatmap_md5"].astype(str))[["combo", "acc_scale", "full", "accuracy"]].mean()
        if not m.empty
        else pd.DataFrame()
    )
    out.update(low=low, high=high, maps=len(per_map), plays=len(m))
    if len(per_map) < COMFORT_MIN_MAPS:
        more = COMFORT_MIN_MAPS - len(per_map)
        out["needs"] = (
            f"Play {more} more different map{'s' if more > 1 else ''} between {low:.1f}★ and {high:.1f}★ (your "
            f"{comfort:.1f}★ comfort level ±{COMFORT_RANGE:g}★), then analyse your replays again: consistency is "
            f"scored from {COMFORT_MIN_MAPS} different maps in that range ({len(per_map)} so far). Passed and failed "
            "plays both count; playing a map you already have again doesn't add one."
        )
        return {**out, "reason": "Not enough data"}
    combo_held = _held(per_map["combo"].to_numpy(float))
    acc_held = _held(per_map["acc_scale"].to_numpy(float))
    return {
        **out,
        "score": round(held_score(combo_held, acc_held), 1),
        "combo": combo_held,
        "accuracy": acc_held,
        "full_combo_share": float(per_map["full"].mean()),
        "mean_accuracy": float(per_map["accuracy"].mean()),
        "reason": f"Combo and accuracy held across {len(per_map)} different maps within ±{COMFORT_RANGE:g}★",
    }
