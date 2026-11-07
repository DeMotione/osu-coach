"""The comfort engine: each skill's best plays per map/mod setup against what is typical at the comfort level."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.player.engines.base import COMFORT, Rated, measured_scores
from osu_coach.domain.player.engines.comfort.ratings import combine_ratings
from osu_coach.domain.player.engines.comfort.readiness import compare_at
from osu_coach.domain.player.engines.ranking import strengths_and_weaknesses

if TYPE_CHECKING:
    from osu_coach.domain.player.engines.readiness import Readiness
    from osu_coach.domain.player.records import SkillRating
    from osu_coach.domain.player.summary import PlaySummary


class ComfortEngine:
    """The comfort-based ratings of :func:`ratings.combine_ratings`."""

    name = COMFORT
    uses_level = True

    def rate(self, summaries: Sequence[PlaySummary], replays: Sequence[ReplayMeta], comfort: float | None) -> Rated:
        skills = combine_ratings([sm.ratings for sm in summaries], replays, comfort)
        strengths, weaknesses = strengths_and_weaknesses(skills)
        return Rated(engine=self.name, skills=skills, strengths=strengths, weaknesses=weaknesses)

    def compare_at(self, rated: Rated, comfort: float, target: float) -> Readiness:
        return compare_at(rated.skills, comfort, target)

    def map_scores(self, skills: Mapping[str, SkillRating], theta: float) -> dict[str, float]:
        return {k: float(v) for k, v in measured_scores(skills).items() if v is not None}
