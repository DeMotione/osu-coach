"""A playlist's focus: the weak spot an analysis page found ("Practise this"), as a filter on the pool's maps.

A focus keeps only the maps whose statistics put them on that weak spot: streams at the weak speeds, streams of the
length where stamina gives in, jumps of the weak distance, and so on. It is written ``kind:spec``:

- ``bpm:120-130,140-160``: the map's streams (their median BPM, 1/4 notes) at one of the speeds, ``lo <= bpm < hi``;
- ``run:12-20``: its longest stream between 12 and 20 notes;
- ``ar:9.5-10``: its approach rate (without mods) in one of the ranges, ``lo <= ar < hi``;
- ``jump:long`` / ``jump:short``: its typical jump (the median) long / short for the pool;
- ``angle:sharp`` / ``angle:wide``: many / few sharp turns (back-and-forth jumps) between its jumps;
- ``quadrant:top-left``: many of its notes in that part of the screen;
- ``slider_length:long`` / ``short`` and ``slider_speed:fast`` / ``slow``: sliders (a good share of them) that are
  long / short or fast / slow for the pool.

"Many" and "long" mean among the pool's quarter of maps with the most: the pool's maps hold one number per map (a
median or a share), not one per note, so a map is on the weak spot when that number is far enough out.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.player.measures.streams import BPM_SLACK

QUADRANTS = ("top-left", "top-right", "bottom-left", "bottom-right")

# the pool's quartiles (pool.json.gz): a map in the top (bottom) quarter has a lot (little) of it
JUMP_LONG, JUMP_SHORT = 2.91, 2.47  # jump_dist: median jump of 2+ circle widths
SHARP_MANY, SHARP_FEW = 0.63, 0.45  # sharp_share: turns under 60° between jumps
QUADRANT_MANY = 0.27  # q_*: share of the notes in that quarter of the screen (0.25 if spread evenly)
SLIDER_LONG, SLIDER_SHORT = 1.41, 1.10  # slider_length_norm: median slider path, circle diameters
SLIDER_FAST, SLIDER_SLOW = 8.9, 6.1  # median slider ball speed, circle diameters a second
SLIDER_SHARE = 0.3  # sliders practised: at least this share of the map's notes are sliders

_SIDES = {
    "jump": ("long", "short"),
    "angle": ("sharp", "wide"),
    "quadrant": QUADRANTS,
    "slider_length": ("long", "short"),
    "slider_speed": ("fast", "slow"),
}
_RANGES = ("bpm", "run", "ar")
_NUMBER = r"\d+(?:\.\d+)?"


@dataclass(frozen=True, slots=True)
class Focus:
    """``kind`` and either the ``ranges`` (lo, hi) a map's number is in, or the ``side`` it leans to."""

    kind: str
    ranges: tuple[tuple[float, float], ...] = ()
    side: str | None = None

    @property
    def sets_tempo(self) -> bool:
        """Whether it picks the tapping speed itself (a speed playlist then doesn't ask for the player's top speed)."""
        return self.kind in ("bpm", "run")

    def matches(self, row: Mapping[str, Any]) -> bool:
        """Whether the pool map ``row`` is on the weak spot."""
        value = _value(self.kind, self.side, row)
        if value is None:
            return False
        if self.kind == "run":
            return any(lo <= value <= hi for lo, hi in self.ranges)
        if self.kind == "bpm":  # as the analysis steps them: half a BPM of slack for note times in whole ms
            return any(lo <= value + BPM_SLACK < hi for lo, hi in self.ranges)
        if self.ranges:
            return any(lo <= value < hi for lo, hi in self.ranges)
        if self.kind in ("slider_length", "slider_speed") and (_get(row, "slider_share") or 0) < SLIDER_SHARE:
            return False
        many = self.side in ("sharp", "long", "fast") or self.kind == "quadrant"
        low, high = _LIMITS[self.kind]
        return value >= high if many else value <= low

    def label(self) -> str:
        """What it practises, for the playlist's heading and its collection name."""
        if self.kind == "bpm":
            return f"streams at {_listed(f'{_n(lo)}–{_n(hi - 1)}' for lo, hi in self.ranges)} BPM"
        if self.kind == "run":
            return f"streams of {_listed(f'{_n(lo)}–{_n(hi)}' for lo, hi in self.ranges)} notes"
        if self.kind == "ar":
            return _listed(f"AR {_n(lo)}" if hi - lo <= 0.5 else f"AR {_n(lo)}–{_n(hi)}" for lo, hi in self.ranges)
        if self.kind == "jump":
            return f"{self.side} jumps"
        if self.kind == "angle":
            return "sharp back-and-forth jumps" if self.side == "sharp" else "wide, flowing jumps"
        if self.kind == "quadrant":
            return f"jumps into the {self.side} of the screen"
        return f"{self.side} sliders"


_LIMITS = {
    "jump": (JUMP_SHORT, JUMP_LONG),
    "angle": (SHARP_FEW, SHARP_MANY),
    "quadrant": (0.0, QUADRANT_MANY),
    "slider_length": (SLIDER_SHORT, SLIDER_LONG),
    "slider_speed": (SLIDER_SLOW, SLIDER_FAST),
}


def parse_focus(text: str | None) -> Focus | None:
    """The focus written ``kind:spec`` (see the module); None for none. Raises ValueError for one it can't read."""
    if text is None or not text.strip():
        return None
    kind, _, spec = text.strip().partition(":")
    if kind in _SIDES:
        if spec not in _SIDES[kind]:
            raise ValueError(f"Unknown {kind} focus {spec!r}.")
        return Focus(kind, side=spec)
    if kind not in _RANGES:
        raise ValueError(f"Unknown focus {kind!r}.")
    ranges = []
    for part in spec.split(","):
        m = re.fullmatch(rf"({_NUMBER})-({_NUMBER})", part.strip())
        if not m or not float(m[1]) < float(m[2]):
            raise ValueError(f"Invalid {kind} range {part!r}.")
        ranges.append((float(m[1]), float(m[2])))
    if len(ranges) > 20:
        raise ValueError("Too many focus ranges.")
    return Focus(kind, ranges=tuple(sorted(ranges)))


def _get(row: Mapping[str, Any], key: str) -> float | None:
    return finite_or_none(row.get(key))


def _value(kind: str, side: str | None, row: Mapping[str, Any]) -> float | None:
    if kind == "bpm":
        return _get(row, "stream_bpm")
    if kind == "run":
        return _get(row, "max_run")
    if kind == "ar":
        return _get(row, "ar")
    if kind == "jump":
        return _get(row, "jump_dist")
    if kind == "angle":
        return _get(row, "sharp_share")
    if kind == "quadrant":
        return _get(row, "q_" + (side or "").replace("-", "_"))
    if kind == "slider_length":
        return _get(row, "slider_length_norm")
    velocity = _get(row, "slider_velocity")  # osu! pixels a millisecond
    if velocity is None:
        return None
    radius = max(1.0, 54.4 - 4.48 * (_get(row, "cs") or 4.0))
    return velocity * 1000 / (2 * radius)


def _n(x: float) -> str:
    return str(int(x)) if math.isclose(x, round(x)) else f"{x:g}"


def _listed(items) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"
