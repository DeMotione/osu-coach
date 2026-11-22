"""Explicit PP scenarios for supported standard configurations, with no silent fallback."""

from __future__ import annotations

import math
from collections.abc import Sequence
from importlib.metadata import version

import rosu_pp_2026 as rosu  # osu!'s pp and star rating of 2026-07-03 (see beatmaps.difficulty)

CALCULATOR_VERSION = version("rosu-pp-2026")
SUPPORTED_MODS = (0, 8, 16, 24, 64, 72, 80, 88)


def _check(mods: int, client: str, accuracy: float) -> None:
    if isinstance(mods, bool) or mods not in SUPPORTED_MODS or client not in ("stable", "lazer"):
        raise ValueError("Unsupported PP configuration.")
    if (
        isinstance(accuracy, bool)
        or not isinstance(accuracy, (int, float))
        or not math.isfinite(accuracy)
        or not 0 <= accuracy <= 1
    ):
        raise ValueError("Accuracy must be a finite fraction between 0 and 1.")


def _standard(osu_bytes: bytes):
    beatmap = rosu.Beatmap(bytes=osu_bytes)
    if beatmap.mode != rosu.GameMode.Osu or beatmap.is_suspicious():
        raise ValueError("PP requires a supported osu!standard beatmap.")
    return beatmap


def _valid(result: float) -> float:
    if not math.isfinite(result) or result < 0:
        raise ValueError("PP calculation produced an invalid result.")
    return result


def pp_curve(osu_bytes: bytes, mods: int, client: str, accuracies: Sequence[float]) -> list[float]:
    """The pp of a full combo at each of ``accuracies``, as :func:`calculate` gives it, with the map's difficulty
    calculated once (the pool's pp table, the play goals' targets)."""
    for accuracy in accuracies:
        _check(mods, client, accuracy)
    lazer = client == "lazer"
    attrs = rosu.Difficulty(mods=mods, lazer=lazer).calculate(_standard(osu_bytes))
    if attrs.n_circles + attrs.n_sliders + attrs.n_spinners == 0:
        raise ValueError("PP requires a map with objects.")
    return [
        _valid(
            rosu.Performance(
                mods=mods,
                lazer=lazer,
                accuracy=accuracy * 100,
                misses=0,
                hitresult_priority=rosu.HitResultPriority.WorstCase,
            )
            .calculate(attrs)
            .pp
        )
        for accuracy in accuracies
    ]


def calculate(
    osu_bytes: bytes,
    mods: int = 0,
    client: str = "stable",
    accuracy: float = 1.0,
    misses: int = 0,
    combo: int | None = None,
) -> float:
    _check(mods, client, accuracy)
    if isinstance(misses, bool) or not isinstance(misses, int) or misses < 0:
        raise ValueError("Miss count must be a non-negative integer.")
    beatmap = _standard(osu_bytes)
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
    return _valid(rosu.Performance(**kwargs).calculate(beatmap).pp)
