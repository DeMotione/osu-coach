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
STEADY_TYPICAL = 2.0      # misses / 100 notes: typical spread between plays of the same difficulty (std) ...
STEADY_POINTS = 30.0      # ... half the spread = +30, like the miss-chain part
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
    g = D.groupby("replay_key").agg(miss=("head_hit", lambda h: float((~h.astype(bool)).mean() * 100)),
                                    stars=("stars", "first") if "stars" in D else ("head_hit", "size"))
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
    out = {"score": None, "n": int(len(P)), "miss_after_miss_ratio": math.nan, "chain_score": None,
           "steady_score": None, "spread": math.nan}
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
        out["too_few_misses"] = True        # nothing to chain: no misses to follow a miss
    return out
