""".osu beatmap file parsing (the model lives in osu_coach.beatmaps.domain)."""
from __future__ import annotations

import bisect
import hashlib
import math
from pathlib import Path

from osu_coach.beatmaps.domain import LEGACY_LAST_TICK_OFFSET, Beatmap, HitObject, SliderEvent, TimingPoint
from osu_coach.beatmaps.curves import SliderPath


# --------------------------------------------------------------------------- parsing
def _kv(line: str) -> tuple[str, str]:
    k, _, v = line.partition(":")
    return k.strip(), v.strip()


def _num(v: str, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def read_metadata(path) -> dict:
    """The [Metadata] section of an .osu file (Artist, Title, Version, Creator, BeatmapID, ...), read
    without parsing the rest of the map. {} if the file can't be read."""
    out: dict = {}
    section = ""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if s.startswith("[") and s.endswith("]"):
                    if section == "Metadata":
                        break
                    section = s[1:-1]
                elif section == "Metadata" and ":" in s:
                    k, v = _kv(s)
                    out[k] = v
    except (OSError, TypeError):
        return {}
    return out


def parse_beatmap_file(path) -> Beatmap:
    data = Path(path).read_bytes()
    return parse_beatmap_bytes(data)


def parse_beatmap_bytes(data: bytes) -> Beatmap:
    bm = parse_beatmap(data.decode("utf-8-sig", errors="replace"))
    bm.md5 = hashlib.md5(data).hexdigest()
    return bm


def parse_beatmap(text: str) -> Beatmap:
    lines = text.splitlines()
    fmt = 14
    if lines and "osu file format v" in lines[0]:
        try:
            fmt = int(lines[0].split("osu file format v", 1)[1].strip())
        except ValueError:
            pass
    bm = Beatmap(format_version=fmt)
    section = ""
    ar_set = False
    raw_timing: list[tuple[float, float, bool]] = []
    raw_objects: list[list[str]] = []
    for line in lines[1:]:
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1]
            continue
        if section == "General":
            k, v = _kv(s)
            if k == "StackLeniency":
                bm.stack_leniency = _num(v, 0.7)
            elif k == "Mode":
                bm.mode = int(_num(v, 0))
        elif section == "Metadata":
            k, v = _kv(s)
            if k == "Title":
                bm.title = v
            elif k == "Artist":
                bm.artist = v
            elif k == "Creator":
                bm.creator = v
            elif k == "Version":
                bm.version_name = v
            elif k == "BeatmapID":
                bm.beatmap_id = int(_num(v, 0))
            elif k == "BeatmapSetID":
                bm.beatmapset_id = int(_num(v, 0))
        elif section == "Difficulty":
            k, v = _kv(s)
            if k == "HPDrainRate":
                bm.hp = _num(v, 5)
            elif k == "CircleSize":
                bm.cs = _num(v, 5)
            elif k == "OverallDifficulty":
                bm.od = _num(v, 5)
            elif k == "ApproachRate":
                bm.ar = _num(v, 5)
                ar_set = True
            elif k == "SliderMultiplier":
                bm.slider_multiplier = min(max(_num(v, 1.4), 0.4), 3.6)
            elif k == "SliderTickRate":
                bm.tick_rate = min(max(_num(v, 1), 0.5), 8)
        elif section == "TimingPoints":
            parts = s.split(",")
            if len(parts) < 2:
                continue
            t = _num(parts[0], 0.0)
            bl = _num(parts[1], math.nan)
            unin = True
            if len(parts) >= 7:
                unin = parts[6].strip() == "1"
            elif bl < 0:
                unin = False
            raw_timing.append((t, bl, unin))
        elif section == "HitObjects":
            raw_objects.append(s.split(","))
    if not ar_set:
        bm.ar = bm.od
    bm.timing_points = [TimingPoint(t, bl, u) for t, bl, u in sorted(raw_timing, key=lambda r: r[0])]
    reds = [tp for tp in bm.timing_points if tp.uninherited and tp.beat_length > 0 and not math.isnan(tp.beat_length)]
    bm._red_times = [tp.time for tp in reds]
    bm._red_beats = [tp.beat_length for tp in reds]
    _sv_times, _sv_values = _build_sv_lookup(bm.timing_points)
    for parts in raw_objects:
        obj = _parse_object(parts, len(bm.objects), bm, _sv_times, _sv_values)
        if obj is not None:
            bm.objects.append(obj)
    bm.objects.sort(key=lambda o: o.time)
    for i, o in enumerate(bm.objects):
        o.index = i
    return bm


def _build_sv_lookup(tps: list[TimingPoint]):
    times: list[float] = []
    values: list[float] = []
    i = 0
    while i < len(tps):
        t = tps[i].time
        group = []
        while i < len(tps) and tps[i].time == t:
            group.append(tps[i])
            i += 1
        greens = [g for g in group if not g.uninherited]
        if greens:
            bl = greens[-1].beat_length
            sv = 1.0 if (math.isnan(bl) or bl >= 0) else 100.0 / min(max(-bl, 10.0), 1000.0)
        else:
            sv = 1.0
        times.append(t)
        values.append(sv)
    return times, values


