"""Readiness for another star rating: the comfort-level scores moved to it, and the chance to pass its maps.

The comfort-level ratings (:func:`experimental.ratings`) score each skill against what is typical at the comfort
level θ: ``50 + P_k · log2(measured / expected)`` (``P_k`` points per doubling). The demand curves (:mod:`demand`)
say how much more typical maps of another star rating T demand of the skill, ``ΔD_k = D_k(T) − D_k(θ)`` (log2).
Together::

    score at T     s_k(T) = clip(s_k(θ) − P_k · ΔD_k, 0, 100)    the comfort score, minus what T★ maps demand more
    clean pass     P(T) = σ(logit(p₀) − (T − θ) / τ)              p₀ at the comfort level

So every score falls as the star rating rises, each by how much more its maps demand (accuracy: the same hit-error
spread in a narrower 300 window), and rises on easier maps. The comfort level is made of clean passes (its 75th
percentile), so the pass chance is p₀ there and falls with every star above it. Consistency has its own card and is
left out. Star ratings more than :data:`MAX_GAP` from the comfort level are too far to compare.
"""

from __future__ import annotations

import math

from osu_coach.profile.domain.demand import log_demand
from osu_coach.profile.domain.experimental import ACCURACY_TRANSITION_STARS, POINTS

SKILLS = ("aim", "flow_aim", "speed", "stamina", "accuracy", "sliders", "reading")
PASS_SPREAD = 0.6  # ★: a star above the comfort level takes the pass chance from 75% to ~36%, two stars to ~10%
PASS_AT_LEVEL = 0.75  # clean-pass chance on maps of the comfort level (a 75th percentile of clean passes)

# the star ratings offered to compare with: half stars up to MAX_GAP either side of the comfort level; the whole
# stars beyond that, from 1★ to 13★, are shown locked
MAX_GAP = 2.0
TARGET_STEP = 0.5
TARGET_RANGE = (1.0, 13.0)


def _sigma_for(non300: float, windows: list[tuple[float, float]]) -> float:
    """Hit-error spread (ms) that gives the non-300 share ``non300`` on these 300 windows (bisection)."""
    total = sum(w for _, w in windows) or 1.0

    def share(sigma: float) -> float:
        return sum(w * math.erfc(win / (math.sqrt(2) * sigma)) for win, w in windows) / total

    lo, hi = 0.5, 500.0
    if non300 <= share(lo):
        return lo
    if non300 >= share(hi):
        return hi
    for _ in range(60):
        mid = math.sqrt(lo * hi)
        if share(mid) < non300:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


def _accuracy_drop(row: dict, theta: float, ratio: float) -> float | None:
    """Accuracy points lost when the 300 window is ``ratio`` times narrower: the same hit-error spread gives a larger
    non-300 share."""
    measured, windows = row.get("measured"), row.get("od_windows") or []
    if measured is None or not windows or not math.isfinite(measured):
        return None
    measured = max(measured, 1e-6)
    sigma = _sigma_for(measured, windows)
    total = sum(w for _, w in windows) or 1.0
    share = sum(w * math.erfc(win / ratio / (math.sqrt(2) * sigma)) for win, w in windows) / total
    points = POINTS["accuracy"] + 5 * min(1.0, max(0.0, ACCURACY_TRANSITION_STARS - theta))
    return points * math.log2(max(share, 1e-6) / measured)


def scores_at(rows: dict[str, dict], theta: float | None, target: float) -> dict[str, dict | None]:
    """The comfort-level scores at ``target`` ★: ``score`` (0–100), ``change`` (points against the comfort level)
    and ``demand`` (how many times what comfort-level maps demand). None: no comfort-level score."""
    out: dict[str, dict | None] = {}
    for skill in SKILLS:
        row = rows.get(skill) or {}
        base = row.get("score")
        if theta is None or base is None or not math.isfinite(theta):
            out[skill] = None
            continue
        ratio = 2 ** (log_demand(skill, target) - log_demand(skill, theta))
        drop = _accuracy_drop(row, theta, ratio) if skill == "accuracy" else POINTS[skill] * math.log2(ratio)
        if drop is None:
            out[skill] = None
            continue
        score = round(max(0.0, min(100.0, base - drop)), 1)
        out[skill] = {"score": score, "change": round(score - base, 1), "demand": round(ratio, 3)}
    return out


def compare_at(rows: dict[str, dict], theta: float, target: float) -> dict:
    """The skills on typical maps of ``target`` ★ (:func:`scores_at`), the lowest of them and the chance to pass such
    a map cleanly."""
    skills = scores_at(rows, theta, target)
    known = {k: v["score"] for k, v in skills.items() if v is not None}
    z = math.log(PASS_AT_LEVEL / (1 - PASS_AT_LEVEL)) - (target - theta) / PASS_SPREAD
    return {
        "target": target,
        "skills": skills,
        "weakest": min(known, key=known.get) if known else None,
        "pass_chance": round(1 / (1 + math.exp(-max(-35.0, min(35.0, z)))), 4),
    }


def targets(comfort: float) -> list[tuple[float, bool]]:
    """The star ratings to compare with, easiest first, and whether each is locked (more than :data:`MAX_GAP` from
    the comfort level): half stars around the comfort level, the whole stars beyond them."""
    lo, hi = TARGET_RANGE
    base = round(min(max(comfort, lo), hi), 1)
    steps = round(MAX_GAP / TARGET_STEP)
    near = [v for i in range(-steps, steps + 1) if lo <= (v := round(base + i * TARGET_STEP, 1)) <= hi]
    for end in (lo, hi):  # 1★ / 13★ within reach: offered too (instead of a half step right next to it)
        if abs(end - base) > MAX_GAP or end in near:
            continue
        closest = min(near, key=lambda v: abs(v - end))
        if abs(closest - end) < TARGET_STEP / 2 and closest != base:
            near.remove(closest)
        near.append(end)
    far = [float(s) for s in range(int(lo), int(hi) + 1) if abs(s - base) > MAX_GAP]
    return sorted([(v, False) for v in near] + [(v, True) for v in far])


def default_target(comfort: float) -> float:
    """One star above the comfort level (or the highest one offered)."""
    lo, hi = TARGET_RANGE
    base = round(min(max(comfort, lo), hi), 1)
    return round(min(base + 1.0, hi), 1)
