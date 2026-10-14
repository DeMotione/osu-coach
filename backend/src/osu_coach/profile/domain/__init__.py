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
* skill scores: observed vs expected misses where "expected" comes from a
  logistic model of the player's own miss chance against local difficulty
  (osu! strain model, star-equivalent per 400 ms section).

Every statistic is weighted by the replay weight (column ``w`` on the objects and presses).
"""
from __future__ import annotations

from osu_coach.profile.domain.aim import (
    aim_regression,
    aim_score,
    aim_values,
    CLICK_BANDS,
    click_points,
    click_summary,
    quadrant_stats,
    worst_quadrant,
)
from osu_coach.profile.domain.build import build_profile
from osu_coach.profile.domain.consistency import consistency_score
from osu_coach.profile.domain.constants import MISS_LABELS, SKILL_HELP, SKILL_LABELS
from osu_coach.profile.domain.levels import (
    clean_pass,
    comfort_stars,
    detect_level,
    LEVEL_BAND,
    LEVEL_SIGMA,
    replay_weight,
    weight_table,
)
from osu_coach.profile.domain.misses import fit_miss_model, miss_causes, miss_chain_ratio
from osu_coach.profile.domain.model import Profile
from osu_coach.profile.domain.ranking import difficulty_weights, rank_weights, ranked_mean
from osu_coach.profile.domain.reading import READ_REF, reading_score, reading_values, usual_ar
from osu_coach.profile.domain.skills import accuracy_score, compute_skills, skills_at_level, top_comparison
from osu_coach.profile.domain.sliders import slider_difficulty, slider_score
from osu_coach.profile.domain.stamina import stamina_ref_bpm, stamina_score, tempo_curve
from osu_coach.profile.domain.stats import played_notes
from osu_coach.profile.domain.tapping import (
    speed_score,
    speed_values,
    stream_fall_behind,
    stream_limits,
    stream_speed_profile,
)

__all__ = [
    "CLICK_BANDS",
    "LEVEL_BAND",
    "LEVEL_SIGMA",
    "MISS_LABELS",
    "Profile",
    "READ_REF",
    "SKILL_HELP",
    "SKILL_LABELS",
    "accuracy_score",
    "aim_regression",
    "aim_score",
    "aim_values",
    "build_profile",
    "clean_pass",
    "click_points",
    "click_summary",
    "comfort_stars",
    "compute_skills",
    "consistency_score",
    "detect_level",
    "difficulty_weights",
    "fit_miss_model",
    "miss_causes",
    "miss_chain_ratio",
    "played_notes",
    "quadrant_stats",
    "rank_weights",
    "ranked_mean",
    "reading_score",
    "reading_values",
    "replay_weight",
    "skills_at_level",
    "slider_difficulty",
    "slider_score",
    "speed_score",
    "speed_values",
    "stamina_ref_bpm",
    "stamina_score",
    "stream_fall_behind",
    "stream_limits",
    "stream_speed_profile",
    "tempo_curve",
    "top_comparison",
    "usual_ar",
    "weight_table",
    "worst_quadrant",
]
