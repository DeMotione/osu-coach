"""What the profile keeps of one replay: a small per-play summary, computed once from its notes.

Every part is unweighted counts, sums or per-play values; the play's weight (how close its star rating is to the
player's level) is applied when :mod:`build` adds the summaries of all plays up. So the profile never needs every
note of every replay at once.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from osu_coach.domain.analysis.events import Events, events
from osu_coach.domain.analysis.models import Play, ReplayMeta
from osu_coach.domain.analysis.notes import HitObjects
from osu_coach.domain.numeric.arrays import ArrayRecord, Bools, Floats, Ints, Texts
from osu_coach.domain.player.algorithm import timing_evidence_eligible
from osu_coach.domain.player.constants import FAST_JUMP_MS
from osu_coach.domain.player.engines.comfort.ratings import RatingInputs, rating_inputs
from osu_coach.domain.player.engines.comfort.skill_values import PlayContext
from osu_coach.domain.player.engines.irt.items import IrtGroups, group_table
from osu_coach.domain.player.measures.aim import AimSummary, JumpSummary, aim_summary, jump_summary
from osu_coach.domain.player.measures.miss_notes import MissNotes, miss_notes
from osu_coach.domain.player.measures.streams import StreamSummary, stream_summary
from osu_coach.domain.player.measures.tapping import PressSummary, TimingSummary, press_summary, timing_summary
from osu_coach.domain.replays.configuration import from_meta


@dataclass(frozen=True, slots=True)
class NoteSummary:
    """The played notes of a replay (spinners left out): misses by cause and slider results."""

    notes: int
    misses: int
    miss_causes: Mapping[str, int]  # head misses by cause (aim, speed_aim, early, late, no_tap, lost, notelock)
    sliders: int
    slider_heads_hit: int
    slider_breaks: Mapping[str, int]  # by reason (follow, released, key_swap)
    slider_end_misses: int  # slider ends missed after the head was hit


def fast_pattern(notes: HitObjects) -> np.ndarray:
    """Bursts and streams (3+ notes at 1/4 or faster, any spacing) and very fast jumps (≤ 125 ms apart)."""
    jumpy = np.fromiter((p in ("jump", "spaced") for p in notes.pattern.tolist()), dtype=bool, count=len(notes))
    return (notes.run_len >= 3) | (jumpy & (notes.dt_real <= FAST_JUMP_MS))


def miss_causes(notes: HitObjects) -> np.ndarray:
    """The cause of every head miss (None for hits): the miss reason, with aim misses on fast patterns
    (:func:`fast_pattern`) as ``speed_aim`` — the tap was in time but the cursor couldn't keep up."""
    cause = np.where(notes.head_hit, None, notes.miss_reason).astype(object)
    cause[(cause == "aim") & fast_pattern(notes)] = "speed_aim"
    return cause


def note_summary(notes: HitObjects) -> NoteSummary:
    """The :class:`NoteSummary` of the played notes of one replay (:meth:`HitObjects.played_notes`)."""
    hit = notes.head_hit
    missed = ~hit
    causes = Counter("lost" if c is None else c for c in miss_causes(notes)[missed].tolist())
    sliders = notes.kind == "slider"
    broke = sliders & notes.broke
    breaks = Counter("follow" if r is None else r for r in notes.break_reason[broke].tolist())
    end_missed = np.fromiter(
        (v is False or v is np.False_ for v in notes.end_hit.tolist()), dtype=bool, count=len(notes)
    )
    return NoteSummary(
        notes=len(notes),
        misses=int(missed.sum()),
        miss_causes=dict(causes),
        sliders=int(sliders.sum()),
        slider_heads_hit=int((sliders & hit).sum()),
        slider_breaks=dict(breaks),
        slider_end_misses=int((sliders & hit & end_missed).sum()),
    )


