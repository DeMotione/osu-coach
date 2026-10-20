"""Readiness for another star rating: every skill as a star level, compared with what maps of that star rating
demand.

The comfort-level ratings (:func:`experimental.ratings`) measure each skill against what is typical at the comfort
level θ, ``r = log2(measured / expected)``. The demand curves (:mod:`demand`) say how much more maps of other star
ratings demand of the skill. Together::

    skill level      L_k  = the star rating whose typical maps demand  D_k(θ) · 2^r      (★)
    at a target T:   gap  = L_k − T,   bar = clip(50 + 10 · gap, 0, 100)     50 = exactly what T★ maps demand
    effective level  L_eff(T) = −τs · ln Σ_k ŵ_k(T) · exp(−L_k / τs)        ŵ = how much T★ maps test k (sum 1),
                                                                             all skills but accuracy
    clean pass       P(T) = σ((L_eff − T) / τ + logit(p₀))                   p₀ at your own effective level

A typical player (every rating 50) gets ``L_k = θ`` for every skill, so every skill is the same number of stars
short of a harder map. The effective level is a soft minimum: the weakest skill a map tests most decides.
Consistency is no level skill (it has its own card) and is left out.
"""

from __future__ import annotations

import math

from osu_coach.profile.domain.demand import log_demand, skill_weights, stars_for
from osu_coach.profile.domain.experimental import MIN_MAPS, _accuracy_sigma, _expected

SKILLS = ("aim", "flow_aim", "speed", "stamina", "accuracy", "sliders", "reading")
# a clean pass is about misses: accuracy (300s vs 100s) has its bar but doesn't decide the effective level
PASS_SKILLS = ("aim", "flow_aim", "speed", "stamina", "sliders", "reading")
POINTS_PER_STAR = 10.0  # bar: 50 + 10 per star above the target, 0 = 5★ short
SOFT_MIN = 0.5  # ★: how strongly the weakest skill decides the effective level (smaller = more)
PASS_SPREAD = 0.6  # ★: a star more than your effective level takes the pass chance from 75% to ~29%
PASS_AT_LEVEL = 0.75  # clean-pass chance on maps of your own effective level (the comfort level is a 75th percentile)
HELD_ALL = 0.95  # success share from which a skill's level is only a lower bound (nothing harder was played) ...
UNTESTED_MARGIN = 0.25  # ... when the level is within this many stars of the hardest demand played

# the star ratings offered to compare with: every whole star below the comfort level, the comfort level, half
# stars up to 2★ above it, then the whole stars after that up to 13★
TARGET_STEP = 0.5
TARGET_AHEAD = 2.0
TARGET_RANGE = (1.0, 13.0)


def _level(skill: str, theta: float, ratio: float) -> tuple[float, str | None]:
    """The star rating whose typical maps demand ``2^ratio`` times what maps of ``theta`` do, and whether that is
    beyond the demand table (``"at_least"`` / ``"at_most"``)."""
    stars, beyond = stars_for(skill, log_demand(skill, theta) + ratio)
    if not beyond:
        return stars, None
    return stars, "at_least" if ratio > 0 else "at_most"


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


def _ratio_and_tested(skill: str, row: dict, theta: float) -> tuple[float | None, float | None, bool]:
    """(log2 of your ability over what is typical at θ, log2 of the hardest demand you played over it, whether you
    held nearly everything you played) for one comfort-level rating row."""
    if skill == "stamina":
        parts = [p for p in row.get("parts") or [] if p.get("maps", 0) >= MIN_MAPS and (p.get("measured") or 0) > 0]
        if not parts:
            return None, None, False
        exp = {p["duration"]: _expected("stamina", theta, duration=p["duration"]) for p in parts}
        ratio = sum(math.log2(p["measured"] / exp[p["duration"]]) for p in parts) / len(parts)
        tested = max(math.log2(max(p.get("tested_demand") or 0.0, 1e-6) / exp[p["duration"]]) for p in parts)
        return ratio, tested, all((p.get("success_share") or 0) >= HELD_ALL for p in parts)
    if skill == "accuracy":
        measured, windows = row.get("measured"), row.get("od_windows") or []
        if row.get("score") is None or measured is None or not windows or not math.isfinite(measured):
            return None, None, False
        return math.log2(_accuracy_sigma(theta) / _sigma_for(measured, windows)), None, False
    measured, expected = row.get("measured"), row.get("expected")
    if (row.get("maps") or 0) < MIN_MAPS or not measured or not expected or measured <= 0 or expected <= 0:
        return None, None, False
    if not (math.isfinite(measured) and math.isfinite(expected)):
        return None, None, False
    ratio = math.log2(measured / expected)
    if skill == "reading":  # its values are relative to the usual AR already: no comparable hardest demand
        return ratio, None, False
    tested = row.get("tested_demand")
    tested_ratio = math.log2(tested / expected) if tested and tested > 0 else None
    return ratio, tested_ratio, (row.get("success_share") or 0) >= HELD_ALL


