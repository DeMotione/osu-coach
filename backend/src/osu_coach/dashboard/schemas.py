"""Responses of the analysis pages. Rates and shares are fractions (0–1) unless the name says ``pct`` or the field description says %; ``null`` = not enough data."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from osu_coach.maps.schemas import MapRow
from osu_coach.tips.schemas import TipOut


# ------------------------------------------------------------------ summary and replays
class ProfileSummary(BaseModel):
    player_label: str
    replay_set: Literal["all", "best"]
    replays: int
    notes: int
    level_stars: float | None


class AnalysedReplay(BaseModel):
    key: str
    played_at: str | None = Field(description="ISO 8601, UTC.")
    map: str
    mods: str
    stars: float | None
    weight: float = Field(description="How much the play counts (difficulty weighting), 0–1.")
    accuracy: float | None
    misses: int | None
    combo: int | None
    ur: float | None
    sim_agreement: float | None = Field(description="Re-simulated judgements matching the replay, 0–1.")
    path: str
    beatmap_md5: str | None


# ------------------------------------------------------------------ overview
class LevelWeight(BaseModel):
    stars_off: float
    weight: float


class LevelInfo(BaseModel):
    stars: float | None = Field(description="The level used for the weighting (detected or set by hand).")
    detected: float | None
    override: bool
    recent_n: int
    band: float
    sigma: float
    weights: list[LevelWeight]
    replays: int
    weighted_replays: float


class OverviewKpis(BaseModel):
    replays: int
    maps: int
    weighted_replays: float
    play_minutes: float | None
    comfort_stars: float | None
    ur: float | None
    misses_per_100: float | None
    accuracy: float | None


class SkillScore(BaseModel):
    key: str
    label: str
    score: float | None
    score_text: str = Field(description="The score as shown, or why there is none.")
    low_data: bool
    too_few_misses: bool
    n: int
    facts: list[str] = Field(description="The player's own numbers behind the score.")


class SkillLevel(BaseModel):
    key: str
    label: str
    level: float | None = Field(
        description="Star rating of a typical map whose demand on this skill matches what the player has shown; "
        "readiness for a target T = 1 − ((T / level)² − 1), clipped to 0–1."
    )
    facts: list[str] = Field(description="What the level is measured from.")


class Readiness(BaseModel):
    comfort: float | None = Field(description="The comfort level (★) the targets are counted from.")
    ahead: float = Field(description="Targets more than this many stars above comfort are locked.")
    step: float = Field(description="Distance between the targets offered near comfort (★).")
    min_target: float = Field(description="Lowest star rating to compare with.")
    max_target: float = Field(description="Highest star rating to compare with.")
    skills: list[SkillLevel]


class ConsistencyBand(BaseModel):
    low: float = Field(description="Star rating (with mods) the band starts at.")
    high: float
    plays: int
    score: float | None = Field(description="0–100; null with fewer than `min_plays` plays in the band.")
    combo: float | None = Field(description="Combo held: share of the map's max combo, average minus its spread, 0–1.")
    accuracy: float | None = Field(description="Accuracy held on the 93–99% scale (0–1), average minus its spread.")
    full_combo_share: float
    mean_accuracy: float


class Consistency(BaseModel):
    min_plays: int
    bands: list[ConsistencyBand]


class StaminaPoint(BaseModel):
    seconds: float
    bpm: float
    typical: float | None


class ReadingSplit(BaseModel):
    low_ar_score: float | None
    low_ar_maps: int
    high_ar_score: float | None
    high_ar_maps: int


class MissCause(BaseModel):
    cause: str
    share: float
    misses: int = Field(description="Unweighted count.")


class AimSplit(BaseModel):
    fast_ratio: float = Field(description="Misses on fast patterns vs expected (1.0 = as expected).")
    normal_ratio: float = Field(description="Misses on normal-speed jumps and notes vs expected.")


class Overview(BaseModel):
    level: LevelInfo
    kpis: OverviewKpis
    skills: list[SkillScore]
    reading_split: ReadingSplit
    few_data: list[str] = Field(description="Skills measured on few maps or notes.")
    readiness: Readiness
    consistency: Consistency
    stamina: list[StaminaPoint] = Field(description="Tempo kept per duration (empty without a stamina score).")
    sliders_scored: bool
    strengths: list[str]
    weaknesses: list[str]
    miss_causes: list[MissCause]
    aim_split: AimSplit | None
    top_tips: list[TipOut]
    sim_exact_share: float | None
    sim_agreement: float | None


# ------------------------------------------------------------------ aim
class AimKpis(BaseModel):
    aim_miss_share: float | None
    speed_aim_miss_share: float | None
    jump_miss_rate: float | None
    near_miss_share: float | None
    jump_along_pct: float | None = Field(description="Median over(+)/undershoot along the jump, % of its length.")


class WorstQuadrant(BaseModel):
    quadrant: str
    miss_rate: float
    rest_miss_rate: float
    relative_risk: float | None
    significant: bool


class QuadrantCell(BaseModel):
    quadrant: str
    miss_rate: float | None
    misses: float
    objects: float


class PlayfieldGrid(BaseModel):
    x: list[float]
    y: list[float]
    rate: list[list[float | None]] = Field(description="Miss rate % per cell, rows top to bottom.")


class DirectionRow(BaseModel):
    direction: str
    angle: int = Field(description="Degrees, counter-clockwise from 'right'.")
    miss_rate: float | None
    objects: float


class DistanceRow(BaseModel):
    bin: str = Field(description="Distance from the previous note, circle diameters.")
    miss_rate: float | None
    objects: float
    along: float | None = Field(description="Over(+)/undershoot in circle radii.")


class AngleRow(BaseModel):
    bin: str
    objects: float
    miss_rate: float | None


class Regression(BaseModel):
    n: int
    scale_x: float
    scale_y: float
    rotation_deg: float
    offset_x: float
    offset_y: float


class AimPage(BaseModel):
    kpis: AimKpis
    worst_quadrant: WorstQuadrant | None
    quadrants: list[QuadrantCell]
    grid: PlayfieldGrid
    directions: list[DirectionRow]
    distances: list[DistanceRow]
    angles: list[AngleRow]
    regression: Regression | None


# ------------------------------------------------------------------ tapping
class TappingKpis(BaseModel):
    ur: float | None
    ur_single: float | None
    ur_streams: float | None
    mean_error: float | None
    three_hundred_rate_single: float | None
    alternation_in_streams: float | None


class TimingHistogram(BaseModel):
    centers: list[float] = Field(description="Bin centres, ms (− early, + late).")
    n300: list[float]
    n100: list[float]
    n50: list[float]
    total: float
    share300: float | None
    share100: float | None
    share50: float | None
    mean: float | None


class StreamPoint(BaseModel):
    x: float = Field(description="Start of the bin, minutes.")
    miss_rate: float | None = Field(description="%")
    ur: float | None
    n: int


class StreamLine(BaseModel):
    key: str = Field(description="'overall' or the band's lowest BPM.")
    points: list[StreamPoint]


class StreamAlong(BaseModel):
    step: float = Field(description="Minutes per point.")
    lines: list[StreamLine]


class StreamsOverTime(BaseModel):
    bands: list[int]
    band_width: int
    notes: int
    map: StreamAlong
    session: StreamAlong


class StreamSpeedRow(BaseModel):
    bpm: int = Field(description="Lowest BPM of the 10-BPM bin.")
    objects: float
    tap_miss_rate: float | None
    speed_aim_rate: float | None
    ur: float | None
    ur_best: float | None
    ur_plays: int
    ur_trend: float | None
    weak: bool


class StreamSpeed(BaseModel):
    rows: list[StreamSpeedRow]
    comfort_bpm: float | None
    limit_bpm: float | None


class FallBehindPoint(BaseModel):
    group: str
    pos: int
    abs_err: float | None
    err: float | None
    miss_rate: float | None
    n: int


class FallBehindSpeedPoint(BaseModel):
    group: str
    pos: int
    rel_err: float | None = Field(description="% of the time between notes.")
    abs_err: float | None
    miss_rate: float | None
    n: int


class FallBehindSpeedGroup(BaseModel):
    group: str
    first: float
    last: float
    notes: int
    rise: float


class MapList(BaseModel):
    min_notes: int
    max_notes: int
    maps: list[MapRow]
    excluded: dict[str, int] = Field(default_factory=dict)


class FallBehind(BaseModel):
    available: bool
    start_note: int | None
    start_seconds: float | None
    bpm: float | None
    base_ms: float | None
    growth_ms: float | None
    last_note: int | None
    comfort_notes: int | None
    practice_notes: list[int] | None = Field(min_length=2, max_length=2, description="[from, to] notes.")
    streams: int
    curves: list[FallBehindPoint]
    by_speed: list[FallBehindSpeedPoint]
    by_speed_groups: list[FallBehindSpeedGroup]
    worst_speed: str | None
    comfortable_maps: MapList | None
    practice_maps: MapList | None


class KeyShare(BaseModel):
    key: str
    share: float


class KeyUsage(BaseModel):
    shares: list[KeyShare]
    hold_ms: float | None
    press_ms_streams: float | None
    chatter_per_1000: float | None


class TappingPage(BaseModel):
    kpis: TappingKpis
    timing: TimingHistogram
    streams_over_time: StreamsOverTime | None
    stream_speed: StreamSpeed | None
    fall_behind: FallBehind
    keys: KeyUsage


# ------------------------------------------------------------------ sliders & reading
class SliderKpis(BaseModel):
    sliders: int
    head_miss_rate: float | None
    break_rate: float | None
    end_miss_rate: float | None


class BreakShare(BaseModel):
    reason: str
    share: float


class ArMissRow(BaseModel):
    ar: str
    miss_rate: float | None
    objects: float


class SliderBin(BaseModel):
    bin: str
    head: float = Field(description="% head missed")
    broke: float = Field(description="% hit but broken later")
    n: int


class SliderRates(BaseModel):
    rows: list[SliderBin]
    worst: str | None


class HitsByAr(BaseModel):
    ar: float
    n: int
    plays: int
    r300: float
    r100: float
    r50: float
    miss: float


class ReadingKpis(BaseModel):
    dense_miss_rate: float | None
    dense_threshold: float | None
    sparse_miss_rate: float | None
    miss_after_miss_ratio: float | None
    end_miss_share: float | None
    end_object_share: float | None


class SlidersReadingPage(BaseModel):
    kpis: SliderKpis
    breaks: list[BreakShare]
    ar_misses: list[ArMissRow]
    by_length: SliderRates | None
    by_speed: SliderRates | None
    hits_by_ar: list[HitsByAr]
    reading: ReadingKpis
