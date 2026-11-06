"""What every rating engine is: a :class:`RatingEngine` turns the plays into :class:`Rated` skill ratings.

Every engine fills the same eight skills on the same 0–100 scale, so every page reads any engine's ratings alike.
Neither 50 is "a typical player": Comfort Score scores against what the comfort level's maps are assumed to demand,
Star-Scale IRT against maps of the player's level (and shows each skill as the map star rating it holds up on). Engines: ``comfort`` (:mod:`.comfort`) and ``irt`` (Star-Scale IRT, :mod:`.irt`,
experimental).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.player.records import SkillRating

if TYPE_CHECKING:
    from osu_coach.domain.player.engines.comfort.readiness import Readiness
    from osu_coach.domain.player.summary import PlaySummary

COMFORT = "comfort"
IRT = "irt"
ENGINES = (COMFORT, IRT)
ENGINE_LABELS = {COMFORT: "Comfort Score", IRT: "Star Levels (experimental)"}  # IRT's spec: Star-Scale IRT


@dataclass(frozen=True, slots=True)
class Rated:
    """What an engine gives the profile: the skill ratings and the skills to show as strong and to work on."""

    engine: str
    skills: dict[str, SkillRating] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    reference: float | None = None  # ★ the 0–100 scores are relative to (the comfort level, or its stand-in)
    fit: Any = field(default=None, repr=False)  # the engine's own state, for later questions (IRT: its IrtFit)


def measured_scores(skills: Mapping[str, SkillRating]) -> dict[str, float | None]:
    """The scores that are measurements: IRT lower bounds (``untested``) are left out."""
    return {k: (None if row.state == "untested" else row.score) for k, row in skills.items()}


class RatingEngine(Protocol):
    name: str

    def rate(self, summaries: Sequence[PlaySummary], replays: Sequence[ReplayMeta], comfort: float | None) -> Rated:
        """The ratings of these plays against the comfort level ``comfort`` (★; None: not measured)."""
        ...

    def compare_at(self, rated: Rated, comfort: float, target: float) -> Readiness:
        """The skills on typical maps of ``target`` ★ and the chance to pass them."""
        ...
