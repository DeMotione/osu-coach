"""Rating engines: swappable ways to turn the plays into the skill ratings.

Every engine fills the same eight skills on the same 0–100 scale (50 = typical at the comfort level), so every page
reads any engine's ratings alike. ``classic`` is the comfort-relative rating of :mod:`ratings`; ``irt`` (Star-Scale
IRT, ``docs/star-scale-irt.md``) is experimental. An unknown name falls back to ``classic``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.player.ratings import RatingInputs, combine_ratings, strengths_and_weaknesses
from osu_coach.domain.player.readiness import Readiness, compare_at
from osu_coach.domain.player.records import SkillRating

if TYPE_CHECKING:
    from osu_coach.domain.player.summary import PlaySummary

CLASSIC = "classic"
IRT = "irt"
ENGINES = (CLASSIC, IRT)
ENGINE_LABELS = {CLASSIC: "Classic", IRT: "Star-Scale IRT (experimental)"}


@dataclass(frozen=True, slots=True)
class Rated:
    """What an engine gives the profile: the skill ratings and the skills to show as strong and to work on."""

    engine: str
    skills: dict[str, SkillRating] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)


class RatingEngine(Protocol):
    name: str

    def rate(self, summaries: Sequence[PlaySummary], replays: Sequence[ReplayMeta], comfort: float | None) -> Rated:
        """The ratings of these plays against the comfort level ``comfort`` (★; None: not measured)."""
        ...

    def compare_at(self, rated: Rated, comfort: float, target: float) -> Readiness:
        """The skills on typical maps of ``target`` ★ and the chance to pass them."""
        ...


class ClassicEngine:
    """The comfort-relative ratings (:func:`ratings.combine_ratings`): each skill's best plays per map/mod setup
    against what is typical at the comfort level."""

    name = CLASSIC

    def rate(self, summaries: Sequence[PlaySummary], replays: Sequence[ReplayMeta], comfort: float | None) -> Rated:
        inputs: list[RatingInputs] = [sm.ratings for sm in summaries]
        skills = combine_ratings(inputs, replays, comfort)
        strengths, weaknesses = strengths_and_weaknesses(skills)
        return Rated(engine=self.name, skills=skills, strengths=strengths, weaknesses=weaknesses)

    def compare_at(self, rated: Rated, comfort: float, target: float) -> Readiness:
        return compare_at(rated.skills, comfort, target)


def compare(rated: Rated, comfort: float, target: float) -> Readiness:
    """The :class:`Readiness` for maps of ``target`` ★, worked out by the engine that made ``rated``."""
    return make_engine(rated.engine).compare_at(rated, comfort, target)


def engine_name(name: str | None) -> str:
    """A known engine name; anything else is ``classic``."""
    return name if name in ENGINES else CLASSIC


def make_engine(name: str | None = None) -> RatingEngine:
    """The engine called ``name`` (``classic`` for an unknown name, and for ``irt`` until it is built)."""
    return ClassicEngine()
