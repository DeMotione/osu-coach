"""Judgement simulation of a replay on a beatmap: osu!stable rules here, osu!lazer
rules in :mod:`judge_lazer` (``simulate`` picks the right one per replay).

Port of the osu!stable rules as reproduced by danser-go (app/rulesets/osu):
* clicks = new presses of the left (M1/K1) or right (M2/K2) button;
* notelock (CanBeHitStable), the 400 ms "hittable range", stack "ignore";
* integer hit windows ``|delta| < hit300/100/50``;
* sliders: head, ticks/repeats/legacy end (36 ms early), follow radius 2.4x
  while sliding, stable's key-swap acceptance quirk, final 300/100/50/miss
  from the fraction of parts hit;
* spinners: approximated from cursor rotation (only affects validation).

On top of the game result it records *why* things went wrong (aim / timing /
notelock / missing tap / slider break reason) and every key press.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from osu_coach.domain.beatmap import HitObject, PlayableBeatmap
from osu_coach.domain.replay import KEY_K1, KEY_K2, KEY_M1, KEY_M2, MOD_BITS, Replay

CLICK, SHAKE, IGNORED = 0, 1, 2
HITTABLE_RANGE = 400
TOLERANCE_2B = 3
LEFT, RIGHT, BOTH = 1, 2, 3


@dataclass
class ClickSeen:
    time: float
    dist: float          # cursor distance to object centre / radius
    action: int          # CLICK / SHAKE / IGNORED
    in_range: bool
    x: float = 0.0       # cursor position at the click
    y: float = 0.0


@dataclass
class ObjResult:
    index: int
    kind: str
    time: float
    end_time: float
    x: float
    y: float
    result: int = -1                 # final 300/100/50/0
    head_hit: bool = False           # circle hit / slider head hit (not a miss)
    head_result: int = -1            # timing judgement of circle / slider head
    hit_time: float | None = None
    hit_error: float | None = None   # ms, map time (positive = late)
    click_x: float | None = None
    click_y: float | None = None
    key: str | None = None
    press_id: int | None = None
    miss_reason: str | None = None
    miss_dist: float | None = None   # closest click distance (radii) when relevant
    miss_x: float | None = None      # cursor position of that closest click
    miss_y: float | None = None
    miss_time: float | None = None
    forced_miss: bool = False        # lazer: missed because a later object was hit first
    clicks: list[ClickSeen] = field(default_factory=list, repr=False)
    # sliders
    n_events: int = 0
    n_events_hit: int = 0
    end_hit: bool | None = None
    broke: bool = False
    break_reason: str | None = None
    break_time: float | None = None
    # spinners
    spins: float | None = None
    spins_required: float | None = None


@dataclass
class Press:
    id: int
    key: str
    time: float
    x: float
    y: float
    release: float | None = None
    target: int | None = None        # object index judged by this press
    outcome: str = "none"            # hit / early_miss / notelock / none

    @property
    def duration(self) -> float | None:
        return None if self.release is None else self.release - self.time


@dataclass
class SimResult:
    objects: list[ObjResult]
    presses: list[Press]
    counts: dict
    max_combo: int
    radius: float
    hit_windows: tuple[int, int, int]
    rules: str = "stable"
    lazer_stats: dict | None = None  # lazer rules: the same statistics lazer stores in its replays


class _ObjState:
    __slots__ = ("obj", "res", "is_hit", "is_start_hit", "start_result", "down_button", "sliding",
                 "slide_start", "scored", "missed", "points", "spin_angle", "last_angle", "last_t")

    def __init__(self, obj: HitObject, res: ObjResult):
        self.obj = obj
        self.res = res
        self.is_hit = False
        self.is_start_hit = False
        self.start_result = 0
        self.down_button = 0
        self.sliding = False
        self.slide_start = 0
        self.scored = 0
        self.missed = 0
        self.points = obj.events if obj.is_slider else []
        self.spin_angle = 0.0
        self.last_angle = None
        self.last_t = None

    def finished(self) -> bool:
        if self.obj.is_slider:
            return self.is_hit and self.is_start_hit
        return self.is_hit


def _result_for_delta(pb: PlayableBeatmap, delta: float) -> int:
    d = int(delta)
    if d < pb.hit300:
        return 300
    if d < pb.hit100:
        return 100
    if d < pb.hit50:
        return 50
    return 0


def simulate(pb: PlayableBeatmap, replay: Replay, rules: str | None = None) -> SimResult:
    """rules: 'stable' / 'lazer' / None (auto: lazer replays use lazer's rules, see judge_lazer)."""
    if rules == "lazer" or (rules is None and replay.is_lazer):
        from osu_coach.domain.judge_lazer import lazer_options, simulate_lazer
        return simulate_lazer(pb, replay, **lazer_options(replay))
    objs = pb.beatmap.objects
    radius = pb.radius
    results = []
    for o in objs:
        x, y = pb.pos(o)
        r = ObjResult(o.index, o.kind, o.time, o.end_time, x, y)
        if o.is_slider:
            r.n_events = len(o.events)
        results.append(r)
    states = [_ObjState(o, results[i]) for i, o in enumerate(objs)]
    pos_cache = [pb.pos(o) for o in objs]

    relax = bool(replay.mods & MOD_BITS["RX"])
    autopilot = bool(replay.mods & MOD_BITS["AP"])
    spun_out = bool(replay.mods & (MOD_BITS["SO"] | MOD_BITS["AT"]))

    combo = 0
    max_combo = 0

    def add_combo(kind: str):
        nonlocal combo, max_combo
        if kind == "inc":
            combo += 1
            max_combo = max(max_combo, combo)
        elif kind == "reset":
            combo = 0

    presses: list[Press] = []
    open_press: dict[str, Press] = {}

    queue_i = 0
    processed: list[_ObjState] = []

    prev_left = prev_right = False
    game_down = False
    mouse_down_button = 0
    last_button = last_button2 = 0

    ts, xs, ys, ks = replay.t, replay.x, replay.y, replay.keys
    n_frames = len(ts)
    old_handling = replay.version < 20190506

    for fi in range(n_frames):
        t = int(ts[fi])
        cx, cy = float(xs[fi]), float(ys[fi])
        k = int(ks[fi])

        # -- objects become active at fade-in (start - preempt)
        while queue_i < len(states) and states[queue_i].obj.time - pb.preempt <= t:
            processed.append(states[queue_i])
            queue_i += 1

        # -- physical key presses (for tapping analysis)
        phys = {"K1": bool(k & KEY_K1), "K2": bool(k & KEY_K2),
                "M1": bool(k & KEY_M1) and not (k & KEY_K1), "M2": bool(k & KEY_M2) and not (k & KEY_K2)}
        new_left_press = new_right_press = None
        for name, down in phys.items():
            if down and name not in open_press:
                p = Press(len(presses), name, t, cx, cy)
                presses.append(p)
                open_press[name] = p
                if name in ("K1", "M1") and new_left_press is None:
                    new_left_press = p
                elif name in ("K2", "M2") and new_right_press is None:
                    new_right_press = p
            elif not down and name in open_press:
                open_press.pop(name).release = t

        left = bool(k & KEY_M1)
        right = bool(k & KEY_M2)
        if relax:
            left = right = False
        left_cond = left and not prev_left
        right_cond = right and not prev_right
        left_e, right_e = left_cond, right_cond
        if left != prev_left or right != prev_right:
            game_down = left or right
            last_button2 = last_button
            last_button = mouse_down_button
            mouse_down_button = (LEFT if left else 0) | (RIGHT if right else 0)

        # -- clicks (UpdateClickFor)
        if left_cond or right_cond:
            for si, st in enumerate(processed):
                o = st.obj
                if o.is_spinner:
                    continue
                if o.is_slider:
                    if st.is_start_hit or st.is_hit:
                        continue
                elif st.is_hit:
                    continue
                if not (left_e or right_e):
                    continue
                px, py = pos_cache[o.index]
                dist = math.hypot(cx - px, cy - py)
                in_range = dist <= radius
                action = _can_be_hit(t, st, si, processed, pb)
                if abs(t - o.time) <= pb.hit50 + 200:
                    st.res.clicks.append(ClickSeen(t, dist / radius, action, in_range, cx, cy))
                if not in_range and action == CLICK and abs(t - o.time) < pb.hit50:
                    # tapped for this note but outside the circle: an aim miss, not an extra tap
                    for press in (new_left_press if left_e else None, new_right_press if right_e else None):
                        if press is not None and press.outcome == "none":
                            press.outcome = "off_target"
                if in_range:
                    if action == CLICK:
                        if left_e:
                            left_e = False
                            press = new_left_press
                        else:
                            right_e = False
                            press = new_right_press
                        result = _result_for_delta(pb, abs(t - o.time))
                        r = st.res
                        r.hit_time, r.hit_error = t, t - o.time
                        r.click_x, r.click_y = cx, cy
                        r.head_result = result
                        r.head_hit = result != 0
                        if press is not None:
                            r.key, r.press_id = press.key, press.id
                            press.target = o.index
                            press.outcome = "hit" if result else "early_miss"
                        if result == 0:
                            r.miss_reason = "early"
                        if o.is_slider:
                            st.down_button = LEFT if left_cond else RIGHT if right_cond else mouse_down_button
                            st.start_result = result
                            st.is_start_hit = True
                            add_combo("inc" if result else "reset")
                        else:
                            st.is_hit = True
                            r.result = result
                            add_combo("inc" if result else "reset")
                    else:
                        label = "too_early" if abs(t - o.time) >= HITTABLE_RANGE else "notelock"
                        for press in (new_left_press if left_e else None, new_right_press if right_e else None):
                            if press is not None and press.outcome == "none":
                                press.outcome = label
                        left_e = right_e = False

        # -- slider tracking (UpdateNormalFor): only the first unfinished slider
        was_slider = False
        for st in processed:
            o = st.obj
            if o.is_spinner:
                if not st.is_hit and o.time <= t <= o.end_time:
                    _spin(st, cx, cy, t, left or right or relax, spun_out)
                continue
            if not o.is_slider:
                continue
            if was_slider:
                continue
            if not st.is_hit:
                was_slider = True
            if t >= o.time and not st.is_hit:
                swap = game_down and not (last_button == BOTH and last_button2 == mouse_down_button)
                acceptable = False
                if game_down:
                    if st.down_button == 0 or (mouse_down_button != BOTH and swap):
                        st.down_button = LEFT if left_cond else RIGHT if right_cond else mouse_down_button
                        acceptable = True
                    elif mouse_down_button & st.down_button:
                        acceptable = True
                else:
                    st.down_button = 0
                acceptable = acceptable or swap or relax
                bx, by = pb.pos_at(o, t)
                need = radius * (2.4 if st.sliding else 1.0)
                d2 = (cx - bx) ** 2 + (cy - by) ** 2
                allowable = acceptable and d2 < need * need
                if allowable and not st.sliding:
                    st.sliding = True
                    st.slide_start = t
                # processTicksStable: one pending point per frame
                passed = 0
                for ev in st.points:
                    if ev.time > t:
                        break
                    passed += 1
                if st.scored + st.missed < passed:
                    ev = st.points[st.scored + st.missed]
                    last = st.scored + st.missed == len(st.points) - 1
                    if allowable and st.slide_start <= ev.time:
                        st.scored += 1
                        st.res.n_events_hit += 1
                        add_combo("inc")
                        if last:
                            st.res.end_hit = True
                    else:
                        st.missed += 1
                        if last:
                            st.res.end_hit = False
                        else:
                            add_combo("reset")
                        if st.start_result != 0 and not st.res.broke and not last:
                            st.res.broke = True
                            st.res.break_time = ev.time
                            if not (left or right):
                                st.res.break_reason = "released"
                            elif not acceptable:
                                st.res.break_reason = "key_swap"
                            else:
                                st.res.break_reason = "follow"
                if not allowable and st.sliding and st.scored + st.missed < len(st.points):
                    st.sliding = False

        # -- UpdatePostFor: auto misses, slider/spinner completion
        def post(tt: int):
            for st in processed:
                o = st.obj
                r = st.res
                if o.kind == "circle":
                    if not st.is_hit and tt > o.time + pb.hit50:
                        st.is_hit = True
                        r.result = 0
                        r.head_result = 0
                        add_combo("reset")
                elif o.is_slider:
                    if not st.is_start_hit and tt > o.time + pb.hit50:
                        st.is_start_hit = True
                        st.start_result = 0
                        r.head_result = 0
                        st.down_button = LEFT if left_cond else RIGHT if right_cond else mouse_down_button
                        add_combo("reset")
                    if tt >= o.end_time and not st.is_hit:
                        scored = st.scored + (1 if st.start_result != 0 else 0)
                        rate = scored / (len(st.points) + 1)
                        res = 300 if rate == 1.0 else 100 if rate >= 0.5 else 50 if rate > 0 else 0
                        r.result = res
                        r.head_hit = st.start_result != 0
                        if res == 0:
                            add_combo("reset")
                        st.is_hit = True
                else:  # spinner
                    if not st.is_hit and tt >= o.end_time:
                        _finish_spinner(st, pb, spun_out or autopilot)
                        add_combo("inc" if r.result else "reset")

        post(t)
        # Replays older than 20190506 judged object ends every ms between
        # input frames (danser's "old handling"), not only on frames.
        if old_handling and fi + 1 < n_frames:
            nxt = int(ts[fi + 1]) - 1
            if nxt > t:
                post(nxt)

        processed = [st for st in processed if not st.finished()]
        prev_left, prev_right = left, right

    # replay ended before these objects were judged (quit / failed play): unplayed
    for st in states:
        r = st.res
        if r.result == -1:
            r.head_hit = False
            r.miss_reason = None
        elif r.head_result == -1 and not st.obj.is_spinner:
            r.head_result = 0
    for p in open_press.values():
        p.release = None

    for st in states:
        if st.res.result != -1:
            classify_miss_reason(st, pb, replay)

    counts = {300: 0, 100: 0, 50: 0, 0: 0}
    for r in results:
        if r.result in counts:
            counts[r.result] += 1
    return SimResult(results, presses, counts, max_combo, radius, (pb.hit300, pb.hit100, pb.hit50), "stable")


def _can_be_hit(t: int, st: _ObjState, si: int, processed: list[_ObjState], pb: PlayableBeatmap) -> int:
    o = st.obj
    if o.kind == "circle" and si > 0:
        prev = processed[si - 1]
        if pb.stack(prev.obj) > 0 and not prev.is_hit:
            return IGNORED
    for g in processed:
        if g is st:
            break
        if not g.is_hit and g.obj.end_time + TOLERANCE_2B < o.time:
            return SHAKE
    if abs(t - o.time) >= HITTABLE_RANGE:
        return SHAKE
    return CLICK


def _spin(st: _ObjState, cx: float, cy: float, t: int, down: bool, auto: bool):
    ang = math.atan2(cy - 192.0, cx - 256.0)
    if st.last_angle is not None and down and st.last_t is not None:
        d = ang - st.last_angle
        while d > math.pi:
            d -= 2 * math.pi
        while d < -math.pi:
            d += 2 * math.pi
        dt = max(1, t - st.last_t)
        st.spin_angle += min(abs(d), 0.05 * dt)  # ~477 rpm cap
    st.last_angle = ang
    st.last_t = t


def _finish_spinner(st: _ObjState, pb: PlayableBeatmap, auto: bool):
    o, r = st.obj, st.res
    length_s = max(0.0, (o.end_time - o.time) / 1000.0)
    od = pb.od
    sps = 1.5 + 0.2 * od if od < 5 else 1.25 + 0.25 * od
    required = math.floor((length_s * sps + 0.5) * 2) / 2
    spins = st.spin_angle / (2 * math.pi)
    r.spins, r.spins_required = spins, required
    if auto or required <= 0 or spins >= required:
        r.result = 300
    elif spins >= required - 1:
        r.result = 100
    elif spins >= 0.25 * required:
        r.result = 50
    else:
        r.result = 0
    r.head_hit = r.result != 0
    st.is_hit = True


def _cursor_at(replay: Replay, t: float) -> tuple[float, float]:
    i = int(np.searchsorted(replay.t, t))
    i = min(max(i, 0), len(replay.t) - 1)
    return float(replay.x[i]), float(replay.y[i])


def classify_miss_reason(st: _ObjState, pb: PlayableBeatmap, replay: Replay):
    o, r = st.obj, st.res
    if o.is_spinner or r.head_hit or r.miss_reason == "early":
        return
    lo, hi = o.time - pb.hit50, o.time + pb.hit50
    in_window = [c for c in r.clicks if lo <= c.time <= hi]
    if any(c.in_range and c.action != CLICK for c in in_window):
        r.miss_reason = "notelock"
        return
    aimed = [c for c in in_window if not c.in_range and c.action == CLICK]
    if aimed:
        best = min(aimed, key=lambda c: c.dist)
        r.miss_reason = "aim"
        r.miss_dist = best.dist
        r.miss_x, r.miss_y, r.miss_time = best.x, best.y, best.time
        return
    late = [c for c in r.clicks if hi < c.time <= hi + 200 and c.dist <= 1.5]
    if late:
        best = min(late, key=lambda c: c.dist)
        r.miss_reason = "late"
        r.miss_dist = best.dist
        r.miss_x, r.miss_y, r.miss_time = best.x, best.y, best.time
        return
    # no click reached this object inside its window
    px, py = r.x, r.y
    cx, cy = _cursor_at(replay, o.time)
    d = math.hypot(cx - px, cy - py) / pb.radius
    r.miss_dist = d
    r.miss_reason = "no_tap" if d <= 2.5 else "lost"
