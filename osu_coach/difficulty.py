"""Thin, fail-soft wrapper around rosu-pp (official osu! difficulty algorithm port).

Gives star rating and per-skill ratings (aim / speed / reading) plus per-400 ms
strain peaks used to tell "aim-heavy" from "speed-heavy" parts of a map.
"""
from __future__ import annotations

import math

try:  # pragma: no cover - import guard
    import rosu_pp_py as rosu
except Exception:  # noqa: BLE001
    rosu = None

ATTR_NAMES = ["stars", "aim", "speed", "reading", "flashlight", "slider_factor", "speed_note_count",
              "aim_difficult_strain_count", "speed_difficult_strain_count", "ar", "hp",
              "great_hit_window", "n_circles", "n_sliders", "n_spinners", "max_combo"]


def available() -> bool:
    return rosu is not None


def _map(osu_bytes: bytes):
    return rosu.Beatmap(bytes=osu_bytes)


def _kwargs(mods: int, rate: float | None, lazer_mods: list | None, lazer: bool) -> dict:
    if lazer_mods:
        # lazer replays: the exact mod list incl. settings (custom rates, Difficulty Adjust, Classic ...)
        return {"mods": [{"acronym": str(m["acronym"]), "settings": dict(m.get("settings") or {})}
                         for m in lazer_mods if m.get("acronym")], "lazer": True}
    kw = {"mods": int(mods), "lazer": bool(lazer)}
    if rate and abs(rate - _legacy_rate(mods)) > 1e-6:
        kw["clock_rate"] = float(rate)
    return kw


def _difficulty(mods: int, rate: float | None, lazer_mods: list | None, lazer: bool):
    try:
        return rosu.Difficulty(**_kwargs(mods, rate, lazer_mods, lazer))
    except Exception:  # noqa: BLE001 - mods rosu-pp doesn't know: fall back to legacy bits + rate
        if not lazer_mods:
            raise
        return rosu.Difficulty(**_kwargs(mods, rate, None, lazer))


def attributes(osu_bytes: bytes, mods: int = 0, rate: float | None = None, lazer_mods: list | None = None,
               lazer: bool = False) -> dict:
    if rosu is None:
        return {}
    try:
        m = _map(osu_bytes)
        if m.is_suspicious():
            return {}
        a = _difficulty(mods, rate, lazer_mods, lazer).calculate(m)
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for k in ATTR_NAMES:
        v = getattr(a, k, None)
        if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
            out[k] = float(v)
    return out


def strains(osu_bytes: bytes, mods: int = 0, rate: float | None = None, lazer_mods: list | None = None,
            lazer: bool = False) -> dict | None:
    if rosu is None:
        return None
    try:
        m = _map(osu_bytes)
        s = _difficulty(mods, rate, lazer_mods, lazer).strains(m)
    except Exception:  # noqa: BLE001
        return None
    return {
        "section_length": float(s.section_length),
        "aim": list(s.aim or []),
        "speed": list(s.speed or []),
        "reading": list(getattr(s, "reading", None) or []),
    }


def _legacy_rate(mods: int) -> float:
    if mods & (64 | 512):
        return 1.5
    if mods & 256:
        return 0.75
    return 1.0


def section_index(real_time: float, second_object_real_time: float, section_length: float, n: int) -> int:
    """Map a (rate-adjusted) time to its strain-peak section, mirroring osu!'s
    StrainSkill: sections end at multiples of section_length, the first one
    ending at ceil(t_second_object / L) * L."""
    if n <= 0:
        return -1
    first_end = math.ceil(second_object_real_time / section_length) * section_length
    k = math.ceil((real_time - first_end) / section_length) if real_time > first_end else 0
    return int(min(max(k, 0), n - 1))
