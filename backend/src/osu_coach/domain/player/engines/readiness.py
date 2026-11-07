"""Readiness for another star rating, as every engine gives it: each skill on typical maps of that star rating, the
weakest of them, and the chance to pass such a map cleanly.

Each engine moves its own scores to the target T (:meth:`RatingEngine.compare_at`); the pass chance is the same for
every engine::

    clean pass     P(T) = σ(logit(p₀) − (T − θ) / τ)              p₀ at the comfort level θ

The comfort level is made of clean passes (its 75th percentile), so the pass chance is p₀ there and falls with every
star above it. Consistency has its own card and is left out. Star ratings more than :data:`MAX_GAP` above the comfort
level are too far to compare.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

SKILLS = ("aim", "flow_aim", "speed", "stamina", "accuracy", "sliders", "reading")
PASS_SPREAD = 0.6  # ★: a star above the comfort level takes the pass chance from 75% to ~36%, two stars to ~10%
PASS_AT_LEVEL = 0.75  # clean-pass chance on maps of the comfort level (a 75th percentile of clean passes)

# the star ratings offered to compare with: every whole star from 1★ to 13★ and half stars near the comfort level;
# those more than MAX_GAP above it are shown locked
MAX_GAP = 2.0
TARGET_STEP = 0.5
TARGET_RANGE = (1.0, 13.0)


@dataclass(frozen=True, slots=True)
class SkillAt:
    """A comfort-level score moved to another star rating: ``score`` (0–100), ``change`` (points against the
    comfort level) and ``demand`` (how many times what comfort-level maps demand). Without a score, ``at_least``
    can still say how good the skill is at least there (an untested skill whose engine can move its bound)."""

    score: float | None
    change: float | None
    demand: float
    at_least: float | None = None


@dataclass(frozen=True, slots=True)
class Readiness:
    """The skills on typical maps of ``target`` ★ (None: no comfort-level score), the lowest of them and the chance
    to pass such a map cleanly."""

    target: float
    skills: dict[str, SkillAt | None]
    weakest: str | None
    pass_chance: float


def pass_chance(comfort: float, target: float) -> float:
    """The chance to pass a typical map of ``target`` ★ cleanly, from the comfort level ``comfort``."""
    z = math.log(PASS_AT_LEVEL / (1 - PASS_AT_LEVEL)) - (target - comfort) / PASS_SPREAD
    return round(1 / (1 + math.exp(-max(-35.0, min(35.0, z)))), 4)


def readiness(comfort: float, target: float, skills: Mapping[str, SkillAt | None]) -> Readiness:
    """The :class:`Readiness` for maps of ``target`` ★ from an engine's skills moved there."""
    known = {k: v.score for k, v in skills.items() if v is not None and v.score is not None}
    return Readiness(
        target=target,
        skills=dict(skills),
        weakest=min(known, key=known.__getitem__) if known else None,
        pass_chance=pass_chance(comfort, target),
    )


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
    """The star rating shown first: the comfort level itself (to 0.1★, within 1–13★)."""
    base, _ = _half_star_below(comfort)
    return base
