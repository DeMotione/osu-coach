"""Configuration-specific pool records for immediate play goals."""

from __future__ import annotations

from osu_coach.beatmaps.domain import Beatmap
from osu_coach.beatmaps.performance import calculate
from osu_coach.maps.domain import map_stats

CONFIGS = {"NM": 0, "HD": 8, "HR": 16, "HDHR": 24, "DT": 64, "HDDT": 72, "HRDT": 80, "HDHRDT": 88}
ACCURACIES = (0.9, 0.95, 0.97, 0.98, 0.99, 1.0)


def configuration(bm: Beatmap, osu_bytes: bytes, mods: str, client: str, status: str = "unknown") -> dict:
    if mods not in CONFIGS or client not in ("stable", "lazer"):
        raise ValueError("Unsupported play-goal configuration.")
    stats = map_stats(bm, osu_bytes, CONFIGS[mods])
    if not stats or not stats.get("stars"):
        raise ValueError("The map has no supported difficulty or too few playable objects.")
    return {
        **stats,
        "mods": mods,
        "client": client,
        "status": status,
        "length_s": stats["drain_length"],
        "pp_curve": [{"accuracy": acc, "pp": calculate(osu_bytes, CONFIGS[mods], client, acc)} for acc in ACCURACIES],
    }
