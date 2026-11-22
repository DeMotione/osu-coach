"""The mod configurations, speeds and accuracies of the play goals.

A configuration is a combination of :data:`CONFIGS` at a speed: the combination's own (DT's 1.5), or with DT any
hundredth from 1.10 to 2.00 (lazer's custom speeds; the ones the pool's map table holds). :func:`config_key` names it.
"""

from __future__ import annotations

# EZ variants (2, 10, 66, 74) come back once the pool's map table holds them.
CONFIGS = {
    "NM": 0,
    "HD": 8,
    "HR": 16,
    "HDHR": 24,
    "DT": 64,
    "HDDT": 72,
    "HRDT": 80,
    "HDHRDT": 88,
}
ACCURACIES = (0.9, 0.95, 0.97, 0.98, 0.99, 1.0)
MIN_RATE, MAX_RATE = 1.10, 2.00  # the speeds DT can be set to here


def standard_rate(mods: str) -> float:
    """The combination's own speed: DT's 1.5, else 1."""
    return 1.5 if "DT" in mods else 1.0


def valid_rate(mods: str, rate: float) -> bool:
    """Whether the combination can be at this speed: its own, or with DT a hundredth from 1.10 to 2.00."""
    if "DT" not in mods:
        return abs(rate - 1.0) < 1e-6
    hundredths = rate * 100
    return MIN_RATE * 100 - 1e-6 <= hundredths <= MAX_RATE * 100 + 1e-6 and abs(hundredths - round(hundredths)) < 1e-6


def config_key(mods: str, rate: float | None = None) -> str:
    """A configuration's name: the combination, and its speed when that is not the combination's own
    (``HDDT 1.20x``)."""
    if rate is None or abs(rate - standard_rate(mods)) < 1e-6:
        return mods
    return f"{mods} {rate:.2f}x"