CHART_FIELDS = (
    "time", "x", "y", "kind", "head_hit", "head_result", "err_real", "err_dx", "err_dy", "radius", "along",
    "cross", "dist_norm", "miss_reason", "start_x", "start_y", "slider_len", "slider_vel_real", "broke",
    "pattern", "stream_bpm", "run_len", "spaced_stream",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class ChartNotes(ArrayRecord):
    """The few fields of the played notes that the charts, the click picture and the setup tips show."""

    time: Floats
    x: Floats
    y: Floats
    kind: Texts
    head_hit: Bools
    head_result: Ints
    err_real: Floats
    err_dx: Floats
    err_dy: Floats
    radius: Floats
    along: Floats
    cross: Floats
    dist_norm: Floats
    miss_reason: Texts
    start_x: Floats
    start_y: Floats
    slider_len: Floats
    slider_vel_real: Floats
    broke: Bools
    pattern: Texts
    stream_bpm: Floats
    run_len: Ints
    spaced_stream: Bools
    miss_cause: Texts
    replay_key: Texts
    w: Floats  # the play's weight; 1 until the profile sets it

    DEFAULTS: ClassVar = {"w": 1.0}


@dataclass(frozen=True, slots=True)
class PlaySummary:
    """Everything the profile and the pages keep of one play: its meta, and its notes reduced to counts, moments and
    a few small per-note records (what is analysed once and stored; the full analysis is read again only for a page
    about that one replay)."""

    key: str
    meta: ReplayMeta
    notes: NoteSummary
    aim: AimSummary
    ratings: RatingInputs
    timing: TimingSummary
    jumps: JumpSummary
    streams: StreamSummary
    miss: MissNotes
    presses: PressSummary
    chart: ChartNotes
    press_lengths: np.ndarray  # how long each key press was held (ms, map time)
    events: Events  # misses, combo and slider breaks
    stream_share: float  # of the played notes: in streams
    jump_share: float  # ... jumps
    irt: IrtGroups  # the notes as Star-Scale IRT items against their difficulty, grouped (engines/irt)


def summarize(play: Play) -> PlaySummary:
    """The summary of one analysed play."""
    played = play.notes.played_notes()
    m = play.meta
    inputs = rating_inputs(played, play_context(play), timing_evidence_eligible(m.mods, m.accuracy), m.od)
    patterns = played.pattern
    return PlaySummary(
        key=play.key,
        meta=m,
        press_lengths=play.presses.duration,
        events=events(play.notes),
        stream_share=float((patterns == "stream").mean()) if len(played) else 0.0,
        jump_share=float((patterns == "jump").mean()) if len(played) else 0.0,
        notes=note_summary(played),
        aim=aim_summary(played),
        ratings=inputs,
        timing=timing_summary(played),
        jumps=jump_summary(played, miss_causes(played)),
        streams=stream_summary(played),
        chart=ChartNotes(
            **{name: getattr(played, name) for name in CHART_FIELDS},
            miss_cause=miss_causes(played),
            replay_key=np.full(len(played), play.key, dtype=object),
            w=np.ones(len(played)),
        ),
        presses=press_summary(play.notes, play.presses, m.rate),
        miss=miss_notes(played, m.stars, m.ar, bool(m.mods & 8), miss_causes(played), fast_pattern(played)),
        irt=group_table(played, m, timing_evidence_eligible(m.mods, m.accuracy)),
    )


def play_context(play: Play) -> PlayContext:
    """The facts about the play the skill values read besides its notes."""
    m = play.meta
    mc = m.map_max_combo if m.map_max_combo == m.map_max_combo else 0
    return PlayContext(
        key=play.key,
        map=from_meta(m.to_dict()).key,
        completed=bool(m.completed),
        combo_ratio=min(1.0, m.max_combo / mc) if mc else math.nan,
        ar=m.ar,
        accuracy=m.accuracy,
        stars=m.stars,
        rate=m.rate,
        hidden=bool(m.mods & 8),
        hidden_custom=any(
            str(mod.get("acronym", "")).upper() == "HD" and bool(mod.get("settings")) for mod in m.lazer_mods
        ),
        flashlight=bool(m.mods & 1024),
    )
