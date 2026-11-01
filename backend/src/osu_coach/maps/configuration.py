"""Finite configuration search grid for map recommendations."""

from __future__ import annotations

import math
from dataclasses import dataclass

from osu_coach.profile.domain.algorithm import RATE_STEP_HUNDREDTHS
from osu_coach.replays.configuration import Configuration
from osu_coach.replays.domain import MOD_BITS


@dataclass(frozen=True)
class SearchOptions:
    allow_hr: bool = False
    allow_hd: bool = False
    adjustable_dt: bool = False
    min_rate: float = 1.10
    max_rate: float = 2.00

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.min_rate, self.max_rate)):
            raise ValueError("Rate bounds must be finite.")
        if not (1.10 <= self.min_rate <= self.max_rate <= 2.00):
            raise ValueError("DT rate bounds must stay between 1.10 and 2.00.")
        if any(abs(v * 100 - round(v * 100)) > 1e-8 for v in (self.min_rate, self.max_rate)):
            raise ValueError("DT rate bounds must use hundredth increments.")

    @property
    def modified(self) -> bool:
        return self.allow_hr or self.allow_hd or self.adjustable_dt

    def configurations(self, md5: str, client: str = "stable") -> tuple[Configuration, ...]:
        rates = [100]
        if self.adjustable_dt:
            rates += list(range(round(self.min_rate * 100), round(self.max_rate * 100) + 1, RATE_STEP_HUNDREDTHS))
        return tuple(
            Configuration(
                md5,
                (MOD_BITS["HR"] if hr else 0) | (MOD_BITS["HD"] if hd else 0) | (MOD_BITS["DT"] if rate != 100 else 0),
                rate / 100,
                client,
            )
            for hr in (False, True)
            if not hr or self.allow_hr
            for hd in (False, True)
            if not hd or self.allow_hd
            for rate in rates
        )
