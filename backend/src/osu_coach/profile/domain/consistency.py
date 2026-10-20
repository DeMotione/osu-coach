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


# ------------------------------------------------------------------ consistency at a star rating
STAR_MIN_MAPS = 8  # different maps needed before a star rating has a score; more = a more reliable score
STAR_SPAN = 1.0  # consistency at X★ uses the maps from X − STAR_SPAN up to X: never harder ones
STAR_EASY_WEIGHT = 0.5  # weight of a map STAR_SPAN easier than X (one at X = 1): easy maps can't carry the score
ACC_BAD, ACC_GOOD = 0.88, 0.94  # accuracy scale: 88% → 0, 94% → 1
COMBO_NONE = 0.10  # share of the map's max combo worth nothing: missing so much the combo never builds up
COMBO_HELD = 0.30  # combo scale value (≈20% of the max combo) below which a map's score fades to 0 at COMBO_NONE
BEST_WEIGHT = 0.7  # the better of combo and accuracy carries the score; both good = top score
SWING_WEIGHT = 0.5  # consistency = usual map score − this × its swing between maps
FULL_COMBO = 0.98  # share of the map's max combo (no misses) that counts as a full combo


def combo_scale(share):
    """How well the combo is held, 0–1, on a log scale from ``COMBO_NONE`` of the max combo (0) to a full combo (1):
    20% = 0.30, 30% = 0.48, 50% = 0.70, 70% = 0.85. Holding big parts of a map counts, not only full combos."""
    share = np.maximum(np.asarray(share, dtype=float), 1e-6)
    return np.clip(np.log10(share / COMBO_NONE) / np.log10(1 / COMBO_NONE), 0, 1)


def map_score(combo_share, accuracy):
    """0–1 for one play: the better of combo held (:func:`combo_scale`) and accuracy (88–94% scale) counts 70%, the
    other 30%, and the score fades to 0 when less than about 20% of the combo is held (10% or less = 0). 30% of the
    combo at 93% = 0.73, a full combo at 90% = 0.80."""
    combo = combo_scale(combo_share)
    acc = np.clip((np.asarray(accuracy, dtype=float) - ACC_BAD) / (ACC_GOOD - ACC_BAD), 0, 1)
    both = BEST_WEIGHT * np.maximum(combo, acc) + (1 - BEST_WEIGHT) * np.minimum(combo, acc)
    return both * np.minimum(1.0, combo / COMBO_HELD)


def _plays_up_to(metas: pd.DataFrame | None, stars: float) -> pd.DataFrame:
    """The plays of maps from ``stars`` − ``STAR_SPAN`` up to ``stars`` (star rating with mods), with their map score
    and weight (1 at ``stars``, ``STAR_EASY_WEIGHT`` a span easier)."""
    need = {"stars", "max_combo", "map_max_combo", "accuracy", "beatmap_md5"}
    if metas is None or metas.empty or not need <= set(metas.columns):
        return pd.DataFrame()
    m = metas.drop_duplicates("key") if "key" in metas else metas
    m = m.assign(
        stars=pd.to_numeric(m["stars"], errors="coerce"),
        accuracy=pd.to_numeric(m["accuracy"], errors="coerce"),
        top=pd.to_numeric(m["map_max_combo"], errors="coerce"),
    )
    m = m[m["stars"].between(stars - STAR_SPAN, stars + 1e-9) & m["accuracy"].notna() & (m["top"] > 0)]
    if m.empty:
        return m
    combo = (pd.to_numeric(m["max_combo"], errors="coerce").fillna(0) / m["top"]).clip(0, 1)
    misses = pd.to_numeric(m["nmiss"], errors="coerce").fillna(0) if "nmiss" in m else pd.Series(0, index=m.index)
    return m.assign(
        combo=combo,
        map_score=map_score(combo, m["accuracy"]),
        weight=1 - (1 - STAR_EASY_WEIGHT) * (stars - m["stars"]) / STAR_SPAN,
        full=((combo >= FULL_COMBO) & (misses == 0)).astype(float),
    )


def star_consistency(metas: pd.DataFrame | None, stars: float | None, *, comfort: bool = False) -> dict:
    """How steadily combo and accuracy hold from map to map at the star rating ``stars``: the maps from a star below
    it up to it (6.2★: 5.2–6.2★, with mods; harder maps never count), every play scored by :func:`map_score`, each
    map once (the average of its plays, so retrying one map can't carry the score) and weighted by how close it is
    to ``stars``. Consistency = the usual map score − half its swing between maps. Scored from ``STAR_MIN_MAPS``
    different maps; until then ``needs`` says what to play. ``comfort``: ``stars`` is the comfort level (wording)."""
    out = {"score": None, "low": None, "high": None, "maps": 0, "plays": 0, "min_maps": STAR_MIN_MAPS, "needs": None}
    if stars is None or not math.isfinite(stars):
        out["needs"] = (
            "First your comfort level: pass 3 different maps (with at most 2 misses per 100 notes) and analyse your "
            f"replays. Then play {STAR_MIN_MAPS} different maps up to a star below it."
        )
        return {**out, "reason": "Not enough data"}
    low, high = max(0.0, stars - STAR_SPAN), stars
    m = _plays_up_to(metas, stars)
    per_map = (
        m.groupby(m["beatmap_md5"].astype(str))[["combo", "map_score", "weight", "full", "accuracy"]].mean()
        if not m.empty
        else pd.DataFrame()
    )
    out.update(low=low, high=high, maps=len(per_map), plays=len(m))
    if len(per_map) < STAR_MIN_MAPS:
        more = STAR_MIN_MAPS - len(per_map)
        which = f"your {stars:.1f}★ comfort level" if comfort else f"{stars:g}★"
        out["needs"] = (
            f"Play {more} more different map{'s' if more > 1 else ''} between {low:.1f}★ and {high:.1f}★ (with mods; "
            f"the closer to {high:.1f}★, the more it counts), then analyse your replays again: consistency at {which} "
            f"is scored from {STAR_MIN_MAPS} different maps up to a star below it ({len(per_map)} so far), and the more "
            "you play, the more reliable it gets. Harder maps don't count. Passed and failed plays both count; playing "
            "a map you already have again doesn't add one."
        )
        return {**out, "reason": "Not enough data"}
    scores, weights = per_map["map_score"].to_numpy(float), per_map["weight"].to_numpy(float)
    usual = float(np.average(scores, weights=weights))
    swing = float(np.sqrt(np.average((scores - usual) ** 2, weights=weights)))
    return {
        **out,
        "score": round(100 * float(np.clip(usual - SWING_WEIGHT * swing, 0, 1)), 1),
        "map_score": usual,
        "swing": swing,
        "weak_maps": int((per_map["combo"] < 0.2).sum()),
        "mean_combo": float(np.average(per_map["combo"], weights=weights)),
        "full_combo_share": float(np.average(per_map["full"], weights=weights)),
        "mean_accuracy": float(np.average(per_map["accuracy"], weights=weights)),
        "reason": f"Combo and accuracy held across {len(per_map)} different maps of {low:.1f}–{high:.1f}★",
    }
