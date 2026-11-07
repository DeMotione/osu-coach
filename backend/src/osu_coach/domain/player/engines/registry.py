"""Picking an engine by name; an unknown name is ``comfort``."""

from __future__ import annotations

from osu_coach.domain.player.engines.base import COMFORT, ENGINES, IRT, Rated, RatingEngine
from osu_coach.domain.player.engines.comfort.engine import ComfortEngine
from osu_coach.domain.player.engines.comfort.readiness import Readiness
from osu_coach.domain.player.engines.irt.engine import IrtEngine


def engine_name(name: str | None) -> str:
    """A known engine name; anything else is ``comfort``."""
    return name if name in ENGINES else COMFORT


def make_engine(name: str | None = None) -> RatingEngine:
    """The engine called ``name`` (``comfort`` for an unknown name)."""
    if engine_name(name) == IRT:
        return IrtEngine()
    return ComfortEngine()


def compare(rated: Rated, comfort: float, target: float) -> Readiness:
    """The :class:`Readiness` for maps of ``target`` ★, worked out by the engine that made ``rated``."""
    return make_engine(rated.engine).compare_at(rated, comfort, target)
