"""The play goals' records: plays as evidence, and what the assessment and the recommendations return (codes, which
the slice turns into text)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from osu_coach.domain.analysis.events import Events
from osu_coach.domain.analysis.models import ReplayMeta

# A map in one mod configuration: a row of the goal pool, or the target's (``md5``, ``mods``, ``client``, ``stars``,
# ``ar``, ``od``, ``bpm``, ``length_s``, demand shares ``s_<skill>``, ``pp_curve``, ...). JSON data, kept as it is read.
MapRow = Mapping[str, Any]


@dataclass(frozen=True)
class GoalPlay:
    """A play as the play goals read it: its meta, misses and breaks, the share of its played notes in streams and
    jumps, and for lazer plays the mods with settings read back from the replay file (None when they couldn't be)."""

    key: str
    meta: ReplayMeta
    events: Events = field(repr=False)
    stream_share: float = 0.0
    jump_share: float = 0.0
    lazer_mods: object = None


@dataclass(frozen=True)
class EvidenceRow:
    """A verified play of the player in a supported mod configuration (``mods_name``)."""

    key: str
    beatmap_md5: str
    date: str  # the play's date as text: rows sort by it
    client: str
    mods_name: str
    completed: bool
    n_played: int
    n_objects: int
    stars: float
    ar: float
    od: float
    bpm: float
    length_s: float
    accuracy: float
    aim: float
    speed: float
    fc: bool
    breaks: int
    stream_share: float
    jump_share: float


@dataclass(frozen=True)
class AccuracyRange:
    """The middle 80% of the accuracy of comparable plays."""

    low: float
    high: float
    median: float
    plays: int
    maps: int


@dataclass(frozen=True)
class Reason:
    """Why: a code and the values its text shows."""

    code: str
    values: tuple = ()


@dataclass(frozen=True)
class Reach:
    """How reachable an FC of the target is."""

    verdict: str  # fc_done | fc_near | stretch | beyond | beyond_for_now | unknown
    reasons: tuple[Reason, ...]
    confidence: str  # unassessed | limited | moderate


@dataclass(frozen=True)
class Blocker:
    """A skill whose misses and breaks stop the player's attempts of the target."""

    skill: str
    events: int
    attempts: int
    timestamps: tuple[str, ...]


@dataclass(frozen=True)
class Recommendation:
    """A map to play next, and the objective for it."""

    map: MapRow
    practice_accuracy: float
    accuracy: AccuracyRange | None
    pp: float | None  # PP of an FC at the practice accuracy
    pp_ss: float | None
    pp_accuracy: float | None
    local_best_accuracy: float | None
    achieved: bool
    stage: str  # starter | core | stretch
    projected: bool  # comparable plays support the FC scenario
    score: float
