"""The comfort engine: each skill's best plays per map/mod setup against what is typical at the comfort level."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.player.engines.base import COMFORT, Rated
from osu_coach.domain.player.engines.comfort.ratings import combine_ratings, strengths_and_weaknesses
from osu_coach.domain.player.engines.comfort.readiness import Readiness, compare_at

if TYPE_CHECKING:
    from osu_coach.domain.player.summary import PlaySummary


class ComfortEngine:
    """The comfort-based ratings of :func:`ratings.combine_ratings`."""

    name = COMFORT

    def rate(self, summaries: Sequence[PlaySummary], replays: Sequence[ReplayMeta], comfort: float | None) -> Rated:
        skills = combine_ratings([sm.ratings for sm in summaries], replays, comfort)
        strengths, weaknesses = strengths_and_weaknesses(skills)
        return Rated(engine=self.name, skills=skills, strengths=strengths, weaknesses=weaknesses)

    def compare_at(self, rated: Rated, comfort: float, target: float) -> Readiness:
        return compare_at(rated.skills, comfort, target)