def skill_levels(rows: dict[str, dict], theta: float | None) -> dict[str, dict | None]:
    """Each skill's star level from the comfort-level ratings (``theta`` = the comfort level they were made for):
    ``level`` (★), ``bound`` (``"at_least"`` when nothing harder was played or the level is beyond the demand
    table, ``"at_most"`` below it), ``tested`` (★ of the hardest demand played, when known) and ``ratio`` (log2 of
    your ability over what is typical at the comfort level). None: not enough data."""
    out: dict[str, dict | None] = {}
    for skill in SKILLS:
        row = rows.get(skill) or {}
        if theta is None or not math.isfinite(theta):
            out[skill] = None
            continue
        ratio, tested_ratio, held = _ratio_and_tested(skill, row, theta)
        if ratio is None:
            out[skill] = None
            continue
        level, bound = _level(skill, theta, ratio)
        tested = round(_level(skill, theta, tested_ratio)[0], 2) if tested_ratio is not None else None
        if bound is None and held and tested is not None and level >= tested - UNTESTED_MARGIN:
            bound = "at_least"  # you held (nearly) all of it: harder maps might go just as well
        out[skill] = {"level": round(level, 2), "bound": bound, "tested": tested, "ratio": round(ratio, 3)}
    return out


def compare_at(levels: dict[str, dict | None], target: float) -> dict:
    """The skills against typical maps of ``target`` ★: per skill the gap (★) and its bar, the effective level
    (soft minimum, weighted by how much those maps test each skill), the skill that limits it most and the chance
    to pass such a map cleanly."""
    skills = {}
    for skill in SKILLS:
        lv = levels.get(skill)
        if lv is None:
            skills[skill] = None
            continue
        gap = lv["level"] - target
        skills[skill] = {"gap": round(gap, 2), "score": round(max(0.0, min(100.0, 50 + POINTS_PER_STAR * gap)), 1)}
    known = {k: v["level"] for k, v in levels.items() if v is not None and k in PASS_SKILLS}
    weights = skill_weights(target)
    w = {k: weights.get(k, 0.0) for k in known if weights.get(k, 0.0) > 0}
    if not w:
        return {"target": target, "skills": skills, "effective": None, "limiting": None, "pass_chance": None}
    total = sum(w.values())
    parts = {k: w[k] / total * math.exp(-known[k] / SOFT_MIN) for k in w}
    effective = -SOFT_MIN * math.log(sum(parts.values()))
    limiting = max(parts, key=parts.get)
    z = (effective - target) / PASS_SPREAD + math.log(PASS_AT_LEVEL / (1 - PASS_AT_LEVEL))
    return {
        "target": target,
        "skills": skills,
        "effective": round(effective, 2),
        "limiting": limiting,
        "pass_chance": round(1 / (1 + math.exp(-max(-35.0, min(35.0, z)))), 4),
    }


def targets(comfort: float) -> list[float]:
    """The star ratings to compare with (:data:`TARGET_STEP`, :data:`TARGET_AHEAD`, :data:`TARGET_RANGE`)."""
    lo, hi = TARGET_RANGE
    base = round(min(max(comfort, lo), hi), 1)
    top = min(base + TARGET_AHEAD, hi)
    out = [float(s) for s in range(math.ceil(lo), math.floor(base - TARGET_STEP + 1e-9) + 1)]
    v = base
    while v < top - 1e-9:
        out.append(round(v, 1))
        v = round(v + TARGET_STEP, 1)
    if top - out[-1] < TARGET_STEP / 2 and out[-1] != base:
        out[-1] = round(top, 1)  # the top instead of a half step right next to it
    else:
        out.append(round(top, 1))
    # whole stars beyond that (not one right next to the last half step)
    out += [float(s) for s in range(math.floor(top) + 1, int(hi) + 1) if s > top + TARGET_STEP / 2]
    return out


def default_target(comfort: float) -> float:
    """One star above the comfort level (or the highest one offered)."""
    lo, hi = TARGET_RANGE
    base = round(min(max(comfort, lo), hi), 1)
    return round(min(base + 1.0, hi), 1)
