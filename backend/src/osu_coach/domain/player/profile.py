"""The :class:`Profile`: what the analysis pages read, and the row records of its tables."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.player.records import (
    AimSplit,
    AimStats,
    PressLengths,
    Regression,
    SkillRating,
    SpeedRow,
    WorstQuadrant,
)
from osu_coach.domain.player.summary import ChartNotes

if TYPE_CHECKING:
    from osu_coach.domain.player.engines import Rated


@dataclass(frozen=True, slots=True)
class Overview:
    """What the plays add up to (rates 0–1; notes and misses unweighted, the rates weighted)."""

    replays: int
    maps: int
    weighted_replays: float
    accuracy: float
    avg_stars: float  # by notes
    max_stars_passed: float  # hardest clean pass
    ur: float  # single-note UR
    sim_exact_share: float  # plays whose simulated judgements match the replay exactly
    sim_agreement: float
    play_minutes: float
    first_date: dt.datetime | None
    last_date: dt.datetime | None
    objects: int  # played notes
    head_misses: int
    miss_rate: float
    misses_per_100: float


@dataclass(frozen=True, slots=True)
class Levels:
    """The player's level (what the replay weights centre on), the comfort level the ratings are measured against,
    and the aim / speed levels (local difficulty held with 5% misses or fewer)."""

    aim_level: float
    speed_level: float
    model_coef: tuple | None  # the miss model: intercept, slope, mean, sd
    level_stars: float | None
    level_detected: float | None
    level_override: bool
    level_recent_n: int
    level_recent_since: dt.datetime | None
    level_band: float
    level_sigma: float
    weighted: bool
    comfort_stars: float | None  # set by hand, or measured (never provisional)
    comfort_status: str  # override | measured | provisional | none
    comfort_setups: int
    comfort_source: str


@dataclass(frozen=True, slots=True)
class Tapping:
    """Hit timing (UR in ms×10, errors in ms) and key presses; the press numbers are None without key-press data."""

    ur: float
    ur_single: float
    ur_streams: float
    mean_error: float
    early_share: float
    three_hundred_rate_single: float
    timing_miss_share: float
    slope_ms_per_note: float  # how the error drifts along streams
    late_half_err: float
    early_half_err: float
    n: int
    comfort_bpm: int | None  # the stream speed the player taps cleanly
    limit_bpm: int | None
    key_share: dict[str, float] | None = None  # presses by key (K1, K2, M1, M2, L, R)
    mouse_button_share: float | None = None
    key_device_known_share: float | None = None
    alternation_in_streams: float | None = None
    alternation_singles: float | None = None
    press_ms_median: float | None = None
    press_ms_streams: float | None = None
    hold_ratio_streams: float | None = None
    overlap_in_streams: float | None = None
    chatter_per_1000: float | None = None
    extra_presses_per_100: float | None = None
    press_count: int | None = None


@dataclass(frozen=True, slots=True)
class Aim:
    """Jump and aim-miss numbers (rates 0–1); ``split`` is the miss model's aim / speed-aim split."""

    aim_miss_rate: float
    aim_miss_share: float
    speed_aim_miss_share: float
    near_miss_share: float
    jump_objects: int
    jump_miss_rate: float
    jump_along: float
    jump_along_pct: float
    aim_err_median: float
    after_slider_miss_rate: float
    spaced_stream_objects: int
    spaced_stream_miss_rate: float
    split: AimSplit | None = None


@dataclass(frozen=True, slots=True)
class Sliders:
    sliders: int
    head_miss_rate: float
    break_rate: float
    end_miss_rate: float


@dataclass(frozen=True, slots=True)
class Reading:
    """Misses by note density and approach rate; ``*_ratio`` are observed / expected misses (None: no data)."""

    lost_share: float
    dense_miss_rate: float | None = None
    sparse_miss_rate: float | None = None
    dense_threshold: float | None = None
    high_ar_miss_rate: float | None = None
    mid_ar_miss_rate: float | None = None
    low_ar_miss_rate: float | None = None
    hidden_miss_rate: float | None = None
    ar_table: list | None = None
    high_ar_ratio: float | None = None
    high_ar_n: int | None = None
    high_ar_misses: float | None = None
    mid_ar_ratio: float | None = None
    mid_ar_n: int | None = None
    mid_ar_misses: float | None = None
    low_ar_ratio: float | None = None
    low_ar_n: int | None = None
    low_ar_misses: float | None = None
    dense_ratio: float | None = None
    dense_n: int | None = None
    dense_misses: float | None = None
    sparse_ratio: float | None = None
    sparse_n: int | None = None


@dataclass(frozen=True, slots=True)
class Consistency:
    """How misses cluster and where in the maps they fall (None: no data)."""

    miss_after_miss_ratio: float | None = None
    end_miss_share: float | None = None
    end_object_share: float | None = None
    first_half_miss_rate: float | None = None
    second_half_miss_rate: float | None = None
    accuracy_std: float | None = None


@dataclass(frozen=True, slots=True)
class FallBehind:
    """How timing falls behind along long streams; the curves are lists of rows."""

    curves: list
    curve: list
    start_note: int | None
    start_seconds: float | None
    bpm: float | None
    slope_after: float
    growth_ms: float
    base_ms: float
    streams: int
    longest: int
    comfort_notes: int | None
    practice_notes: tuple | None
    reach_bpm: int | None
    curves_bpm: list


@dataclass(eq=False)
class Profile:
    """Everything the pages show about a set of plays. ``replays`` and ``weights`` go together: each play's meta and
    its weight (by how far its star rating is from the player's level)."""

    overview: Overview
    replays: tuple[ReplayMeta, ...]
    weights: tuple[float, ...]
    miss_breakdown: dict
    slider_breaks: dict
    tapping: Tapping
    stream_profile: tuple[SpeedRow, ...]
    aim: Aim
    quadrants: tuple[AimStats, ...]
    worst_quadrant: WorstQuadrant | None
    grid: tuple[AimStats, ...]  # cells 0–8
    directions: tuple[AimStats, ...]
    distances: tuple[AimStats, ...]
    angles: tuple[AimStats, ...]
    regression: Regression | None
    sliders: Sliders
    reading: Reading
    consistency: Consistency
    strengths: list
    weaknesses: list
    levels: Levels
    notes: ChartNotes = field(repr=False)  # the played notes of every play (``replay_key``), with its weight ``w``
    presses: PressLengths = field(repr=False)
    miss_breakdown_raw: dict = field(default_factory=dict)  # the same, unweighted counts
    fall_behind: FallBehind | None = None  # streams.fall_behind()
    skill_ratings: dict[str, SkillRating] = field(default_factory=dict)  # by skill (ratings.py)
    engine: str = "comfort"  # the rating engine that made skill_ratings (engines.py)
    rated: Rated | None = field(default=None, repr=False)  # what that engine gave (None without ratings)
