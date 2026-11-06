"""Aggregate many replay analyses into a player profile.

Everything here is computed from replays only:
* the player's level (comfort star rating of the recent replays) and a weight per replay by how far its
  star rating is from that level (``replay_weight``): plays far below or above the level (a 1.5★ warm-up,
  a 9★ map played for fun) hardly count, so they don't distort the numbers;
* overview, miss breakdown (why misses happen, incl. *speed-aim*: aim misses in streams / very fast
  jumps, where the cursor couldn't keep up with the tempo),
* tapping (UR, bias, stream speed profile, alternation, key holds, extra taps, falling behind in streams),
* aim (spacing / direction / angle / quadrant / heat-map, over-/undershoot and an
  affine "tablet area" regression),
* sliders, reading, consistency,
* skill ratings (``ratings.py``): each skill against what is typical at the player's comfort level (50 = typical),
  and the strengths and weaknesses every page and the tips use.

Every statistic is weighted by the replay weight (column ``w`` on the objects and presses).
"""

from __future__ import annotations

from osu_coach.domain.player.aim import (
    worst_quadrant,
)
from osu_coach.domain.player.build import build_profile, build_profile_from
from osu_coach.domain.player.constants import SKILLS
from osu_coach.domain.player.levels import (
    LEVEL_BAND,
    LEVEL_SIGMA,
    comfort,
    replay_weight,
    weight_table,
)
from osu_coach.domain.player.profile import Profile
from osu_coach.domain.player.reading import usual_ar
from osu_coach.domain.player.summary import PlaySummary, summarize

__all__ = [
    "LEVEL_BAND",
    "LEVEL_SIGMA",
    "Profile",
    "SKILLS",
    "build_profile",
    "build_profile_from",
    "PlaySummary",
    "summarize",
    "comfort",
    "replay_weight",
    "usual_ar",
    "weight_table",
    "worst_quadrant",
]
