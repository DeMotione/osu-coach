"""The skill scores together: accuracy, the comparison with top players, ``compute_skills``."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.profile.domain.aim import (
    AIM_POINTS,
    FLOW_POINTS,
    FLOW_REF,
    FLOW_REF_STEP,
    aim_ref,
    aim_score,
    flow_score,
)
from osu_coach.profile.domain.consistency import consistency_score
from osu_coach.profile.domain.constants import (
    ACCURACY_TOP,
    ACCURACY_ZERO,
    LOW_DATA_MAPS,
    LOW_DATA_NOTES,
    LOW_DATA_REPLAYS,
    SKILL_LABELS,
)
from osu_coach.profile.domain.misses import TYPICAL_CHAIN_RATIO
from osu_coach.profile.domain.ranking import _n_replays, difficulty_weights
from osu_coach.profile.domain.reading import READ_POINTS, READ_REF, reading_score
from osu_coach.profile.domain.sliders import SLIDER_POINTS, slider_ref, slider_score
from osu_coach.profile.domain.stamina import STAMINA_POINTS, STAMINA_WINDOW_SHARE, stamina_ref_bpm, stamina_score
from osu_coach.profile.domain.stats import _clip
from osu_coach.profile.domain.tapping import SPEED_POINTS, speed_score


def accuracy_score(r300: float) -> float:
    return _clip((r300 - ACCURACY_ZERO) / (ACCURACY_TOP - ACCURACY_ZERO) * 100)


# ------------------------------------------------------------------ compared with top players
# The skill values of the top players' reference plays (dev_tools/reference_replays.md, 38 plays, each skill from
# its own group of 4-5 specialists, computed with these same formulas): 100 = as good as them.
TOP_PLAYERS = {
    "aim": 52.2,              # cursor speed x combo of the jump group (WhiteCat, mrekk)
    "flow_aim": 28.6,         # flow group (cryshina, chocomint)
    "speed": 282.7,           # clean burst / stream BPM of the speed group (MALISZEWSKI, aetrna, milosz)
    "stamina": {10: 237.5, 30: 211.7, 60: 195.0, 120: 141.6, 300: 103.0},   # stamina group; 5 min: mrekk's Save Me
    "accuracy": 0.988,        # single-note 300 share of the accuracy group
    "sliders": 277.7,         # slider group (MALISZEWSKI AKAGE / Magic people, mrekk Euclid)
    "reading": 16.4,          # reading group (AR0 plays, -GN / JGLF / reowl)
    "consistency": 1.0,       # miss-after-miss ratio 1.0: a miss doesn't make you miss more (top players barely miss)
}


TOP_LEVEL = 10.0          # the reference players' level (their plays average ~10 stars with mods)


def skills_at_level(skills: dict, level: float) -> dict:
    """The level-relative skill scores again, but with ``level`` as the yardstick instead of your own level (same
    values, same formulas: only "typical for the level" changes). Accuracy, reading and consistency don't depend
    on the level, so they stay as they are."""
    g = lambda k, f: (skills.get(k) or {}).get(f, math.nan)  # noqa: E731
    out = {}

    def log_score(v, ref, points):
        return _clip(50 + points * math.log2(v / ref)) if v is not None and np.isfinite(v) and v > 0 else None
    out["aim"] = log_score(g("aim", "value"), aim_ref(level), AIM_POINTS)
    out["flow_aim"] = log_score(g("flow_aim", "value"), FLOW_REF * 2 ** ((level - 6.0) / FLOW_REF_STEP),
                                FLOW_POINTS)
    out["speed"] = log_score(g("speed", "bpm"), stamina_ref_bpm(level), SPEED_POINTS)
    curve = g("stamina", "curve")
    if isinstance(curve, dict) and curve:
        parts = [log_score(v, stamina_ref_bpm(level) * STAMINA_WINDOW_SHARE[W], STAMINA_POINTS)
                 for W, v in curve.items() if W in STAMINA_WINDOW_SHARE]
        parts = [x for x in parts if x is not None]
        out["stamina"] = float(np.mean(parts)) if parts else None
    else:
        out["stamina"] = None
    out["sliders"] = log_score(g("sliders", "value"), slider_ref(level), SLIDER_POINTS)
    for k in ("accuracy", "reading", "consistency"):
        out[k] = (skills.get(k) or {}).get("score")
    return out


def _top_skills() -> dict:
    """The top players' reference values (:data:`TOP_PLAYERS`) as a skills dict, scored like a player's."""
    t = TOP_PLAYERS
    r = t["accuracy"]
    return {"aim": {"value": t["aim"]}, "flow_aim": {"value": t["flow_aim"]}, "speed": {"bpm": t["speed"]},
            "stamina": {"curve": dict(t["stamina"])}, "sliders": {"value": t["sliders"]},
            "accuracy": {"score": accuracy_score(r)},
            "reading": {"score": _clip(50 + READ_POINTS * math.log2(t["reading"] / READ_REF))},
            "consistency": {"score": _clip(50 + 30 * math.log2(TYPICAL_CHAIN_RATIO / t["consistency"]))}}


def top_comparison(skills: dict, level: float = TOP_LEVEL) -> dict:
    """Your skills measured against the top players' level instead of your own: ``score`` = the same formula with
    ``level`` (10 stars) as the yardstick, so 50 = typical for a 10-star player and it is never above your score
    against your own level; ``top`` = the top players' reference plays on the same scale (where you are headed)."""
    you = skills_at_level(skills, level)
    top = skills_at_level(_top_skills(), level)
    return {k: {"score": you.get(k), "top": top.get(k), "label": SKILL_LABELS.get(k, k)} for k in SKILL_LABELS}


