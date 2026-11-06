"""The tips engine: ``make_tips`` runs every rule on a profile and the player's setup; ``practice_plan``.

What to change in the setup itself is in :mod:`.setup`, not here."""

from __future__ import annotations

import logging
import math

from osu_coach.common.texts import SKILL_LABELS
from osu_coach.domain.player import Profile
from osu_coach.domain.player.setup import Setup
from osu_coach.features.tips.rules.aim import direction_tips, distance_angle_tips, miss_cause_tip, quadrant_tips
from osu_coach.features.tips.rules.common import Tip
from osu_coach.features.tips.rules.skills import consistency_tips, reading_tips, slider_tips
from osu_coach.features.tips.rules.tapping import key_usage_tips, stream_tips, timing_tips

log = logging.getLogger(__name__)


def make_tips(p: Profile, setup: Setup | None = None) -> list[Tip]:
    setup = setup or Setup()
    tips: list[Tip] = []
    for rule in (
        miss_cause_tip,
        quadrant_tips,
        direction_tips,
        distance_angle_tips,
        timing_tips,
        stream_tips,
        key_usage_tips,
        slider_tips,
        reading_tips,
        consistency_tips,
    ):
        try:
            out = rule(p, setup)
        except Exception as exc:  # noqa: BLE001 - one bad rule must not hide the others
            log.exception("tip rule %s failed", rule.__name__)
            out = [Tip("Internal", f"Could not evaluate {rule.__name__}", 1, str(exc))]
        tips.extend(out or [])
    tips.sort(key=lambda t: -t.severity)
    return tips


def practice_plan(p: Profile) -> list[str]:
    """A simple daily routine built around the weakest skills."""
    comfort = p.levels.comfort_stars
    lvl = f"{comfort:.1f}★" if comfort and not math.isnan(comfort) else "your comfort level"
    if p.weaknesses:
        focus = (
            f"Focus block (20-30 min): the '{SKILL_LABELS[p.weaknesses[0]]}' playlist from Goals & Training — "
            "repeat each map until the target in the playlist note is met."
        )
    else:  # no skill is rated yet: nothing to name
        focus = (
            f"Focus block (20-30 min): maps around {lvl} from Goals & Training — repeat each map until you pass it "
            "cleanly; your skill scores (and a playlist for the weakest) come with a few more passes."
        )
    return [
        f"Warm-up (10 min): 2-3 maps about 1★ below {lvl}, aiming for full combos.",
        focus,
        f"Push (10 min): one or two maps slightly above {lvl}.",
        "Cool-down: replay a favourite map for fun.",
        "Re-run the analysis after ~20 new replays and compare the scores.",
    ]
