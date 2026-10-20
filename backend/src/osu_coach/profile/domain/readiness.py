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
left out. Star ratings more than :data:`MAX_GAP` above the comfort level are too far to compare.
"""

from __future__ import annotations

import math

from osu_coach.profile.domain.demand import log_demand
from osu_coach.profile.domain.experimental import ACCURACY_TRANSITION_STARS, POINTS

SKILLS = ("aim", "flow_aim", "speed", "stamina", "accuracy", "sliders", "reading")
PASS_SPREAD = 0.6  # ★: a star above the comfort level takes the pass chance from 75% to ~36%, two stars to ~10%
PASS_AT_LEVEL = 0.75  # clean-pass chance on maps of the comfort level (a 75th percentile of clean passes)

# the star ratings offered to compare with: every whole star from 1★ to 13★ and half stars near the comfort level;
# those more than MAX_GAP above it are shown locked
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


def _half_star_below(comfort: float) -> tuple[float, float]:
    """The comfort level (to 0.1★, within 1–13★) and the half star at or below it."""
    lo, hi = TARGET_RANGE
    base = round(min(max(comfort, lo), hi), 1)
    return base, math.floor(base / TARGET_STEP + 1e-9) * TARGET_STEP


def targets(comfort: float) -> list[tuple[float, bool]]:
    """The star ratings to compare with, easiest first, and whether each is locked: every whole star from 1★ to 13★,
    the comfort level itself and the two half stars either side of it (6.15★: 5.5, 6, 6.5 and 7★; 6.55★: 6, 6.5, 7
    and 7.5★). Only star ratings more than :data:`MAX_GAP` above the comfort level are locked; easier ones never."""
    lo, hi = TARGET_RANGE
    base, half = _half_star_below(comfort)
    near = {round(half + i * TARGET_STEP, 1) for i in (-1, 0, 1, 2)}
    stars = sorted(s for s in {float(s) for s in range(int(lo), int(hi) + 1)} | near | {base} if lo <= s <= hi)
    return [(s, s > base + MAX_GAP + 1e-9) for s in stars]


def default_target(comfort: float) -> float:
    """The half star a star above the comfort level (6.15★: 7★), or the highest one offered."""
    _, half = _half_star_below(comfort)
    return round(min(half + 1.0, TARGET_RANGE[1]), 1)
