"""The breaks of a play, in map order: judged misses (the results screen's count), slider heads missed while the
slider still scored ("combo break") and slider breaks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from osu_coach.domain.analysis.notes import HitObjects
from osu_coach.domain.numeric.arrays import ArrayRecord, Floats, Ints, Texts


@dataclass(frozen=True, slots=True)
class Events(ArrayRecord):
    time: Floats  # ms into the map
    idx: Ints  # the object's index in the map
    row: Ints  # its row in the objects the events were found in
    what: Texts  # miss | combo break | slider break
    reason: Texts  # the miss reason (aim, late, ...), spinner, or the slider break's (follow, released, key_swap)
    pattern: Texts  # the note's pattern; slider / spinner for those
    stream_bpm: Floats
    timestamp: Texts  # mm:ss:mmm


def timestamp(ms: float) -> str:
    """Map time as the osu! editor shows it: mm:ss:mmm."""
    ms = max(int(round(ms)), 0)
    return f"{ms // 60000:02d}:{ms // 1000 % 60:02d}:{ms % 1000:03d}"


def events(objects: HitObjects) -> Events:
    """The events of the played objects of one play, sorted by time (then map order)."""
    rows: list[tuple] = []
    played = np.flatnonzero(objects.played)
    for i in played.tolist():
        kind = objects.kind[i]
        pattern = "slider" if kind == "slider" else "spinner" if kind == "spinner" else objects.pattern[i]
        what = reason = None
        if objects.result[i] == 0:
            what, reason = "miss", ("spinner" if kind == "spinner" else (objects.miss_reason[i] or "lost"))
        elif kind == "slider" and not objects.head_hit[i]:
            what, reason = "combo break", objects.miss_reason[i] or "lost"
        if what:
            rows.append((objects.time[i], objects.idx[i], i, what, reason, pattern, objects.stream_bpm[i]))
        if kind == "slider" and bool(objects.broke[i]):
            rows.append(
                (
                    objects.time[i],
                    objects.idx[i],
                    i,
                    "slider break",
                    objects.break_reason[i] or "follow",
                    pattern,
                    objects.stream_bpm[i],
                )
            )
    rows.sort(key=lambda r: (r[0], r[1]))  # stable: a slider's miss stays before its break
    columns = list(zip(*rows, strict=True)) if rows else [[]] * 7
    names = ("time", "idx", "row", "what", "reason", "pattern", "stream_bpm")
    data = dict(zip(names, columns, strict=True))
    data["timestamp"] = [timestamp(t) for t in data["time"]]
    return Events.from_columns(data, n=len(rows))
