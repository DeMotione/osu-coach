"""The notes and key presses of one analysed replay: what each hit object was and what the player did.

Value objects with one numpy array per field (:class:`~osu_coach.domain.numeric.arrays.ArrayRecord`); text fields
hold ``str`` or None. They exist only while one replay is analysed or shown: everything the profile needs from a
replay is kept as its :class:`~osu_coach.domain.player.summary.PlaySummary`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from osu_coach.domain.numeric.arrays import ArrayRecord, Bools, Floats, Ints, Texts


@dataclass(frozen=True, slots=True)
class HitObjects(ArrayRecord):
    """One item per hit object of a replay."""

    # what the object is (beatmap features)
    idx: Ints
    kind: Texts  # circle | slider | spinner
    time: Floats
    end_time: Floats
    x: Floats
    y: Floats
    end_x: Floats
    end_y: Floats
    new_combo: Bools
    beat_len: Floats
    bpm_real: Floats
    quadrant: Texts
    grid: Ints
    edge_dist: Floats
    time_frac: Floats
    slider_len: Floats
    slider_dur_real: Floats
    slider_spans: Ints
    slider_vel_real: Floats
    slider_turn: Floats
    slider_corners: Ints
    slider_bends: Ints
    density: Ints
    prev_idx: Floats
    dt: Floats
    dt_end: Floats
    dist: Floats
    dist_norm: Floats
    angle: Floats
    direction: Floats
    dir8: Texts
    snap: Floats
    rhythm: Texts
    from_slider: Bools
    mx: Floats
    my: Floats
    dt_real: Floats
    dt_end_real: Floats
    velocity_real: Floats
    slider_vel_change: Floats
    slider_next_gap: Floats
    run_id: Ints
    run_len: Ints
    run_pos: Ints
    stream_bpm: Floats
    pattern: Texts
    spaced_stream: Bools
    # what the player did (judgement simulation)
    result: Ints
    head_hit: Bools
    head_result: Ints
    hit_time: Floats
    hit_error: Floats
    click_x: Floats
    click_y: Floats
    key: Texts
    press_id: Floats
    miss_reason: Texts
    miss_dist: Floats
    miss_x: Floats
    miss_y: Floats
    forced_miss: Bools
    n_events: Ints
    n_events_hit: Ints
    end_hit: Texts  # True / False, None for objects without an end
    broke: Bools
    break_reason: Texts
    spins: Floats
    spins_required: Floats
    played: Bools
    err_real: Floats
    radius: Floats
    err_dx: Floats
    err_dy: Floats
    aim_err: Floats
    start_x: Floats
    start_y: Floats
    along: Floats
    cross: Floats
    aim_strain: Floats
    speed_strain: Floats
    reading_strain: Floats
    aim_eq: Floats
    speed_eq: Floats

    DEFAULTS: ClassVar[Mapping[str, Any]] = {
        "kind": "circle",
        "played": True,
        "head_hit": True,
        "head_result": 300,
        "result": 300,
        "run_id": -1,
        "run_len": 1,
        "radius": 32.0,
    }

    def played_notes(self) -> HitObjects:
        """The objects that were played, without spinners."""
        return self.take(self.played & (self.kind != "spinner"))


@dataclass(frozen=True, slots=True)
class KeyPresses(ArrayRecord):
    """One item per key press of a replay."""

    id: Ints
    key: Texts
    time: Floats
    release: Floats
    duration: Floats
    x: Floats
    y: Floats
    target: Floats
    outcome: Texts
    gap_prev: Floats
    prev_key: Texts
    alternated: Bools
    same_key_gap: Floats
    target_pattern: Texts
    target_dt: Floats
    target_run_len: Floats
    hold_ratio: Floats
