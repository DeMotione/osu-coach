""".osu beatmap parsing + "playable" view with mods, stacking and slider events.

Mechanics follow osu!stable as reproduced by osu!lazer / danser-go:
hit windows (truncated ints), preempt, circle radius (+0.041% allowance),
new/old stacking, slider velocity, ticks (lazer SliderEventGenerator incl. the
legacy 36 ms last-tick offset) and HardRock vertical flip.
"""
from __future__ import annotations

import bisect
import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path

from .curves import SliderPath

PLAYFIELD_W, PLAYFIELD_H = 512.0, 384.0
STACK_DISTANCE = 3.0
LEGACY_LAST_TICK_OFFSET = 36.0
MOD_EZ, MOD_HR, MOD_DT, MOD_HT, MOD_NC = 2, 16, 64, 256, 512


def difficulty_range(value: float, low: float, mid: float, high: float) -> float:
    """osu! DifficultyRange(difficulty, min(0), mid(5), max(10))."""
    if value > 5:
        return mid + (high - mid) * (value - 5) / 5
    if value < 5:
        return mid - (mid - low) * (5 - value) / 5
    return mid


@dataclass
class TimingPoint:
    time: float
    beat_length: float
    uninherited: bool


@dataclass
class SliderEvent:
    time: float
    kind: str  # 'tick' | 'repeat' | 'end'  ('end' = legacy last tick, judged 36 ms early)
    progress: float  # path progress 0..1 at that time


@dataclass
class HitObject:
    index: int
    kind: str  # 'circle' | 'slider' | 'spinner'
    time: float
    end_time: float
    x: float
    y: float
    new_combo: bool = False
    # slider only
    path: SliderPath | None = None
    spans: int = 1
    pixel_length: float = 0.0
    velocity: float = 0.0  # osu!px per ms
    span_duration: float = 0.0
    tick_distance: float = 0.0
    events: list[SliderEvent] = field(default_factory=list)

    @property
    def is_slider(self) -> bool:
        return self.kind == "slider"

    @property
    def is_spinner(self) -> bool:
        return self.kind == "spinner"

    def progress_at(self, t: float) -> float:
        """Path progress (0..1) of the slider ball at time t (handles repeats)."""
        if not self.is_slider or self.span_duration <= 0:
            return 0.0
        p = (t - self.time) / self.span_duration
        p = min(max(p, 0.0), float(self.spans))
        span = int(p)
        frac = p - span
        if span >= self.spans:
            span, frac = self.spans - 1, 1.0
        return 1.0 - frac if span % 2 == 1 else frac

    def raw_pos_at(self, t: float) -> tuple[float, float]:
        if not self.is_slider:
            return (self.x, self.y)
        return self.path.position_at(self.progress_at(t))

    def raw_end_pos(self) -> tuple[float, float]:
        if not self.is_slider:
            return (self.x, self.y)
        return self.path.position_at(1.0 if self.spans % 2 == 1 else 0.0)


@dataclass
class Beatmap:
    format_version: int
    title: str = ""
    artist: str = ""
    creator: str = ""
    version_name: str = ""
    beatmap_id: int = 0
    beatmapset_id: int = 0
    md5: str = ""
    mode: int = 0
    hp: float = 5.0
    cs: float = 5.0
    od: float = 5.0
    ar: float = 5.0
    slider_multiplier: float = 1.4
    tick_rate: float = 1.0
    stack_leniency: float = 0.7
    timing_points: list[TimingPoint] = field(default_factory=list)
    objects: list[HitObject] = field(default_factory=list)
    _red_times: list[float] = field(default_factory=list, repr=False)
    _red_beats: list[float] = field(default_factory=list, repr=False)

    @property
    def display_name(self) -> str:
        return f"{self.artist} - {self.title} [{self.version_name}]"

    def beat_length_at(self, t: float) -> float:
        if not self._red_times:
            return 500.0
        i = bisect.bisect_right(self._red_times, t) - 1
        return self._red_beats[max(i, 0)]

    def bpm_at(self, t: float) -> float:
        return 60000.0 / self.beat_length_at(t)

    def main_bpm(self) -> float:
        """BPM that covers the most playable time (like the website's BPM)."""
        if not self.objects or not self._red_times:
            return 120.0
        end = self.objects[-1].end_time
        dur: dict[float, float] = {}
        for i, (t, bl) in enumerate(zip(self._red_times, self._red_beats)):
            nxt = self._red_times[i + 1] if i + 1 < len(self._red_times) else end
            start = max(t, self.objects[0].time) if i == 0 else t
            d = max(0.0, min(nxt, end) - start)
            key = round(60000.0 / bl, 2)
            dur[key] = dur.get(key, 0.0) + d
        return max(dur.items(), key=lambda kv: kv[1])[0] if dur else 120.0

    def max_combo(self) -> int:
        combo = 0
        for o in self.objects:
            combo += 1
            if o.is_slider:
                combo += len(o.events)  # ticks + repeats + tail
        return combo

    @property
    def drain_seconds(self) -> float:
        if not self.objects:
            return 0.0
        return max(0.0, (self.objects[-1].end_time - self.objects[0].time) / 1000.0)