def _sv_at(times, values, t: float) -> float:
    i = bisect.bisect_right(times, t) - 1
    return values[i] if i >= 0 else 1.0


def _parse_object(parts: list[str], idx: int, bm: Beatmap, sv_times, sv_values) -> HitObject | None:
    if len(parts) < 4:
        return None
    try:
        x, y, t = float(parts[0]), float(parts[1]), float(parts[2])
        typ = int(parts[3])
    except ValueError:
        return None
    nc = bool(typ & 4)
    if typ & 1:
        return HitObject(idx, "circle", t, t, x, y, nc)
    if typ & 8:
        end = _num(parts[5], t) if len(parts) > 5 else t
        return HitObject(idx, "spinner", t, max(end, t), 256.0, 192.0, nc)
    if typ & 2:
        if len(parts) < 8:
            return None
        return _parse_slider(parts, idx, x, y, t, nc, bm, sv_times, sv_values)
    return None  # mania hold notes etc.


def _parse_slider(parts, idx, x, y, t, nc, bm: Beatmap, sv_times, sv_values) -> HitObject | None:
    tokens = parts[5].split("|")
    curve_type = "B"
    cps: list[tuple[float, float]] = [(x, y)]
    point_types: dict[int, str] = {}
    pending_type: str | None = None
    first = True
    for tok in tokens:
        if ":" not in tok:
            letter = tok.strip().upper()[:1]
            if letter in "BCLP" and letter:
                if first:
                    curve_type = letter
                    first = False
                else:
                    pending_type = letter
            continue
        a, _, b = tok.partition(":")
        try:
            p = (float(a), float(b))
        except ValueError:
            continue
        if pending_type is not None:
            # lazer v128 style: type letter starts a new segment at the previous point
            point_types[len(cps) - 1] = pending_type
            pending_type = None
        if len(cps) == 1 and p == cps[0] and not point_types:
            continue  # skip first point equal to the head
        cps.append(p)
    try:
        spans = max(1, min(int(float(parts[6])), 9000))
        pixel_length = float(parts[7])
    except ValueError:
        return None
    if pixel_length <= 0 or math.isnan(pixel_length):
        pixel_length = None  # let the path decide
    path = SliderPath(curve_type, cps, pixel_length, point_types)
    length = path.length
    beat = bm.beat_length_at(t)
    sv = _sv_at(sv_times, sv_values, t)
    scoring_distance = 100.0 * bm.slider_multiplier * sv
    velocity = scoring_distance / beat if beat > 0 else 0.1
    if velocity <= 0 or math.isnan(velocity):
        velocity = 0.1
    span_duration = length / velocity if length > 0 else 0.0
    # stable floors the slider end time (danser: calculateFollowPointsStable)
    obj = HitObject(idx, "slider", t, math.floor(t + span_duration * spans), x, y, nc, path=path, spans=spans,
                    pixel_length=length, velocity=velocity, span_duration=span_duration)
    tick_distance = scoring_distance / bm.tick_rate
    if bm.format_version < 8:
        tick_distance /= sv
    obj.tick_distance = tick_distance
    obj.events = _slider_events(obj, tick_distance)
    return obj


def _slider_events(o: HitObject, tick_distance: float) -> list[SliderEvent]:
    """Ticks/repeats like lazer's SliderEventGenerator, with stable's integer
    timings (floored) and stable's last-tick rule:
    max(start + duration/2, end - 36) on the floored end time."""
    events: list[SliderEvent] = []
    length = min(100000.0, o.pixel_length)
    tick_distance = min(max(tick_distance, 0.0), length)
    min_from_end = o.velocity * 10
    for span in range(o.spans):
        span_start = o.time + span * o.span_duration
        reversed_span = span % 2 == 1
        ticks = []
        if tick_distance > 0:
            d = tick_distance
            while d <= length:
                if d >= length - min_from_end:
                    break
                path_prog = d / length
                time_prog = 1 - path_prog if reversed_span else path_prog
                ticks.append(SliderEvent(math.floor(span_start + time_prog * o.span_duration), "tick", path_prog))
                d += tick_distance
        if reversed_span:
            ticks.reverse()
        events.extend(ticks)
        if span < o.spans - 1:
            events.append(SliderEvent(math.floor(span_start + o.span_duration), "repeat",
                                      1.0 if span % 2 == 0 else 0.0))
    start = int(o.time)
    end = int(o.end_time)
    final_end = max(start + (end - start) // 2, end - int(LEGACY_LAST_TICK_OFFSET))
    final_span_start = o.time + (o.spans - 1) * o.span_duration
    prog = (final_end - final_span_start) / o.span_duration if o.span_duration > 0 else 1.0
    if o.spans % 2 == 0:
        prog = 1 - prog
    events.append(SliderEvent(final_end, "end", min(max(prog, 0.0), 1.0)))
    events.sort(key=lambda e: e.time)
    return events
