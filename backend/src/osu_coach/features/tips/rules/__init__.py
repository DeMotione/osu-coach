"""Tips engine: turns a replay profile + the player's setup into concrete advice.

``make_tips``: what to practise, each tip with the evidence measured from the replays and concrete actions.
``setup_advice``: what to change in the setup (tablet area or sensitivity, audio offset, keys), with the exact new
values, and only when the replays show it is big enough to feel and costs you (:mod:`.setup`).
"""

from __future__ import annotations

from osu_coach.features.tips.rules.common import Tip
from osu_coach.features.tips.rules.engine import make_tips, practice_plan
from osu_coach.features.tips.rules.setup import mm_per_osu_px, setup_advice

__all__ = [
    "Tip",
    "make_tips",
    "mm_per_osu_px",
    "practice_plan",
    "setup_advice",
]
