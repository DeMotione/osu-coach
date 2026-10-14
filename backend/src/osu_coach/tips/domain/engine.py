"""The tips engine: ``make_tips`` runs every rule on a profile and the player's setup; ``practice_plan``."""
from __future__ import annotations

import math
from osu_coach.profile.domain import Profile, SKILL_LABELS
from osu_coach.settings.domain import Setup

from osu_coach.tips.domain.aim import _direction_tips, _distance_angle_tips, _miss_cause_tip, _quadrant_tips
from osu_coach.tips.domain.common import Tip
from osu_coach.tips.domain.keyboard import _keyboard_tips
from osu_coach.tips.domain.skills import _consistency_tips, _reading_tips, _slider_tips
from osu_coach.tips.domain.tablet import _area_rotation_offset_tips, _area_scale_tips, _calibration_tip
from osu_coach.tips.domain.tapping import _key_usage_tips, _stream_tips, _timing_tips


def make_tips(p: Profile, setup: Setup | None = None) -> list[Tip]:
    setup = setup or Setup()
    tips: list[Tip] = []
    for rule in (_miss_cause_tip, _calibration_tip, _area_scale_tips, _area_rotation_offset_tips, _quadrant_tips, _direction_tips,
                 _distance_angle_tips, _timing_tips, _stream_tips, _key_usage_tips, _keyboard_tips, _slider_tips,
                 _reading_tips, _consistency_tips):
        try:
            out = rule(p, setup)
        except Exception as exc:  # noqa: BLE001 - one bad rule must not hide the others
            out = [Tip("Internal", f"Could not evaluate {rule.__name__}", 1, str(exc))]
        tips.extend(out or [])
    tips.sort(key=lambda t: -t.severity)
    return tips


def practice_plan(p: Profile) -> list[str]:
    """A simple daily routine built around the weakest skills."""
    weak = [SKILL_LABELS[k] for k in p.weaknesses] or ["your weakest skill"]
    comfort = p.levels.get("comfort_stars")
    lvl = f"{comfort:.1f}★" if comfort and not math.isnan(comfort) else "your comfort level"
    return [
        f"Warm-up (10 min): 2-3 maps about 1★ below {lvl}, aiming for full combos.",
        f"Focus block (20-30 min): the '{weak[0]}' playlist from Skill Development — repeat each map until the "
        "target in the playlist note is met.",
        f"Push (10 min): one or two maps slightly above {lvl}.",
        "Cool-down: replay a favourite map for fun.",
        "Re-run the analysis after ~20 new replays and compare the scores.",
    ]