def compute_skills(P, model, tapping, sliders, reading, consistency, level: float | None = None,
            presses: pd.DataFrame | None = None) -> dict:
    s = {}
    N = _n_replays(P)
    # every skill: its plays ranked hardest first, 100% / 99% / 98% ... (1/N steps), like osu!'s pp list
    s["aim"] = aim_score(P, level, N)
    s["flow_aim"] = flow_score(P, level, N)
    s["speed"] = speed_score(P, level, N)
    s["stamina"] = stamina_score(P, tapping, level, presses=presses, n_total=N)
    single = P["run_len"] < 3
    Wa = difficulty_weights(P, None, "stars", N)
    sd = P[single & P["head_hit"].astype(bool)]
    wa = Wa[sd.index]
    r300 = float((wa * (sd["head_result"] == 300)).sum() / wa.sum()) if len(sd) and wa.sum() > 0 else math.nan
    n_single = int(single.sum())
    s["accuracy"] = {"score": accuracy_score(r300) if not math.isnan(r300) and n_single >= 60 else None,
                     "n": n_single, "three_hundred_rate": r300, "ur": tapping.get("ur_single")}
    s["sliders"] = slider_score(P, level, n_total=N)
    s["reading"] = reading_score(P, N)
    s["consistency"] = consistency_score(P, Wa, N)
    for k, v in s.items():
        v["label"] = SKILL_LABELS[k]
        maps = v.get("maps") if v.get("maps") is not None else (v.get("plays") or 0)
        if isinstance(maps, dict):           # stamina: maps per duration
            maps = max(maps.values(), default=0)
        v["low_data"] = bool(v.get("score") is not None and (N < LOW_DATA_REPLAYS or (
            k in ("accuracy",) and (v.get("n") or 0) < LOW_DATA_NOTES) or (0 < maps < LOW_DATA_MAPS)))
    return s


def _rank_skills(skills: dict) -> tuple[list, list]:
    scored = [(k, v["score"]) for k, v in skills.items() if v.get("score") is not None]
    scored.sort(key=lambda kv: kv[1], reverse=True)
    strengths = [k for k, sc in scored[:3] if sc >= 55]
    weaknesses = [k for k, sc in sorted(scored, key=lambda kv: kv[1])[:3] if sc <= 45]
    if not weaknesses and len(scored) >= 3:
        weaknesses = [scored[-1][0]]  # always give one thing to work on
    return strengths, weaknesses
