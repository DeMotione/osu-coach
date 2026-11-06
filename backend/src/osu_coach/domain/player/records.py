"""The records of the profile: the rows of its tables, its aim findings and the skill ratings."""

from __future__ import annotations

import math
from dataclasses import dataclass

from osu_coach.domain.numeric.arrays import ArrayRecord, Floats, Texts
from osu_coach.domain.player.messages import Message


@dataclass(frozen=True, slots=True)
class AimStats:
    """Notes of one kind (a quadrant, a grid cell, a direction, a distance, a turn angle), weighted: how many, how
    many missed (all / by aim), the mean aim error on screen (px) and the over-/undershoot (``along``) and side error
    (``cross``) in radii."""

    name: str | int
    objects: float
    misses: float
    miss_rate: float
    aim_misses: float
    aim_miss_rate: float
    mean_dx: float
    mean_dy: float
    along: float
    cross: float
    aim_err: float = math.nan  # median aim error (radii; distances only)


@dataclass(frozen=True, slots=True)
class SpeedRow:
    """Bursts and streams of one BPM bin (weighted notes; rates 0–1)."""

    bpm_bin: int
    objects: float
    miss_rate: float
    tap_miss_rate: float  # finger misses
    speed_aim_rate: float  # aim misses: the cursor fell behind
    non300_rate: float
    ur: float  # median of the plays' URs here (the pooled UR without enough hits per play)
    ur_best: float
    ur_plays: int
    ur_pooled: float
    mean_err: float
    ur_trend: float = math.nan  # the UR expected at this speed (:func:`~osu_coach.domain.player.streams.ur_trend`)
    weak: bool = False  # the UR is well above the trend: a speed you are weak at


@dataclass(frozen=True, slots=True)
class PressLengths(ArrayRecord):
    """Every key press: its play and how long it was held (ms, map time)."""

    replay_key: Texts
    duration: Floats


@dataclass(frozen=True, slots=True)
class WorstQuadrant:
    """The playfield quadrant with the most misses, against the rest."""

    quadrant: str
    miss_rate: float
    rest_miss_rate: float
    relative_risk: float
    z: float
    objects: int
    misses: int
    mean_dx: float
    mean_dy: float
    along: float
    aim_miss_rate: float
    significant: bool


@dataclass(frozen=True, slots=True)
class Regression:
    """Where the cursor lands against the notes, as an affine map (the "tablet area" fit)."""

    n: int
    scale_x: float
    scale_y: float
    rotation_deg: float
    offset_x: float
    offset_y: float
    offset_se: float
    residual_px: float
    radius: float


@dataclass(frozen=True, slots=True)
class MissSplitPart:
    """The notes of one side of the aim split (weighted): its aim misses, all its misses and the misses the miss
    model expects there."""

    notes: float
    misses: float
    all_misses: float
    expected: float

    @property
    def ratio(self) -> float | None:
        """All misses against the expected ones; None without expected misses."""
        return self.all_misses / self.expected if self.expected > 0 else None


@dataclass(frozen=True, slots=True)
class AimSplit:
    """Aim misses on normal-speed patterns (``aim``) vs speed-aim misses on fast ones (``speed_aim``)."""

    aim: MissSplitPart
    speed_aim: MissSplitPart


@dataclass(frozen=True, slots=True)
class StaminaPart:
    """The stamina rating at one stretch duration (s): the fastest tempo kept over it on the best map/mod setups
    (``measured``), the tempo typical at the comfort level (``expected``) and the hardest one played
    (``tested_demand``). ``untested``: nothing played was demanding enough to tell."""

    duration: int
    measured: float
    maps: int
    tested_demand: float
    success_share: float
    expected: float
    untested: bool


@dataclass(frozen=True, slots=True)
class SkillRating:
    """A skill's rating against the comfort level (50 = what is typical there; None: not enough data) and how it was
    measured. Only some skills fill the optional numbers: stamina its ``parts``, accuracy the OD windows,
    consistency its range of maps."""

    score: float | None
    maps: int
    reason: Message  # how the score was found, or why there is none
    needs: Message | None = None  # what to play to get a score
    at_least: float | None = None  # untested: the skill is at least this good
    measured: float | None = None
    expected: float | None = None
    tested_demand: float | None = None
    success_share: float | None = None
    parts: tuple[StaminaPart, ...] | None = None  # stamina: one per stretch duration
    hit_single_notes: int | None = None  # accuracy
    expected_top: float | None = None
    od_windows: list[tuple[float, float]] | None = None  # accuracy: (300 window in ms, weight)
    low: float | None = None  # consistency: the star range of the maps
    high: float | None = None
    plays: int | None = None
    min_maps: int | None = None
    map_score: float | None = None
    swing: float | None = None
    weak_maps: int | None = None
    mean_combo: float | None = None
    full_combo_share: float | None = None
    mean_accuracy: float | None = None


UNRATED = SkillRating(score=None, maps=0, reason=Message("not_enough_data"))  # a skill without a rating
