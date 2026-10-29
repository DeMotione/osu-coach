"""Explicit PP scenarios for supported standard configurations, with no silent fallback."""

from __future__ import annotations

import math
from importlib.metadata import version

import rosu_pp_py as rosu

CALCULATOR_VERSION = version("rosu-pp-py")
SUPPORTED_MODS = (0, 8, 16, 24, 64, 72, 80, 88)


def calculate(
    osu_bytes: bytes,
    mods: int = 0,
    client: str = "stable",
    accuracy: float = 1.0,
    misses: int = 0,
    combo: int | None = None,
) -> float:
    if isinstance(mods, bool) or mods not in SUPPORTED_MODS or client not in ("stable", "lazer"):
        raise ValueError("Unsupported PP configuration.")
    if (
        isinstance(accuracy, bool)
        or not isinstance(accuracy, (int, float))
        or not math.isfinite(accuracy)
        or not 0 <= accuracy <= 1
    ):
        raise ValueError("Accuracy must be a finite fraction between 0 and 1.")
    if isinstance(misses, bool) or not isinstance(misses, int) or misses < 0:
        raise ValueError("Miss count must be a non-negative integer.")
    beatmap = rosu.Beatmap(bytes=osu_bytes)
    if beatmap.mode != rosu.GameMode.Osu or beatmap.is_suspicious():
        raise ValueError("PP requires a supported osu!standard beatmap.")
    attrs = rosu.Difficulty(mods=mods, lazer=client == "lazer").calculate(beatmap)
    objects = attrs.n_circles + attrs.n_sliders + attrs.n_spinners
    if objects == 0 or misses > objects:
        raise ValueError("Miss count exceeds the map's object count.")
    if client == "stable" and accuracy > 1 - misses / objects + 1e-9:
        raise ValueError("This accuracy is impossible with the stated misses.")
    if combo is not None and (
        isinstance(combo, bool) or not isinstance(combo, int) or not 0 <= combo <= attrs.max_combo
    ):
        raise ValueError("Combo is outside the beatmap's combo range.")
    if client == "lazer" and (misses or (combo is not None and combo < attrs.max_combo)):
        raise ValueError("Broken lazer plays require slider outcomes; an FC scenario cannot substitute for them.")
    kwargs = {
        "mods": mods,
        "lazer": client == "lazer",
        "accuracy": accuracy * 100,
        "misses": misses,
        "hitresult_priority": rosu.HitResultPriority.WorstCase,
    }
    if combo is not None:
        kwargs["combo"] = combo
    result = rosu.Performance(**kwargs).calculate(beatmap).pp
    if not math.isfinite(result) or result < 0:
        raise ValueError("PP calculation produced an invalid result.")
    return result
