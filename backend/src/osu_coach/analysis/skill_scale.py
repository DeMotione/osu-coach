"""Shared calibration for replay speed ratings and map tapping demands."""

from __future__ import annotations

import math

SPEED_POINTS = 75.0


def expected_speed_bpm(stars: float) -> float:
    return min(300.0, max(120.0, 120 + 15 * stars))


def speed_rating(bpm: float, stars: float) -> float:
    """Put a tapping tempo on the same 0–100 scale as replay speed ability."""
    return min(100.0, max(0.0, 50 + SPEED_POINTS * math.log2(bpm / expected_speed_bpm(stars))))


def speed_bpm_for_rating(rating: float, stars: float) -> float:
    return expected_speed_bpm(stars) * 2 ** ((rating - 50) / SPEED_POINTS)
