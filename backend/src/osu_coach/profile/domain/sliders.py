"""Slider difficulty, reference and the slider score."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.profile.domain.ranking import _n_replays, rank_weights, ranked_mean
from osu_coach.profile.domain.stats import _clip, _map_key

SLIDER_FOLLOW_SLACK = 1.0  # circle diameters of slider path the follow circle covers without moving
SLIDER_SHORT = 0.5  # ... short sliders still count as half a diameter of movement (holding them)
SLIDER_TOP = 30  # per play: the hardest 30 sliders whose head you hit
SLIDER_MIN = 10  # ... a play needs 10+ such sliders
SLIDER_MIN_MAPS = 3
SLIDER_HOLD_POWER = 3.0  # breaking a few of your hardest sliders costs a lot: value × held share³
SLIDER_REF = 40.0  # 50 = this value at 6★ ...
SLIDER_REF_STEP = 3.0  # ... ×2 every 3★ (slider difficulty grows much slower with star rating than aim)
SLIDER_POINTS = 25.0  # points per doubling of the value


def slider_difficulty(S: pd.DataFrame) -> pd.Series:
    """Difficulty of following each slider (0 = the follow circle covers it without moving):

    speed (circle diameters per second the ball moves, real time) × length (log2 of 1 + the path beyond what
    the follow circle covers, in diameters; repeats add log2(repeats)) × shape (1 + half a point per half
    circle of turning, up to 2 full turns, + 0.3 per sharp corner and + 0.2 per left↔right bend, up to 4 each)
    × speed change (1 + |ln(speed / previous slider's speed)|, up to ×2: a slow slider right after a fast one or
    the other way round) × rush (up to ×1.5 when the next note comes less than 250 ms after the slider end)."""
    diam = 2 * S["radius"].astype(float).clip(lower=1.0)
    speed = S["slider_vel_real"].astype(float).fillna(0) * 1000.0 / diam
    eff = (S["slider_len"].astype(float).fillna(0) / diam - SLIDER_FOLLOW_SLACK).clip(lower=0)
    spans = S["slider_spans"].astype(float).fillna(1).clip(lower=1)
    length = np.log2(1 + (eff + SLIDER_SHORT) * (1 + np.log2(spans)))
    col = lambda c: S[c].astype(float).fillna(0) if c in S else pd.Series(0.0, index=S.index)  # noqa: E731
    shape = (
        1
        + 0.5 * (col("slider_turn") / math.pi).clip(upper=4)
        + 0.3 * col("slider_corners").clip(upper=4)
        + 0.2 * col("slider_bends").clip(upper=4)
    )
    change = 1 + col("slider_vel_change").clip(upper=1.0)
    gap = S["slider_next_gap"].astype(float).fillna(1000.0) if "slider_next_gap" in S else 1000.0
    rush = 1 + 0.5 * ((250.0 - gap) / 250.0).clip(0, 1)
    return speed * length * shape * change * rush


def slider_ref(level: float | None) -> float:
    lv = 6.0 if level is None or not np.isfinite(level) else float(level)
    return SLIDER_REF * 2 ** ((lv - 6.0) / SLIDER_REF_STEP)


def slider_score(P: pd.DataFrame, level: float | None = None, n_total: int | None = None) -> dict:
    """Slider control: how hard the sliders are that you follow to the end — not how many easy ones.

    Every slider whose head you hit gets a difficulty (:func:`slider_difficulty`: speed, length, shape, speed
    changes, rush). Per play, the hardest 30 count: value = their average difficulty × (share you held without
    a break)³, so a play full of short, slow sliders stays low however clean, and breaking 1 of the 30 hardest
    costs about 25%. One value per map (your best play of it), weighted like osu!'s pp (:func:`ranked_mean`); the
    score = 50 + 25 × log2(that ÷ the value typical for your level), so twice the typical value = 75."""
    out = {
        "score": None,
        "n": 0,
        "plays": 0,
        "value": math.nan,
        "ref": slider_ref(level),
        "break_rate": math.nan,
        "top_held": math.nan,
        "best": None,
    }
    if P is None or P.empty or "kind" not in P:
        return out
    S = P[(P["kind"] == "slider") & P["head_hit"].astype(bool)]
    if "slider_vel_real" not in S or S.empty:
        return out
    S = S.assign(
        diff=slider_difficulty(S).to_numpy(),
        held=~S["broke"].fillna(False).astype(bool).to_numpy(),
        map=_map_key(S).to_numpy(),
    )
    out["n"] = int(len(S))
    out["break_rate"] = float(1 - S["held"].mean())
    rows = []
    for (k, m), d in S.groupby(["replay_key", "map"], sort=False):
        if len(d) < SLIDER_MIN:
            continue
        top = d.nlargest(SLIDER_TOP, "diff")
        hold = float(top["held"].mean())
        rows.append(
            {
                "map": m,
                "value": float(top["diff"].mean()) * hold**SLIDER_HOLD_POWER,
                "hold": hold,
                "diff": float(top["diff"].mean()),
            }
        )
    if not rows:
        return out
    R = pd.DataFrame(rows).sort_values("value", ascending=False).drop_duplicates("map")
    N = n_total or _n_replays(P)
    w = rank_weights(N, len(R))
    out["plays"] = int(len(R))
    out["value"] = ranked_mean(R["value"].to_numpy(), N)
    out["top_held"] = float((R["hold"].to_numpy() * w).sum() / w.sum()) if w.sum() > 0 else math.nan
    out["best"] = float(R["value"].iloc[0])
    if len(R) >= SLIDER_MIN_MAPS:
        out["score"] = _clip(50 + SLIDER_POINTS * math.log2(max(out["value"], 1e-6) / out["ref"]))
    return out
