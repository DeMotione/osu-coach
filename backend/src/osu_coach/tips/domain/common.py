"""What every tip rule shares: the :class:`Tip` itself and small formatting helpers."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

PLAYFIELD_SCREEN_FRACTION = 0.8   # osu! playfield height = 80 % of screen height


@dataclass
class Tip:
    category: str
    title: str
    severity: int                      # 1 (nice to know) .. 3 (biggest impact)
    evidence: str
    actions: list[str] = field(default_factory=list)
    settings: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _pct(v: float, digits: int = 1) -> str:
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v * 100:.{digits}f}%"


def _nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))
