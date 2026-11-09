"""Rating engines: swappable ways to turn the plays into the skill ratings.

* :mod:`.base` — what an engine is (:class:`RatingEngine`) and gives (:class:`Rated`);
* :mod:`.registry` — picking one by name (:func:`make_engine`);
* shared by every engine: :mod:`.readiness` (other star ratings, the pass chance), :mod:`.demand` (the map pool's
  demand curves), :mod:`.consistency`, :mod:`.ranking` (strengths and weaknesses), :mod:`.skill_scale` (the tempo
  scale map suggestions read);
* :mod:`.comfort` — the comfort-based 0–100 ratings;
* :mod:`.irt` — Star-Scale IRT, skills in stars (experimental; ``docs/star-scale-irt.md``).
"""

from osu_coach.domain.player.engines.base import (
    COMFORT,
    ENGINE_LABELS,
    ENGINES,
    IRT,
    Rated,
    RatingEngine,
    measured_scores,
)
from osu_coach.domain.player.engines.comfort.engine import ComfortEngine
from osu_coach.domain.player.engines.registry import compare, engine_name, make_engine

__all__ = [
    "COMFORT",
    "ENGINES",
    "ENGINE_LABELS",
    "IRT",
    "ComfortEngine",
    "Rated",
    "RatingEngine",
    "compare",
    "engine_name",
    "make_engine",
    "measured_scores",
]
