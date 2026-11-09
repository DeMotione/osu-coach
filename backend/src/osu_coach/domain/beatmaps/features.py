"""Per-object pattern features (spacing, rhythm, angles, streams, jumps, position).

Everything is computed on the *playable* beatmap (mods applied: HR flip, stacking,
CS/AR changes) and converted to real time with the play rate, so a DT play and a
NM play of the same pattern produce comparable numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from osu_coach.domain.beatmaps.models import PlayableBeatmap
from osu_coach.domain.numeric.arrays import ArrayRecord, Bools, Floats, Ints, Texts

RUN_SNAP_MAX = 0.34  # 1/3 beat or faster counts as "tight" (streams/bursts)
RUN_DT_MAX = 200.0  # ms (real time); keeps very slow maps out of streams
JUMP_DIST = 2.0  # spacing in circle diameters
DIR8 = ["right", "down-right", "down", "down-left", "left", "up-left", "up", "up-right"]


@dataclass(frozen=True, slots=True)
class MapObjects(ArrayRecord):
    """One item per object of the playable beatmap: position, timing, spacing, rhythm, slider shape, runs and the
    pattern label. ``*_real`` values are in real time (the play rate applied)."""

    idx: Ints
    kind: Texts
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
    density: Ints  # objects visible at hit time
    prev_idx: Floats  # the previous object that isn't a spinner (NaN: none)
    dt: Floats
    dt_end: Floats
    dist: Floats
    dist_norm: Floats  # circle diameters
    angle: Floats
    direction: Floats
    dir8: Texts
    snap: Floats  # beats since the previous object
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

    DEFAULTS: ClassVar = {"run_id": -1, "run_len": 1, "run_pos": 0, "slider_vel_change": 0.0}


def _quadrant(x: float, y: float) -> str:
    v = "top" if y < 192 else "bottom"
    h = "left" if x < 256 else "right"
    return f"{v}-{h}"


def _rhythm_label(snap: float) -> str:
    for label, value in (
        ("1/8", 0.125),
        ("1/6", 1 / 6),
        ("1/4", 0.25),
        ("1/3", 1 / 3),
        ("1/2", 0.5),
        ("1/1", 1.0),
        ("2/1", 2.0),
    ):
        if abs(snap - value) <= value * 0.08:
            return label
    return "other" if snap < 2.2 else "break"


SHAPE_STEP = 8.0  # osu!px between path samples for the slider shape
SHAPE_SHARP = math.radians(40)  # a direction change this big between two samples = a corner (red anchor)


def slider_shape(o) -> tuple[float, int, int]:
    """Shape of a slider's path (one span): ``turn`` = total direction change in radians (a straight slider 0, a
    half circle π, a full circle 2π, wiggles add up), ``corners`` = sharp corners (40°+ at once, e.g. red
    anchors), ``bends`` = how often the path switches between turning left and right (S-shapes, zig-zags)."""
    path = getattr(o, "path", None)
    if path is None or path.length <= SHAPE_STEP:
        return 0.0, 0, 0
    n = max(2, int(path.length / SHAPE_STEP))
    pts = np.array([path.position_at(i / n) for i in range(n + 1)], dtype=float)
    d = np.diff(pts, axis=0)
    keep = np.hypot(d[:, 0], d[:, 1]) > 1e-6
    d = d[keep]
    if len(d) < 2:
        return 0.0, 0, 0
    ang = np.arctan2(d[:, 1], d[:, 0])
    da = (np.diff(ang) + np.pi) % (2 * np.pi) - np.pi
    turn = float(np.abs(da).sum())
    corners = int((np.abs(da) >= SHAPE_SHARP).sum())
    sig = np.sign(da[np.abs(da) > math.radians(2)])
    bends = int((np.diff(sig) != 0).sum()) if len(sig) > 1 else 0
    return turn, corners, bends


def object_features(pb: PlayableBeatmap) -> MapObjects:
    bm = pb.beatmap
    objs = bm.objects
    rate = pb.rate
    diameter = 2 * pb.radius_raw
    rows = []
    starts = [pb.pos(o) for o in objs]
    ends = [pb.end_pos(o) for o in objs]
    first_t = objs[0].time if objs else 0.0
    last_t = objs[-1].time if objs else 1.0
    span = max(last_t - first_t, 1.0)
    times = np.array([o.time for o in objs])

    prev = None  # index of previous non-spinner object
    prevprev = None
    for i, o in enumerate(objs):
        x, y = starts[i]
        ex, ey = ends[i]
        beat = bm.beat_length_at(o.time)
        row = {
            "idx": i,
            "kind": o.kind,
            "time": o.time,
            "end_time": o.end_time,
            "x": x,
            "y": y,
            "end_x": ex,
            "end_y": ey,
            "new_combo": o.new_combo,
            "beat_len": beat,
            "bpm_real": 60000.0 / beat * rate,
            "quadrant": _quadrant(x, y),
            "grid": int(min(2, max(0, x // (512 / 3)))) + 3 * int(min(2, max(0, y // (384 / 3)))),
            "edge_dist": min(x, 512 - x, y, 384 - y),
            "time_frac": (o.time - first_t) / span,
            "slider_len": o.pixel_length if o.is_slider else 0.0,
            "slider_dur_real": (o.end_time - o.time) / rate if o.is_slider else 0.0,
            "slider_spans": o.spans if o.is_slider else 0,
            "slider_vel_real": o.velocity * rate if o.is_slider else 0.0,
        }
        if o.is_slider:
            row["slider_turn"], row["slider_corners"], row["slider_bends"] = slider_shape(o)
        else:
            row["slider_turn"], row["slider_corners"], row["slider_bends"] = 0.0, 0, 0
        # objects visible at hit time (reading density)
        hi = np.searchsorted(times, o.time + pb.preempt, side="right")
        lo = np.searchsorted(times, o.time, side="left")
        row["density"] = int(hi - lo)
        if o.is_spinner or prev is None:
            row.update(
                prev_idx=None if prev is None else prev,
                dt=np.nan,
                dt_end=np.nan,
                dist=np.nan,
                dist_norm=np.nan,
                angle=np.nan,
                direction=np.nan,
                dir8=None,
                snap=np.nan,
                rhythm=None,
                from_slider=False,
                mx=np.nan,
                my=np.nan,
            )
        else:
            p = objs[prev]
            px, py = ends[prev]
            dx, dy = x - px, y - py
            dist = math.hypot(dx, dy)
            dt = o.time - p.time
            dt_end = max(o.time - p.end_time, 1.0)
            ang = np.nan
            if prevprev is not None:
                ax, ay = starts[prevprev][0] - starts[prev][0], starts[prevprev][1] - starts[prev][1]
                bx, by = x - starts[prev][0], y - starts[prev][1]
                la, lb = math.hypot(ax, ay), math.hypot(bx, by)
                if la > 1e-6 and lb > 1e-6:
                    c = (ax * bx + ay * by) / (la * lb)
                    ang = math.degrees(math.acos(max(-1.0, min(1.0, c))))
            direction = (math.degrees(math.atan2(dy, dx)) + 360) % 360 if dist > 1e-6 else np.nan
            snap = dt / beat if beat > 0 else np.nan
            row.update(
                prev_idx=prev,
                dt=dt,
                dt_end=dt_end,
                dist=dist,
                dist_norm=dist / diameter,
                angle=ang,
                direction=direction,
                dir8=None if np.isnan(direction) else DIR8[int(((direction + 22.5) % 360) // 45)],
                snap=snap,
                rhythm=_rhythm_label(snap),
                from_slider=p.is_slider,
                mx=dx,
                my=dy,
            )
        row["dt_real"] = row["dt"] / rate if not np.isnan(row["dt"]) else np.nan
        row["dt_end_real"] = row["dt_end"] / rate if not np.isnan(row["dt_end"]) else np.nan
        row["velocity_real"] = (row["dist"] / max(row["dt_end_real"], 25.0)) if not np.isnan(row["dist"]) else np.nan
        rows.append(row)
        if not o.is_spinner:
            prevprev, prev = prev, i

    columns = {f: [r.get(f) for r in rows] for f in rows[0]} if rows else {}
    return _labelled(MapObjects.from_columns(columns, n=len(rows)))


def features_at_rate(template: MapObjects, rate: float) -> MapObjects:
    """Reapply real-time features to one map's geometry at a different play rate.

    ``template`` is the output of ``object_features`` at rate 1 with the same geometry-changing mods (records are
    immutable, so another configuration can reuse it)."""
    if not len(template) or rate == 1.0:
        return template
    t = template
    sliders = t.kind == "slider"
    dt_end_real = t.dt_end / rate
    return _labelled(
        t.replace(
            bpm_real=60000.0 / t.beat_len * rate,
            slider_dur_real=np.where(sliders, t.end_time - t.time, 0.0) / rate,
            slider_vel_real=t.slider_vel_real * rate,
            dt_real=t.dt / rate,
            dt_end_real=dt_end_real,
            velocity_real=t.dist / np.maximum(dt_end_real, 25.0),
        )
    )


SLIDER_CHANGE_WINDOW = 2000.0  # ms (real): a slider this soon after the previous one is compared with it


def _labelled(t: MapObjects) -> MapObjects:
    """The objects with their slider context, runs (bursts / streams) and pattern labels."""
    if not len(t):
        return t
    return _label_patterns(_label_runs(_slider_context(t)))


def _slider_context(t: MapObjects) -> MapObjects:
    """``slider_vel_change`` = |ln(speed / previous slider's speed)| when the previous slider ended at most 2 s
    earlier (0.69 = twice or half as fast, 0 = same speed or no slider before); ``slider_next_gap`` = real ms
    from the slider's end to the next object (short = you must leave the slider and move on quickly)."""
    n = len(t)
    change = np.zeros(n)
    gap = np.full(n, np.nan)
    kinds, start, end, v = t.kind, t.time, t.end_time, t.slider_vel_real
    rate = float(t.bpm_real[0] * t.beat_len[0] / 60000.0) if n else 1.0
    last = None
    for i in range(n):
        if kinds[i] != "slider":
            continue
        if last is not None and (start[i] - end[last]) / rate <= SLIDER_CHANGE_WINDOW and v[last] > 0 and v[i] > 0:
            change[i] = abs(math.log(v[i] / v[last]))
        if i + 1 < n:
            gap[i] = max(0.0, (start[i + 1] - end[i]) / rate)
        last = i
    return t.replace(slider_vel_change=change, slider_next_gap=gap)


def _label_runs(t: MapObjects) -> MapObjects:
    n = len(t)
    kinds = t.kind
    spinner = kinds == "spinner"
    tight = (t.snap <= RUN_SNAP_MAX) & (t.dt_real <= RUN_DT_MAX) & ~spinner
    run_id = np.full(n, -1)
    run_len = np.ones(n, dtype=int)
    run_pos = np.zeros(n, dtype=int)
    rid = -1
    i = 0
    while i < n:
        if spinner[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and tight[j + 1] and not spinner[j + 1]:
            j += 1
        if j > i:
            rid += 1
            run_id[i : j + 1] = rid
            run_len[i : j + 1] = j - i + 1
            run_pos[i : j + 1] = np.arange(j - i + 1)
        i = j + 1
    # BPM of the stream expressed in 1/4 notes, real time; the first note of a run gets the run's median speed
    dtr = np.where((run_pos > 0) & (t.dt_real > 0), t.dt_real, np.nan)  # simultaneous notes (2B maps): dt = 0
    with np.errstate(divide="ignore", invalid="ignore"):
        per_note = 15000.0 / dtr
    stream_bpm = np.full(n, np.nan)
    for r in range(rid + 1):
        m = run_id == r
        values = per_note[m]
        values = values[~np.isnan(values)]
        if len(values):
            stream_bpm[m] = np.median(values)
    return t.replace(run_id=run_id, run_len=run_len, run_pos=run_pos, stream_bpm=stream_bpm)


def _label_patterns(t: MapObjects) -> MapObjects:
    pattern = []
    for kind, run_len, dist_norm, snap in zip(t.kind, t.run_len, t.dist_norm, t.snap, strict=True):
        if kind == "spinner":
            pattern.append("spinner")
        elif run_len >= 9:
            pattern.append("stream")
        elif run_len >= 3:
            pattern.append("burst")
        elif not np.isnan(dist_norm) and dist_norm >= JUMP_DIST and snap <= 0.55:
            pattern.append("jump")
        elif not np.isnan(dist_norm) and dist_norm >= JUMP_DIST:
            pattern.append("spaced")
        else:
            pattern.append("single")
    return t.replace(pattern=np.array(pattern, dtype=object), spaced_stream=(t.run_len >= 3) & (t.dist_norm >= 0.9))