# --------------------------------------------------------------------------- parsing
def _kv(line: str) -> tuple[str, str]:
    k, _, v = line.partition(":")
    return k.strip(), v.strip()


def _num(v: str, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


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


# --------------------------------------------------------------------------- playable view
class PlayableBeatmap:
    """A beatmap with mods applied: adjusted settings, stacking, flipped positions.

    ``overrides``: lazer's Difficulty Adjust values ({"cs"/"ar"/"od"/"hp": value}), applied
    instead of the map's own settings. ``mirror``: lazer's Mirror mod, "horizontal",
    "vertical" or "both"."""

    def __init__(self, beatmap: Beatmap, mods: int = 0, rate: float | None = None,
                 overrides: dict | None = None, mirror: str | None = None):
        self.beatmap = beatmap
        self.mods = mods
        cs, ar, od, hp = beatmap.cs, beatmap.ar, beatmap.od, beatmap.hp
        if overrides:
            cs = overrides.get("cs", cs)
            ar = overrides.get("ar", ar)
            od = overrides.get("od", od)
            hp = overrides.get("hp", hp)
        if mods & MOD_HR:
            cs, ar, od, hp = min(cs * 1.3, 10), min(ar * 1.4, 10), min(od * 1.4, 10), min(hp * 1.4, 10)
        if mods & MOD_EZ:
            cs, ar, od, hp = cs / 2, ar / 2, od / 2, hp / 2
        self.cs, self.ar, self.od, self.hp = cs, ar, od, hp
        self.flip = bool(mods & MOD_HR) != (mirror in ("vertical", "both"))
        self.flip_x = mirror in ("horizontal", "both")
        if rate is None:
            rate = 1.5 if mods & (MOD_DT | MOD_NC) else 0.75 if mods & MOD_HT else 1.0
        self.rate = rate
        self.radius_raw = difficulty_range(cs, 54.4, 32, 9.6)
        self.radius = self.radius_raw * 1.00041  # stable hit-test allowance
        self.preempt = math.floor(difficulty_range(ar, 1800, 1200, 450))
        self.hit300 = int(difficulty_range(od, 80, 50, 20))
        self.hit100 = int(difficulty_range(od, 140, 100, 60))
        self.hit50 = int(difficulty_range(od, 200, 150, 100))
        self._stack: dict[int, int] = {}
        self._apply_stacking()

    # effective (rate-adjusted) values for display
    @property
    def effective_ar(self) -> float:
        p = self.preempt / self.rate
        return 5 + (1200 - p) / 150 if p < 1200 else 5 - (p - 1200) / 120

    @property
    def effective_od(self) -> float:
        return (79.5 - (self.hit300 - 0.5) / self.rate) / 6

    def stack(self, obj: HitObject) -> int:
        return self._stack.get(obj.index, 0)

    def _transform(self, obj: HitObject, p: tuple[float, float]) -> tuple[float, float]:
        x, y = p
        if self.flip:
            y = PLAYFIELD_H - y
        if self.flip_x:
            x = PLAYFIELD_W - x
        off = self.stack(obj) * self.radius / 10.0
        return (x - off, y - off)

    def pos(self, obj: HitObject) -> tuple[float, float]:
        return self._transform(obj, (obj.x, obj.y))

    def end_pos(self, obj: HitObject) -> tuple[float, float]:
        return self._transform(obj, obj.raw_end_pos())

    def pos_at(self, obj: HitObject, t: float) -> tuple[float, float]:
        return self._transform(obj, obj.raw_pos_at(t))

    def event_pos(self, obj: HitObject, ev: SliderEvent) -> tuple[float, float]:
        return self._transform(obj, obj.path.position_at(ev.progress))

    # ---- stacking (danser-go / lazer OsuBeatmapProcessor)
    def _apply_stacking(self):
        objs = self.beatmap.objects
        st = self._stack
        for o in objs:
            st[o.index] = 0
        threshold = math.floor(self.preempt * self.beatmap.stack_leniency)
        if self.beatmap.format_version >= 6:
            self._new_stacking(objs, threshold)
        else:
            self._old_stacking(objs, threshold)
        for o in objs:
            if o.is_spinner:
                st[o.index] = 0

    @staticmethod
    def _dist(a, b) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _new_stacking(self, objs, threshold):
        st = self._stack
        d = self._dist
        start = lambda o: (o.x, o.y)  # noqa: E731
        end = lambda o: o.raw_end_pos()  # noqa: E731
        n = len(objs)
        extended_end = n - 1
        for i in range(n - 1, -1, -1):
            base = i
            for k in range(base + 1, n):
                sb = objs[base]
                if sb.is_spinner:
                    break
                ok = objs[k]
                if ok.is_spinner:
                    continue
                if ok.time - sb.end_time > threshold:
                    break
                if d(start(sb), start(ok)) < STACK_DISTANCE or (sb.is_slider and d(end(sb), start(ok)) < STACK_DISTANCE):
                    base = k
                    st[ok.index] = 0
            if base > extended_end:
                extended_end = base
                if extended_end == n - 1:
                    break
        extended_start = 0
        for i in range(extended_end, 0, -1):
            n_i = i
            oi = objs[i]
            if st[oi.index] != 0 or oi.is_spinner:
                continue
            if oi.kind == "circle":
                n_i -= 1
                while n_i >= 0:
                    on = objs[n_i]
                    if on.is_spinner:
                        n_i -= 1
                        continue
                    if oi.time - on.end_time > threshold:
                        break
                    if n_i < extended_start:
                        st[on.index] = 0
                        extended_start = n_i
                    if on.is_slider and d(end(on), start(oi)) < STACK_DISTANCE:
                        offset = st[oi.index] - st[on.index] + 1
                        for j in range(n_i + 1, i + 1):
                            oj = objs[j]
                            if d(end(on), start(oj)) < STACK_DISTANCE:
                                st[oj.index] = st[oj.index] - offset
                        break
                    if d(start(on), start(oi)) < STACK_DISTANCE:
                        st[on.index] = st[oi.index] + 1
                        oi = on
                    n_i -= 1
            elif oi.is_slider:
                n_i -= 1
                while n_i >= 0:
                    on = objs[n_i]
                    if on.is_spinner:
                        n_i -= 1
                        continue
                    if oi.time - on.time > threshold:
                        break
                    if d(end(on), start(oi)) < STACK_DISTANCE:
                        st[on.index] = st[oi.index] + 1
                        oi = on
                    n_i -= 1

    def _old_stacking(self, objs, threshold):
        st = self._stack
        d = self._dist
        for i, oi in enumerate(objs):
            start_time = oi.end_time
            if st[oi.index] == 0 or oi.is_slider:
                slider_stack = 0
                for k in range(i + 1, len(objs)):
                    on = objs[k]
                    if on.time - threshold > start_time:
                        break
                    if d((on.x, on.y), (oi.x, oi.y)) < STACK_DISTANCE:
                        st[oi.index] += 1
                        start_time = on.end_time
                    elif d((on.x, on.y), oi.raw_end_pos()) < STACK_DISTANCE:
                        slider_stack += 1
                        st[on.index] -= slider_stack
                        start_time = on.end_time
