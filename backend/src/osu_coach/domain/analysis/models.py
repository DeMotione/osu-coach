"""An analysed play: the replay's metadata (:class:`ReplayMeta`) with its notes and key presses (:class:`Play`)."""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Any

from osu_coach.domain.analysis.judge_lazer import lazer_mod_settings
from osu_coach.domain.analysis.notes import HitObjects, KeyPresses
from osu_coach.domain.beatmaps.models import Beatmap, PlayableBeatmap
from osu_coach.domain.replays.models import Replay

ANALYSIS_VERSION = 9


class UnsupportedReplay(ValueError):
    """A replay osu-coach can't analyse faithfully (reason in the message)."""


def playable(bm: Beatmap, replay: Replay) -> PlayableBeatmap:
    """The beatmap as it was played: legacy mods, lazer's speed changes, Difficulty Adjust and Mirror."""
    mods = lazer_mod_settings(replay)
    da = mods.get("DA") or {}
    overrides = {
        k: float(da[src])
        for k, src in (
            ("cs", "circle_size"),
            ("ar", "approach_rate"),
            ("od", "overall_difficulty"),
            ("hp", "drain_rate"),
        )
        if isinstance(da.get(src), (int, float))
    }
    mirror = None
    if "MR" in mods:
        refl = mods["MR"].get("reflection", 0)
        mirror = {0: "horizontal", 1: "vertical", 2: "both"}.get(refl, str(refl).lower())
        if mirror not in ("horizontal", "vertical", "both"):
            mirror = "horizontal"
    return PlayableBeatmap(bm, replay.mods, rate=replay.rate, overrides=overrides or None, mirror=mirror)


LazerMod = Mapping[str, Any]  # a lazer mod as the replay stores it: {"acronym": "DT", "settings": {...}}


@dataclass(frozen=True, slots=True)
class ReplayMeta:
    """What a replay is: the map, mods, client, result and the analysis checks (one per analysed play)."""

    key: str
    player: str = ""
    date: dt.datetime | None = None
    beatmap_md5: str = ""
    title: str = ""
    artist: str = ""
    version: str = ""
    creator: str = ""
    beatmap_id: int = 0
    beatmapset_id: int = 0
    map_name: str = ""
    mods: int = 0
    mod_string: str = "NM"
    rate: float = 1.0
    lazer_mods: tuple[LazerMod, ...] = ()
    rules: str = "stable"
    client: str = "stable"
    replay_version: int = 0
    n300: int = 0
    n100: int = 0
    n50: int = 0
    nmiss: int = 0
    max_combo: int = 0
    score: int = 0
    accuracy: float = math.nan
    header_empty: bool = False
    sim_counts: tuple[int, ...] = ()
    sim_max_combo: int = 0
    sim_match: bool | None = None
    sim_agreement: float = math.nan
    n_objects: int = 0
    n_played: int = 0
    completed: bool = True
    cs: float = math.nan
    ar: float = math.nan
    od: float = math.nan
    hp: float = math.nan
    bpm: float = math.nan
    length_s: float = math.nan
    ur: float = math.nan
    mean_error: float = math.nan
    head_misses: int = 0
    relax_or_autopilot: bool = False
    source_path: str = ""
    source: str = ""  # the install or folder the replay was found in
    analysis_version: int = 0
    # difficulty attributes (rosu-pp, the play's mods)
    stars: float = math.nan
    aim: float = math.nan
    speed: float = math.nan
    slider_factor: float = math.nan
    speed_note_count: float = math.nan
    map_max_combo: float = math.nan

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> ReplayMeta:
        """From the dict an analysis was saved with (older ones lack some keys; unknown keys are dropped)."""
        known = {f.name for f in fields(cls)}
        out = {k: v for k, v in values.items() if k in known and v is not None}
        for name in ("lazer_mods", "sim_counts"):
            if name in out:
                out[name] = tuple(out[name])
        return cls(**out)

    def to_dict(self) -> dict[str, Any]:
        """The dict the analysis cache stores (the same keys as before)."""
        out = {f.name: getattr(self, f.name) for f in fields(self)}
        out["lazer_mods"] = [dict(m) for m in self.lazer_mods]
        return out


@dataclass(frozen=True, slots=True)
class Play:
    """One analysed replay: its metadata, notes and key presses."""

    meta: ReplayMeta
    notes: HitObjects = field(repr=False)
    presses: KeyPresses = field(repr=False)

    @property
    def key(self) -> str:
        return self.meta.key


def along_cross(ex: float, ey: float, mx: float, my: float) -> tuple[float, float]:
    """Split an aim error (ex, ey) into the component along the movement
    direction (positive = overshoot) and across it (positive = clockwise side
    in screen coordinates, y pointing down)."""
    n = math.hypot(mx, my)
    if n < 1e-9:
        return (math.nan, math.nan)
    ux, uy = mx / n, my / n
    along = ex * ux + ey * uy
    cross = -ex * uy + ey * ux
    return (along, cross)
