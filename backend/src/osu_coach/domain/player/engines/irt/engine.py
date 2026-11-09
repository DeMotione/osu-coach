"""The Star-Scale IRT engine: the fit turned into the app's skill ratings.

Spec and why it differs from it: docs/star-scale-irt.md.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

import numpy as np

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.player.engines.base import IRT, Rated, measured_scores
from osu_coach.domain.player.engines.consistency import star_consistency
from osu_coach.domain.player.engines.demand import log_demand
from osu_coach.domain.player.engines.irt import constants as K
from osu_coach.domain.player.engines.irt import tables
from osu_coach.domain.player.engines.irt.anchors import UNITS, natural_at
from osu_coach.domain.player.engines.irt.fit import IrtFit, SkillFit, fit, held_bound
from osu_coach.domain.player.engines.irt.merge import Merged, merge
from osu_coach.domain.player.engines.ranking import strengths_and_weaknesses
from osu_coach.domain.player.engines.readiness import SKILLS as READINESS_SKILLS
from osu_coach.domain.player.engines.readiness import Readiness, SkillAt, readiness
from osu_coach.domain.player.engines.skill_scale import speed_rating
from osu_coach.domain.player.levels import comfort as comfort_of
from osu_coach.domain.player.messages import Message
from osu_coach.domain.player.records import SkillRating

if TYPE_CHECKING:
    from osu_coach.domain.player.summary import PlaySummary

POINTS_PER_STAR = 20.0  # around 50
CURVE = 100 / (4 * POINTS_PER_STAR)  # ★: the S-curve's width for that slope at 50
FALLBACK_STARS = 4.0
CALIBRATION_RANGE = 30.0  # ★ either side of the level searched for a skill's reference


def adapter(stars: float, reference: float) -> float:
    """0–100 score of an ability against a reference: an S-curve, 50 at the reference, kept within 1–99."""
    # shown as whole numbers: kept within 1–99, so rounding never makes a 0 or a 100
    return min(99.0, max(1.0, round(100 / (1 + math.exp(-(stars - reference) / CURVE)), 1)))


def prior_centre(replays: Sequence[ReplayMeta], comfort: float | None) -> float:
    """The prior centre: the comfort level, else the provisional one, else the median stars played."""
    if comfort is not None and math.isfinite(comfort):
        return float(comfort)
    found = comfort_of(tuple(replays)).stars if replays else None
    if found is not None and math.isfinite(found):
        return float(found)
    stars = [m.stars for m in replays if m.stars is not None and math.isfinite(m.stars)]
    return float(np.median(stars)) if stars else FALLBACK_STARS


def _fail_share(theta: float, b: np.ndarray, w: np.ndarray, a: float, c: float) -> float:
    q = 1 / (1 + np.exp(np.clip(c + a * (theta - b), -700, 700)))
    return float((q * w).sum() / w.sum())


def calibration(merged: Merged, level: float) -> dict[str, float]:
    """Per skill, the ability that fails the skill's anchor share of its notes on maps of ``level``.

    Every play's notes are shifted to the level; only the maps' content counts, not hits and misses.
    """
    out: dict[str, float] = {}
    for key in (*K.SKILLS, "acc"):
        bs, ws = [], []
        for part, stars in zip(merged.parts, merged.part_stars, strict=True):
            if not math.isfinite(stars):
                continue
            rows = part.take(part.kind == K.ACCURACY) if key == "acc" else part.take(part.kind != K.TIMING)
            b = rows.b_acc if key == "acc" else getattr(rows, f"b_{key}")
            ok = np.isfinite(b) & (rows.n > 0)
            bs.append(b[ok] - stars + level)
            ws.append(rows.n[ok])
        b = np.concatenate(bs) if bs else np.zeros(0)
        w = np.concatenate(ws) if ws else np.zeros(0)
        if not len(b) or w.sum() <= 0:
            out[key] = level
            continue
        if key == "acc":
            a, c, share = K.A_ACC, K.C_ACC, 1 - K.PI_ACC
        else:
            a, c, share = float(K.A[K.SKILLS.index(key)]), K.C, 1 - K.PI
        lo, hi = level - CALIBRATION_RANGE, level + CALIBRATION_RANGE  # the share falls as θ rises
        for _ in range(60):
            mid = (lo + hi) / 2
            if _fail_share(mid, b, w, a, c) > share:
                lo = mid
            else:
                hi = mid
        out[key] = (lo + hi) / 2
    return out


def state_of(s: SkillFit) -> str:
    # nothing held: no tested difficulty, so no number
    if s.items <= 0 or not math.isfinite(s.tested):
        return "not_enough_data"
    if s.theta > s.tested:
        return "untested"  # a lower bound, even when too unsure to place
    if s.se > K.PROVISIONAL_SE:
        return "not_enough_data"
    if s.se > K.MEASURED_SE or s.modes is not None:
        return "provisional"
    return "measured"


def _rating(
    key: str,
    s: SkillFit | None,
    level: float,
    reference: float,
    bound: float,
    maps: float | None = None,
) -> SkillRating:
    """One skill's rating; its star values are kept on the level's scale (θ − R + L)."""
    app = K.APP_KEYS[key]
    anchor = K.ANCHOR_OF[key]
    if s is None:
        return SkillRating(score=None, maps=0, reason=Message("irt_failed"), state="failed")
    state = state_of(s)
    shift = level - reference  # from the skill's own scale to the level's
    low, high = s.theta - K.Z90 * s.se, s.theta + K.Z90 * s.se
    if s.modes is not None:
        low, high = min(low, s.modes[0] - K.Z90 * s.se), max(high, s.modes[1] + K.Z90 * s.se)
    common = dict(
        maps=int(round(s.plays)),
        natural_unit=UNITS[anchor],
        tested_demand=round(s.tested + shift, 2) if math.isfinite(s.tested) else None,
        expected=level,
    )
    if state in ("measured", "provisional"):
        return SkillRating(
            score=adapter(s.theta, reference),
            reason=Message(f"irt_{state}"),
            state=state,
            stars=round(s.theta + shift, 2),
            stars_low=round(low + shift, 2),
            stars_high=round(high + shift, 2),
            measured=round(s.theta + shift, 3),
            natural=round(natural_at(s.theta, tables.NATURAL[anchor]), 2),
            **common,
        )
    if state == "untested" and math.isfinite(bound):
        # held almost everything: score the hardest band held, as a lower bound
        score = adapter(bound, reference)
        return SkillRating(
            score=score,
            at_least=score,
            reason=Message("irt_untested", {"skill": app, "maps": maps}),
            needs=Message("irt_play_harder", {"skill": app, "level": level + 1}),
            state="untested",
            stars=round(bound + shift, 2),
            stars_low=round(bound + shift, 2),
            measured=round(bound + shift, 3),
            **common,
        )
    return SkillRating(
        score=None,
        reason=Message("irt_not_enough"),
        needs=Message("irt_play_at", {"skill": app, "level": level}),
        state="not_enough_data",
        **common,
    )


def hard_maps(summaries: Sequence[PlaySummary]) -> dict[str, float]:
    """Per skill: the 90th percentile of the star ratings of the plays that test it."""
    stars_of: dict[str, list[float]] = {}
    for sm in summaries:
        stars = sm.meta.stars
        if stars is None or not math.isfinite(stars):
            continue
        g = sm.irt
        tested = {k: bool(np.isfinite(getattr(g, f"b_{k}")).any()) for k in K.SKILLS}
        tested["acc"] = bool((g.kind == K.ACCURACY).any())
        for k, has in tested.items():
            if has:
                stars_of.setdefault(k, []).append(float(stars))
    return {k: float(np.quantile(v, 0.9)) for k, v in stars_of.items()}


class IrtEngine:
    """Star-Scale IRT (experimental)."""

    name = IRT
    uses_level = False  # each skill is measured against the maps themselves, not against a level

    def fit(self, summaries: Sequence[PlaySummary], prior: float) -> IrtFit:
        return self.fit_merged(merge([(sm.meta, sm.irt) for sm in summaries]), prior)

    @staticmethod
    def fit_merged(merged: Merged, prior: float) -> IrtFit:
        return fit(merged.groups, prior, merged.plays, merged.parts)

    def rate(self, summaries: Sequence[PlaySummary], replays: Sequence[ReplayMeta], comfort: float | None) -> Rated:
        level = prior_centre(replays, comfort)
        merged = merge([(sm.meta, sm.irt) for sm in summaries])
        result = self.fit_merged(merged, level)
        references = calibration(merged, level)
        maps = hard_maps(summaries)
        skills: dict[str, SkillRating] = {}
        for key in (*K.SKILLS, "acc"):
            s = result.skills.get(key) if result.converged else None
            bound = held_bound(merged.groups, key)
            skills[K.APP_KEYS[key]] = _rating(key, s, level, references[key], bound, maps.get(key))
        skills["consistency"] = star_consistency(replays, comfort, comfort=True)
        order = ("aim", "flow_aim", "speed", "stamina", "accuracy", "sliders", "reading", "consistency")
        skills = {k: skills[k] for k in order}
        strengths, weaknesses = strengths_and_weaknesses(skills)
        return Rated(
            engine=self.name,
            skills=skills,
            strengths=strengths,
            weaknesses=weaknesses,
            reference=level,
        )

    def compare_at(self, rated: Rated, comfort: float, target: float) -> Readiness:
        """The scores on typical maps of ``target`` ★."""
        skills: dict[str, SkillAt | None] = {}
        for key in READINESS_SKILLS:
            row = rated.skills.get(key)
            demand = round(2 ** (log_demand(key, target) - log_demand(key, comfort)), 3)
            if row is None or row.score is None or row.measured is None:
                skills[key] = None
                continue
            score = adapter(row.measured, target)
            bound = score if row.at_least is not None else None
            skills[key] = SkillAt(score=score, change=round(score - row.score, 1), demand=demand, at_least=bound)
        return readiness(comfort, target, skills)

    def map_scores(self, skills: Mapping[str, SkillRating], theta: float) -> dict[str, float]:
        out = {k: float(v) for k, v in measured_scores(skills).items() if v is not None}
        # the recommender reads tapping speed on the tempo scale, so it comes from the BPM measured
        speed = skills.get("speed")
        if "speed" in out and speed is not None and speed.natural is not None and math.isfinite(speed.natural):
            out["speed"] = round(speed_rating(float(speed.natural), theta), 1)
        return out
