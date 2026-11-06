"""The Star-Scale IRT engine: the fit (:mod:`.fit`) turned into the app's eight skill ratings.

Every skill keeps its ability in stars (``SkillRating.stars``, with a 90% range) and gets a 0–100 score by the
adapter ``clip(50 + 20·(θ − L), 0, 100)``, L the comfort level: the same 20 points per star the map suggestions use,
so "ability ≥ a map's demand" means "θ ≥ the map's difficulty" in both engines.

States (spec §9 and the review's fixes, ``docs/star-scale-irt.md``):

* ``measured`` (SE ≤ 0.35★) and ``provisional`` (SE ≤ 0.75★, or two answers fit about as well): scored;
* ``untested``: the fit lands above the hardest difficulty the player held (95th percentile) — shown as "at least"
  that, never as the fitted value (fix 1);
* ``not_enough_data``: SE above 0.75★ (the prior is doing the work);
* ``failed``: the solver didn't converge — no number at all (fix 4).

Consistency keeps the comfort engine's measure (combo and accuracy held map to map, fix 13).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.player.engines.base import IRT, Rated
from osu_coach.domain.player.engines.comfort.consistency import star_consistency
from osu_coach.domain.player.engines.comfort.demand import log_demand
from osu_coach.domain.player.engines.comfort.ratings import strengths_and_weaknesses
from osu_coach.domain.player.engines.comfort.readiness import (
    PASS_AT_LEVEL,
    PASS_SPREAD,
    Readiness,
    SkillAt,
)
from osu_coach.domain.player.engines.comfort.readiness import (
    SKILLS as READINESS_SKILLS,
)
from osu_coach.domain.player.engines.irt import constants as K
from osu_coach.domain.player.engines.irt import tables
from osu_coach.domain.player.engines.irt.anchors import UNITS, natural_at
from osu_coach.domain.player.engines.irt.fit import IrtFit, SkillFit, fit
from osu_coach.domain.player.engines.irt.merge import merge
from osu_coach.domain.player.levels import comfort as comfort_of
from osu_coach.domain.player.messages import Message
from osu_coach.domain.player.records import SkillRating

if TYPE_CHECKING:
    from osu_coach.domain.player.summary import PlaySummary

POINTS_PER_STAR = 20.0
FALLBACK_STARS = 4.0


def adapter(stars: float, reference: float) -> float:
    """The 0–100 score of an ability of ``stars`` ★ against the reference level."""
    return round(float(np.clip(50 + POINTS_PER_STAR * (stars - reference), 0, 100)), 1)


def prior_centre(replays: Sequence[ReplayMeta], comfort: float | None) -> float:
    """The prior centre L (fix 8): the comfort level; else the provisional one; else the median star rating played;
    else 4★."""
    if comfort is not None and math.isfinite(comfort):
        return float(comfort)
    found = comfort_of(tuple(replays)).stars if replays else None
    if found is not None and math.isfinite(found):
        return float(found)
    stars = [m.stars for m in replays if m.stars is not None and math.isfinite(m.stars)]
    return float(np.median(stars)) if stars else FALLBACK_STARS


def state_of(s: SkillFit) -> str:
    # nothing held at all (every item failed): there is no tested difficulty to cap by, so no number either
    if s.items <= 0 or s.se > K.PROVISIONAL_SE or not math.isfinite(s.tested):
        return "not_enough_data"
    if math.isfinite(s.tested) and s.theta > s.tested:
        return "untested"
    if s.se > K.MEASURED_SE or s.modes is not None:
        return "provisional"
    return "measured"


def _rating(key: str, s: SkillFit | None, reference: float) -> SkillRating:
    app = K.APP_KEYS[key]
    anchor = K.ANCHOR_OF[key]
    if s is None:
        return SkillRating(score=None, maps=0, reason=Message("irt_failed"), state="failed")
    state = state_of(s)
    low, high = s.theta - K.Z90 * s.se, s.theta + K.Z90 * s.se
    if s.modes is not None:
        low, high = min(low, s.modes[0] - K.Z90 * s.se), max(high, s.modes[1] + K.Z90 * s.se)
    shown = s.tested if state == "untested" else s.theta
    common = dict(
        maps=int(round(s.plays)),
        state=state,
        stars=round(shown, 2),
        stars_low=round(low, 2) if state != "untested" else round(s.tested, 2),
        stars_high=round(high, 2) if state != "untested" else None,
        natural=round(natural_at(shown, tables.NATURAL[anchor]), 2),
        natural_unit=UNITS[anchor],
        tested_demand=round(s.tested, 2) if math.isfinite(s.tested) else None,
        measured=round(s.theta, 3),
        expected=reference,
    )
    if state in ("measured", "provisional"):
        return SkillRating(score=adapter(s.theta, reference), reason=Message(f"irt_{state}"), **common)
    if state == "untested":
        return SkillRating(
            score=None,
            at_least=adapter(s.tested, reference),
            reason=Message("irt_untested", {"tested": s.tested}),
            needs=Message("irt_play_harder", {"skill": app, "stars": s.tested}),
            **common,
        )
    return SkillRating(
        score=None,
        reason=Message("irt_not_enough"),
        needs=Message("irt_play_at", {"skill": app, "stars": reference}),  # where the player's level is
        **common,
    )


class IrtEngine:
    """Star-Scale IRT (experimental)."""

    name = IRT

    def fit(self, summaries: Sequence[PlaySummary], prior: float) -> IrtFit:
        merged = merge([(sm.meta, sm.irt) for sm in summaries])
        return fit(merged.groups, prior, merged.plays)

    def rate(self, summaries: Sequence[PlaySummary], replays: Sequence[ReplayMeta], comfort: float | None) -> Rated:
        reference = prior_centre(replays, comfort)
        result = self.fit(summaries, reference)
        skills: dict[str, SkillRating] = {}
        for key in (*K.SKILLS, "acc"):
            s = result.skills.get(key) if result.converged else None
            skills[K.APP_KEYS[key]] = _rating(key, s, reference)
        skills["consistency"] = star_consistency(replays, comfort, comfort=True)
        order = ("aim", "flow_aim", "speed", "stamina", "accuracy", "sliders", "reading", "consistency")
        skills = {k: skills[k] for k in order}
        strengths, weaknesses = strengths_and_weaknesses(skills)
        return Rated(
            engine=self.name,
            skills=skills,
            strengths=strengths,
            weaknesses=weaknesses,
            reference=reference,
            fit=result,
        )

    def compare_at(self, rated: Rated, comfort: float, target: float) -> Readiness:
        """A typical map of ``target`` ★ demands ``target`` ★ of every skill (that is how the anchors are made), so
        a skill's score there is the adapter against ``target``."""
        skills: dict[str, SkillAt | None] = {}
        for key in READINESS_SKILLS:
            row = rated.skills.get(key)
            if row is None or row.score is None or row.measured is None:
                skills[key] = None
                continue
            base = row.score
            score = adapter(row.measured, target)
            demand = 2 ** (log_demand(key, target) - log_demand(key, comfort))
            skills[key] = SkillAt(score=score, change=round(score - base, 1), demand=round(demand, 3))
        known = {k: v.score for k, v in skills.items() if v is not None}
        z = math.log(PASS_AT_LEVEL / (1 - PASS_AT_LEVEL)) - (target - comfort) / PASS_SPREAD
        return Readiness(
            target=target,
            skills=skills,
            weakest=min(known, key=known.__getitem__) if known else None,
            pass_chance=round(1 / (1 + math.exp(-max(-35.0, min(35.0, z)))), 4),
        )
