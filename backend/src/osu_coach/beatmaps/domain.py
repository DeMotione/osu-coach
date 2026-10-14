"""Beatmap model and the "playable" view with mods, stacking and slider events.

Mechanics follow osu!stable as reproduced by osu!lazer / danser-go:
hit windows (truncated ints), preempt, circle radius (+0.041% allowance),
new/old stacking, slider velocity, ticks (lazer SliderEventGenerator incl. the
legacy 36 ms last-tick offset) and HardRock vertical flip.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

from osu_coach.beatmaps.curves import SliderPath

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


# --------------------------------------------------------------------------- playable view
class PlayableBeatmap:
    """A beatmap with mods applied: adjusted settings, stacking, flipped positions.

    ``overrides``: lazer's Difficulty Adjust values ({"cs"/"ar"/"od"/"hp": value}), applied
    instead of the map's own settings. ``mirror``: lazer's Mirror mod, "horizontal",
    "vertical" or "both"."""

    def __init__(
        self,
        beatmap: Beatmap,
        mods: int = 0,
        rate: float | None = None,
        overrides: dict | None = None,
        mirror: str | None = None,
    ):
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
                if d(start(sb), start(ok)) < STACK_DISTANCE or (
                    sb.is_slider and d(end(sb), start(ok)) < STACK_DISTANCE
                ):
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
