"""The row records of the profile's tables."""

from __future__ import annotations

import math
from dataclasses import dataclass

from osu_coach.domain.numeric.arrays import ArrayRecord, Floats, Texts


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
