"""The comfort engine's readiness for another star rating: its comfort-level scores moved to it.

The comfort-level ratings (:func:`ratings.ratings`) score each skill against what is typical at the comfort
level θ: ``50 + P_k · log2(measured / expected)`` (``P_k`` points per doubling). The demand curves (:mod:`..demand`)
say how much more typical maps of another star rating T demand of the skill, ``ΔD_k = D_k(T) − D_k(θ)`` (log2).
Together::

    score at T     s_k(T) = clip(s_k(θ) − P_k · ΔD_k, 0, 100)    the comfort score, minus what T★ maps demand more

So every score falls as the star rating rises, each by how much more its maps demand (accuracy: the same hit-error
spread in a narrower 300 window), and rises on easier maps. The pass chance: :mod:`..readiness`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from osu_coach.domain.player.engines.comfort.ratings import ACCURACY_TRANSITION_STARS, POINTS
from osu_coach.domain.player.engines.demand import log_demand
from osu_coach.domain.player.engines.readiness import SKILLS, Readiness, SkillAt, readiness
from osu_coach.domain.player.records import UNRATED, SkillRating


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


def _accuracy_drop(row: SkillRating, theta: float, ratio: float) -> float | None:
    """Accuracy points lost when the 300 window is ``ratio`` times narrower: the same hit-error spread gives a larger
    non-300 share."""
    measured, windows = row.measured, row.od_windows or []
    if measured is None or not windows or not math.isfinite(measured):
        return None
    measured = max(measured, 1e-6)
    sigma = _sigma_for(measured, windows)
    total = sum(w for _, w in windows) or 1.0
    share = sum(w * math.erfc(win / ratio / (math.sqrt(2) * sigma)) for win, w in windows) / total
    points = POINTS["accuracy"] + 5 * min(1.0, max(0.0, ACCURACY_TRANSITION_STARS - theta))
    return points * math.log2(max(share, 1e-6) / measured)


def scores_at(rows: Mapping[str, SkillRating], theta: float | None, target: float) -> dict[str, SkillAt | None]:
    """The comfort-level scores at ``target`` ★ (:class:`SkillAt`); None: no comfort-level score."""
    out: dict[str, SkillAt | None] = {}
    for skill in SKILLS:
        row = rows.get(skill, UNRATED)
        base = row.score
        if theta is None or base is None or not math.isfinite(theta):
            out[skill] = None
            continue
        ratio = 2 ** (log_demand(skill, target) - log_demand(skill, theta))
        drop = _accuracy_drop(row, theta, ratio) if skill == "accuracy" else POINTS[skill] * math.log2(ratio)
        if drop is None:
            out[skill] = None
            continue
        score = round(max(0.0, min(100.0, base - drop)), 1)
        out[skill] = SkillAt(score=score, change=round(score - base, 1), demand=round(ratio, 3))
    return out


def compare_at(rows: Mapping[str, SkillRating], theta: float, target: float) -> Readiness:
    """The :class:`Readiness` for maps of ``target`` ★ (the skills: :func:`scores_at`)."""
    return readiness(theta, target, scores_at(rows, theta, target))
