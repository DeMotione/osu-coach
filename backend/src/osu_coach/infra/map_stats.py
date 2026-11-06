"""Pattern and difficulty statistics of one .osu file (rosu-pp), for the map pools."""

from __future__ import annotations

import math

import numpy as np

from osu_coach.domain.beatmaps.models import MOD_DT, MOD_HT, MOD_NC, Beatmap
from osu_coach.domain.maps.suggestions import pattern_stats, skill_scores
from osu_coach.infra.beatmaps import difficulty


# ------------------------------------------------------------------ per-map statistics
def map_stats(
    bm: Beatmap, osu_bytes: bytes, mods: int = 0, rate: float | None = None, lazer: bool = False
) -> dict | None:
    """Pattern + difficulty statistics of one parsed .osu file; NoMod unless ``mods`` is supplied."""
    pattern = pattern_stats(bm, osu_bytes, mods, rate)
    return finish_stats(pattern, osu_bytes, mods, rate, lazer) if pattern is not None else None


def finish_stats(
    s: dict, osu_bytes: bytes, mods: int, rate: float | None, lazer: bool = False, parsed_map=None
) -> dict:
    """Calculate exact rosu difficulty and skill values for one configuration."""
    s = s.copy()
    pb_rate = rate if rate is not None else (1.5 if mods & (MOD_DT | MOD_NC) else 0.75 if mods & MOD_HT else 1.0)
    a = difficulty.attributes(osu_bytes, mods, rate=pb_rate, lazer=lazer, parsed_map=parsed_map)
    s.update(
        {
            "stars": a.get("stars", math.nan),
            "aim": a.get("aim", math.nan),
            "speed": a.get("speed", math.nan),
            "slider_factor": a.get("slider_factor", 1.0),
            "max_combo": a.get("max_combo", math.nan),
            "speed_note_count": a.get("speed_note_count", math.nan),
        }
    )
    if not mods and pb_rate == 1.0:
        s["stars_dt"] = difficulty.attributes(osu_bytes, 64, parsed_map=parsed_map).get("stars", math.nan)
    s["evenness"] = _evenness(osu_bytes, mods, pb_rate, lazer=lazer, parsed_map=parsed_map)
    s.update(skill_scores(s))
    return s


def _evenness(
    osu_bytes: bytes, mods: int = 0, rate: float | None = None, lazer: bool = False, parsed_map=None
) -> float:
    """Median / peak section difficulty in star units (1 = equally hard throughout)."""
    st = difficulty.strains(osu_bytes, mods, rate=rate, lazer=lazer, parsed_map=parsed_map)
    if not st or not st.get("aim"):
        return math.nan
    aim = np.sqrt(10 * np.asarray(st["aim"], dtype=float))
    speed = np.sqrt(10 * np.asarray(st["speed"] or [0.0] * len(aim), dtype=float))
    n = min(len(aim), len(speed))
    comb = np.maximum(aim[:n], speed[:n])
    comb = comb[comb > 0]
    return float(np.median(comb) / comb.max()) if len(comb) else math.nan
