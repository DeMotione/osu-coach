"""Experimental skill-model assumptions; change this version when recalibrating."""

from __future__ import annotations

import math

from osu_coach.replays.domain import MOD_BITS

MODEL_VERSION = 1
DT_ACCURACY_MIN = 0.88  # strict greater-than gate for timing evidence
READ_LOW_AR = 9.5
READ_HD_UPPER_AR = 10.0
READ_FAST_AR = 10.5
READ_LOW_WEIGHT = 0.015
READ_FAST_WEIGHT = 0.05
READ_HD_BASE = 0.12
READ_HD_LOW_WEIGHT = 0.025
READ_HD_HIGH_WEIGHT = 0.035
READ_HD_DENSITY_WEIGHT = 0.02
RATE_STEP_HUNDREDTHS = 1


def timing_evidence_eligible(mods: int, accuracy: float | None) -> bool:
    """DT/NC timing evidence needs strictly more than the configured accuracy."""
    if not mods & (MOD_BITS["DT"] | MOD_BITS["NC"]):
        return True
    try:
        value = float(accuracy)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value) and value > DT_ACCURACY_MIN
