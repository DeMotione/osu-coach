"""osu!lazer judgement simulation (osu! ruleset, current lazer rules).

Ported from osu!lazer (ppy/osu, 2025-2026 sources):

* hit windows ``floor(DifficultyRange(OD)) - 0.5`` ms, judged ``|offset| <= window``
  (OsuHitWindows since 2025-06-25; replays from older clients use the unfloored windows);
  a 400 ms miss window, presses earlier than that only shake the note;
* hit test: cursor inside the circle (stable's 1.00041 radius allowance included);
* ``StartTimeOrderedHitPolicy``: a circle or slider head can't be hit before the previous
  one's start time unless that one is judged, and hitting a note force-misses every earlier
  unjudged circle/head.  The Classic mod's note lock uses ``LegacyHitPolicy`` instead;
* sliders (``SliderInputManager``): the head is judged like a circle (or as a large tick with
  the Classic mod's "no slider head accuracy", the slider then scored by the share of parts
  hit).  Ticks and repeats are judged when reached, the tail any time from 36 ms before the
  end while tracking.  Tracking needs a held key (only the key that hit the head until the
  other key has been released) and the cursor inside the follow area (2.4x radius while
  tracking, 1x to start).  A late head hit judges the parts already passed at once
  (``PostProcessHeadJudgement``).  Missed ticks/repeats break combo, a missed tail doesn't;
* spinners: angle deltas while a key is held (x playback rate), lazer's spin history (spinning
  back and forth doesn't count), Great/Ok/Meh at 100/90/75 % of the required spins.

A replay only stores input at ~60 Hz plus every key change, with whole-millisecond times.
Between frames the cursor is interpolated linearly (as lazer's replay playback does), and
everything that falls due between two frames (ticks, the tail window, late misses, spinner
ends) is judged at its own time.
"""
from __future__ import annotations

import math
import re

import numpy as np

from osu_coach.domain.beatmap import HitObject, PlayableBeatmap
from osu_coach.domain.judge import CLICK, HITTABLE_RANGE, IGNORED, SHAKE, ClickSeen, ObjResult, Press, SimResult, classify_miss_reason
from osu_coach.domain.replay import KEY_K1, KEY_K2, KEY_M1, KEY_M2, MOD_BITS, Replay

LEFT, RIGHT = 1, 2
FOLLOW_AREA = 2.4
TAIL_LENIENCY = -36.0
MISS_WINDOW = 400.0
GREAT, OK, MEH, MISS = 300, 100, 50, 0
# lazer client from which hit windows are floored (OsuHitWindows, 2025-06-25)
FLOORED_WINDOWS_SINCE = (2025, 625)
# extra slider-tracking updates between replay frames (ms); see simulate_lazer
TRACKING_STEP = 4.0


def lazer_mod_settings(replay: Replay) -> dict[str, dict]:
    """{acronym: settings} of a lazer replay's mods ({} for stable replays)."""
    out = {}
    for m in (replay.lazer or {}).get("mods", []) or []:
        ac = str(m.get("acronym", "")).upper()
        if ac:
            out[ac] = m.get("settings") or {}
    return out


def client_version(replay: Replay) -> tuple[int, int] | None:
    v = str((replay.lazer or {}).get("client_version", ""))
    m = re.match(r"(\d{4})\.(\d{1,4})", v)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _lazer_range(difficulty: float, low: float, mid: float, high: float) -> float:
    """IBeatmapDifficultyInfo.DifficultyRange exactly as lazer computes it: the (float) setting
    widened to double, and ``(d - 5) / 5`` evaluated first (the order matters for the floors)."""
    d = float(np.float32(difficulty))
    if d > 5:
        return mid + (high - mid) * ((d - 5) / 5)
    if d < 5:
        return mid + (mid - low) * ((d - 5) / 5)
    return mid


def lazer_hit_windows(od: float, floored: bool = True) -> tuple[float, float, float]:
    """Great / Ok / Meh windows in ms (a hit counts if ``|offset| <= window``)."""
    w = (_lazer_range(od, 80, 50, 20), _lazer_range(od, 140, 100, 60), _lazer_range(od, 200, 150, 100))
    if floored:
        return tuple(math.floor(x) - 0.5 for x in w)  # type: ignore[return-value]
    return w


def lazer_options(replay: Replay) -> dict:
    """Judgement options implied by a lazer replay's mods, client version and stored results."""
    mods = lazer_mod_settings(replay)
    cl = mods.get("CL")
    ver = client_version(replay)
    lz = replay.lazer or {}
    st, mx = lz.get("statistics") or {}, lz.get("maximum_statistics") or {}
    judged = sum(int(st.get(k, 0) or 0) for k in ("great", "ok", "meh", "miss"))
    total = sum(int(mx.get(k, 0) or 0) for k in ("great", "ok", "meh", "miss"))
    return {
        "classic_slider": cl is not None and bool(cl.get("no_slider_head_accuracy", True)),
        "classic_notelock": cl is not None and bool(cl.get("classic_note_lock", True)),
        "floored_windows": ver is None or ver >= FLOORED_WINDOWS_SINCE if replay.lazer else False,
        "spun_out": "SO" in mods or bool(replay.mods & MOD_BITS["SO"]),
        # a failed play stops being judged at the fail, while the replay runs on through the fail animation
        "fail_after": judged if 0 < judged < total else None,
    }


# ---------------------------------------------------------------- per-object state
class _Nested:
    __slots__ = ("kind", "time", "x", "y", "judged", "hit")

    def __init__(self, kind: str, time: float, x: float, y: float):
        self.kind, self.time, self.x, self.y = kind, time, x, y
        self.judged = False
        self.hit = False


class _Obj:
    __slots__ = ("obj", "res", "kind", "time", "end", "x", "y", "judged", "hit_action", "prev_block", "nested",
                 "last_tick", "tail", "tracking", "accept_any_after", "last_pressed", "all_judged", "slider_judged",
                 "spin_total", "spin_at_completion", "spin_cur_max", "spin_completed", "last_angle", "lifetime_start")

    def __init__(self, obj: HitObject, res: ObjResult, x: float, y: float, preempt: float):
        self.obj, self.res, self.kind = obj, res, obj.kind
        self.time = obj.time
        self.x, self.y = x, y
        self.lifetime_start = obj.time - preempt
        self.judged = False              # circle / slider head / spinner judged
        self.hit_action: int | None = None
        self.prev_block: _Obj | None = None
        self.nested: list[_Nested] = []
        self.last_tick: _Nested | None = None
        self.tail: _Nested | None = None
        self.tracking = False
        self.accept_any_after: float | None = None
        self.last_pressed: frozenset = frozenset()
        self.all_judged = False
        self.slider_judged = False
        self.end = obj.end_time
        self.spin_total = 0.0
        self.spin_at_completion = 0.0
        self.spin_cur_max = 0.0
        self.spin_completed = 0
        self.last_angle: float | None = None


def lazer_nested_events(o: HitObject) -> list[tuple[str, float]]:
    """Ticks, repeats and the tail of a slider as lazer generates them
    (SliderEventGenerator): unrounded times, the tail at the real end."""
    length = min(100000.0, o.pixel_length)
    td = min(max(getattr(o, "tick_distance", 0.0) or 0.0, 0.0), length)
    min_from_end = o.velocity * 10
    out: list[tuple[str, float]] = []
    for span in range(o.spans):
        span_start = o.time + span * o.span_duration
        rev = span % 2 == 1
        ticks = []
        if td > 0 and math.isfinite(td):
            d = td
            while d <= length:
                if d >= length - min_from_end:
                    break
                prog = d / length
                ticks.append(("tick", span_start + (1 - prog if rev else prog) * o.span_duration))
                d += td
            if rev:
                ticks.reverse()
        out += ticks
        if span < o.spans - 1:
            out.append(("repeat", span_start + o.span_duration))
    out.append(("tail", o.time + o.spans * o.span_duration))
    out.sort(key=lambda e: e[1])
    return out


# ---------------------------------------------------------------- simulation
def simulate_lazer(pb: PlayableBeatmap, replay: Replay, *, classic_slider: bool = False,
                   classic_notelock: bool = False, floored_windows: bool = True,
                   spun_out: bool = False, fail_after: int | None = None, trace: list | None = None,
                   tracking_step: float | None = TRACKING_STEP) -> SimResult:
    """``fail_after``: stop judging after this many circle/head/slider/spinner judgements
    (a failed play).  ``trace``: if given, collects (object index, part, part time, judged at,
    hit, judged on a real frame) for every slider part, for debugging.  ``tracking_step``:
    ms between the extra slider-tracking updates inserted between replay frames (None: off)."""
    objs = pb.beatmap.objects
    radius = pb.radius
    r2 = radius * radius
    follow2 = (radius * FOLLOW_AREA) ** 2
    od = pb.od
    w_great, w_ok, w_meh = lazer_hit_windows(od, floored_windows)
    rate = replay.rate
    min_rps = _lazer_range(od, 90, 150, 225) / 60
    max_rps = _lazer_range(od, 250, 380, 430) / 60

    results: list[ObjResult] = []
    states: list[_Obj] = []
    hittable: list[_Obj] = []          # circles and sliders (heads), in start-time order
    for o in objs:
        x, y = pb.pos(o)
        r = ObjResult(o.index, o.kind, o.time, o.end_time, x, y)
        s = _Obj(o, r, x, y, pb.preempt)
        if o.is_slider:
            s.end = o.time + o.spans * o.span_duration
            for kind, t in lazer_nested_events(o):
                nx, ny = pb.pos_at(o, t)
                nd = _Nested(kind, t, nx, ny)
                s.nested.append(nd)
                if kind == "tail":
                    s.tail = nd
                else:
                    s.last_tick = nd
            r.n_events = len(s.nested)
        if not o.is_spinner:
            # hit policy: the latest circle / slider head with a strictly earlier start time
            j = len(hittable) - 1
            while j >= 0 and hittable[j].time >= s.time:
                j -= 1
            s.prev_block = hittable[j] if j >= 0 else None
            hittable.append(s)
        results.append(r)
        states.append(s)
    first_open = [0]                   # hittable[:first_open] are all judged

    combo = 0
    max_combo = 0
    stats = {"great": 0, "ok": 0, "meh": 0, "miss": 0, "large_tick_hit": 0, "large_tick_miss": 0,
             "slider_tail_hit": 0, "small_tick_hit": 0, "small_tick_miss": 0, "small_bonus": 0, "large_bonus": 0,
             "ignore_hit": 0, "ignore_miss": 0}
    name = {GREAT: "great", OK: "ok", MEH: "meh", MISS: "miss"}
    ctx = {"judged": 0, "stopped": False, "on_frame": True}

    def count_main(result: int):
        stats[name[result]] += 1
        ctx["judged"] += 1
        if fail_after is not None and ctx["judged"] >= fail_after:
            ctx["stopped"] = True

    def add_combo(hit: bool):
        nonlocal combo, max_combo
        if hit:
            combo += 1
            max_combo = max(max_combo, combo)
        else:
            combo = 0

    def result_for(offset: float) -> int | None:
        a = abs(offset)
        if a <= w_great:
            return GREAT
        if a <= w_ok:
            return OK
        if a <= w_meh:
            return MEH
        if a <= MISS_WINDOW:
            return MISS
        return None

    # -------------------------------------------------------- hit policy
    def alive(s: _Obj, t: float) -> bool:
        return t >= s.lifetime_start

    def can_receive(s: _Obj) -> bool:
        """HitReceptor.CanBeHit: not judged (classic note lock: slider fully judged)."""
        if s.obj.is_slider and classic_notelock:
            return not s.all_judged
        return not s.judged

    def check_hittable(s: _Obj, t: float, result: int | None) -> int:
        if classic_notelock:
            return _legacy_policy(s, t, result)
        p = s.prev_block
        if p is not None and not p.judged and t < p.time:
            return SHAKE
        if result is None:
            return SHAKE
        return CLICK

    def _legacy_policy(s: _Obj, t: float, result: int | None) -> int:
        # LegacyHitPolicy (osu!stable note lock); heads aren't top-level, so skip the stack check
        idx = s.obj.index
        if s.kind == "circle" and idx > 0:
            prev = states[idx - 1]
            if alive(prev, t) and pb.stack(prev.obj) > 0 and not _all_judged(prev):
                return IGNORED
        if result is None:
            return SHAKE
        for g in states:
            if g.time > t + pb.preempt:
                break
            if not alive(g, t) or _all_judged(g):
                continue
            if g is s:
                break
            if _end_time(g) + 3 < s.time:
                return SHAKE
        return CLICK if abs(s.time - t) < HITTABLE_RANGE else SHAKE

    def _all_judged(g: _Obj) -> bool:
        return g.all_judged if g.obj.is_slider else g.judged

    def _end_time(g: _Obj) -> float:
        return g.end if g.obj.is_slider else g.obj.end_time

    def handle_hit(s: _Obj):
        """StartTimeOrderedHitPolicy.HandleHit: miss every earlier unjudged circle/head."""
        if classic_notelock:
            return
        i = first_open[0]
        while i < len(hittable) and hittable[i].judged:
            i += 1
        first_open[0] = i
        for g in hittable[i:]:
            if g.time >= s.time:
                break
            if not g.judged:
                judge_head(g, MISS, forced=True)

    # -------------------------------------------------------- judgements
    def judge_head(s: _Obj, result: int, t: float | None = None, pos=None, press: Press | None = None,
                   forced: bool = False):
        if ctx["stopped"]:
            return
        r = s.res
        s.judged = True
        if not s.obj.is_slider:
            s.all_judged = True
        r.head_result = result
        r.head_hit = result != MISS
        if forced:
            r.forced_miss = True
        if t is not None:
            r.hit_time, r.hit_error = t, t - s.time
            r.click_x, r.click_y = pos
            if press is not None:
                r.key, r.press_id = press.key, press.id
                press.target = s.obj.index
                press.outcome = "hit" if result != MISS else "early_miss"
            if result == MISS:
                r.miss_reason = "early"
        # the playfield's hit policy sees a new result before the score processor does: the
        # earlier notes this one force-misses break the combo *before* this result counts
        handle_hit(s)
        if ctx["stopped"]:
            return
        if s.obj.is_slider and classic_slider:
            stats["large_tick_hit" if result != MISS else "large_tick_miss"] += 1
        else:
            count_main(result)
            r.result = result
        add_combo(result != MISS)

    def judge_nested(s: _Obj, nd: _Nested, hit: bool, t: float, actions: frozenset, pos):
        if ctx["stopped"]:
            return
        nd.judged = True
        nd.hit = hit
        if trace is not None:
            trace.append((s.obj.index, nd.kind, nd.time, t, hit, ctx["on_frame"]))
        r = s.res
        if hit:
            r.n_events_hit += 1
        if nd.kind == "tail":
            r.end_hit = hit
            if classic_slider:
                stats["small_tick_hit" if hit else "small_tick_miss"] += 1
            elif hit:
                stats["slider_tail_hit"] += 1
                add_combo(True)
            else:
                stats["ignore_miss"] += 1
        else:
            stats["large_tick_hit" if hit else "large_tick_miss"] += 1
            add_combo(hit)
            if not hit and r.head_hit and not r.broke:
                r.broke = True
                r.break_time = nd.time
                if not actions:
                    r.break_reason = "released"
                elif not any(_valid_action(s, a, t) for a in actions):
                    r.break_reason = "key_swap"
                else:
                    r.break_reason = "follow"

    def judge_slider(s: _Obj):
        if ctx["stopped"]:
            return
        s.slider_judged = True
        s.all_judged = True
        r = s.res
        if classic_slider:
            parts = 1 + len(s.nested)
            got = (1 if r.head_hit else 0) + sum(1 for nd in s.nested if nd.hit)
            res = GREAT if got == parts else MISS if got == 0 else OK if got / parts >= 0.5 else MEH
            r.result = res
            count_main(res)
            add_combo(res != MISS)
        else:
            # the slider's own result only drives visuals: hit if any part was hit (no score/combo)
            any_hit = r.head_hit or any(nd.hit for nd in s.nested)
            stats["ignore_hit" if any_hit else "ignore_miss"] += 1
            if r.result == -1:
                r.result = r.head_result

    # -------------------------------------------------------- sliders
    def follow_pos(s: _Obj, t: float):
        o = s.obj
        dur = s.end - o.time
        p = min(max((t - o.time) / dur, 0.0), 1.0) if dur > 0 else 1.0
        return pb.pos_at(o, o.time + p * dur)

    def in_follow(s: _Obj, t: float, pos, expanded: bool) -> bool:
        fx, fy = follow_pos(s, t)
        d2 = (pos[0] - fx) ** 2 + (pos[1] - fy) ** 2
        return d2 <= (follow2 if expanded else r2)

    def _valid_action(s: _Obj, a: int, t: float) -> bool:
        ha = s.hit_action
        if ha is not None and (s.accept_any_after is None or t <= s.accept_any_after):
            return a == ha
        return a in (LEFT, RIGHT)

    def update_tracking(s: _Obj, t: float, actions: frozenset, valid_pos: bool):
        ha = s.hit_action
        if ha is None:
            s.accept_any_after = None
        if ha is not None and s.accept_any_after is None:
            other = LEFT if ha == RIGHT else RIGHT
            if other not in s.last_pressed:
                s.accept_any_after = t
        s.last_pressed = actions
        valid = any(_valid_action(s, a, t) for a in actions)
        s.tracking = (not s.all_judged or t <= s.end) and valid_pos and valid

    def post_process_head(s: _Obj, t: float, pos, actions: frozenset):
        if not s.res.head_hit or not in_follow(s, t, pos, True):
            return
        all_in = True
        for nd in s.nested:
            if nd.judged:
                continue
            if nd.time > t:
                break
            if (nd.x - pos[0]) ** 2 + (nd.y - pos[1]) ** 2 > follow2:
                all_in = False
                break
        for nd in s.nested:
            if nd.judged:
                continue
            if nd.time > t:
                break
            judge_nested(s, nd, all_in, t, actions, pos)
        update_tracking(s, t, actions, all_in or in_follow(s, t, pos, False))
        if s.tail is not None and s.tail.judged and not s.slider_judged and t >= s.end:
            judge_slider(s)

    def try_judge_nested(s: _Obj, nd: _Nested, t: float, actions: frozenset, pos):
        off = t - nd.time
        if nd.kind == "tail":
            if off < TAIL_LENIENCY:
                return
            if s.last_tick is not None and not s.last_tick.judged:
                return
        elif off < 0:
            return
        if not s.judged:
            return
        if s.tracking:
            judge_nested(s, nd, True, t, actions, pos)
        elif off >= 0:
            judge_nested(s, nd, False, t, actions, pos)

    # -------------------------------------------------------- spinners
    def spin_report(s: _Obj, delta: float):
        if delta == 0:
            return
        s.spin_total += delta
        cur = s.spin_total - s.spin_at_completion
        s.spin_cur_max = max(s.spin_cur_max, abs(cur))
        while s.spin_cur_max >= 360:
            direction = 1 if cur > 0 else -1
            s.spin_completed += 1
            s.spin_at_completion += direction * 360
            cur = s.spin_total - s.spin_at_completion
            s.spin_cur_max = abs(cur)

    def spin_update(s: _Obj, t: float, pos, actions: frozenset):
        o = s.obj
        tracking = o.time <= t < o.end_time and not s.judged and bool(actions)
        ang = -math.degrees(math.atan2(pos[0] - 256.0, pos[1] - 192.0))
        if s.last_angle is not None:
            d = ang - s.last_angle
            if d > 180:
                d -= 360
            if d < -180:
                d += 360
            if tracking:
                spin_report(s, d * abs(rate))
        s.last_angle = ang

    def judge_spinner(s: _Obj):
        if ctx["stopped"]:
            return
        o, r = s.obj, s.res
        dur_s = (o.end_time - o.time) / 1000
        required = int(min_rps * dur_s + 0.0001)
        bonus_max = max(0, int(max_rps * dur_s + 0.0001) - required - 2)
        total = 360 * s.spin_completed + s.spin_cur_max
        progress = 1.0 if required == 0 or spun_out else total / 360 / required
        res = GREAT if progress >= 1 else OK if progress > 0.9 else MEH if progress > 0.75 else MISS
        spins = int(total / 360)
        small, large = min(spins, required + 2), min(max(spins - required - 2, 0), bonus_max)
        stats["small_bonus"] += small
        stats["large_bonus"] += large
        stats["ignore_miss"] += (required + 2 - small) + (bonus_max - large)   # ticks not spun
        s.judged = s.all_judged = True
        r.result = res
        r.head_hit = res != MISS
        r.spins, r.spins_required = total / 360, float(required)
        count_main(res)
        add_combo(res != MISS)

    # -------------------------------------------------------- one game update
    def update(t: float, pos, actions: frozenset, with_spin: bool):
        # lazer updates later objects first; inside a slider: tracking, ticks, repeats, tail, head
        for s in reversed(active):
            o = s.obj
            if o.is_slider:
                if s.all_judged:
                    continue
                update_tracking(s, t, actions, in_follow(s, t, pos, s.tracking))
                for kind in ("tick", "repeat", "tail"):
                    for nd in s.nested:
                        if nd.kind == kind and not nd.judged:
                            try_judge_nested(s, nd, t, actions, pos)
                if not s.judged and t - s.time > w_meh:
                    judge_head(s, MISS)
                # DrawableSlider judges itself once the tail is judged and the slider's end is reached
                if s.tail is not None and s.tail.judged and not s.slider_judged and t >= s.end:
                    judge_slider(s)
            elif o.is_spinner:
                if s.judged:
                    continue
                if with_spin:
                    spin_update(s, t, pos, actions)
                if t >= o.end_time:
                    judge_spinner(s)
            elif not s.judged and t - s.time > w_meh:
                judge_head(s, MISS)

    # -------------------------------------------------------- input
    presses: list[Press] = []
    open_press: dict[str, Press] = {}

    def press(t: float, pos, action: int, p: Press | None):
        for s in active:
            if s.obj.is_spinner or not can_receive(s):
                continue
            o = s.obj
            dist2 = (pos[0] - s.x) ** 2 + (pos[1] - s.y) ** 2
            hovered = dist2 <= r2
            result = result_for(t - s.time) if not s.judged else None
            act = check_hittable(s, t, result) if not s.judged else SHAKE
            if abs(t - o.time) <= w_meh + 200 and not s.judged:
                s.res.clicks.append(ClickSeen(t, math.sqrt(dist2) / radius, act, hovered, pos[0], pos[1]))
            if not hovered:
                if act == CLICK and abs(t - o.time) <= w_meh and p is not None and p.outcome == "none":
                    p.outcome = "off_target"   # tapped for this note but outside the circle: an aim miss
                continue
            if p is not None and p.outcome == "off_target":
                p.outcome = "none"             # it did reach a (later) note after all
            if not s.judged:
                if act == CLICK and result is not None:
                    judge_head(s, result, t, pos, p)
                    if o.is_slider:
                        # runs before HitReceptor sets HitAction, exactly like lazer
                        post_process_head(s, t, pos, cur_actions)
                elif p is not None and p.outcome == "none":
                    p.outcome = "too_early" if result is None else "notelock"
            if s.hit_action is None:
                s.hit_action = action
            return

    ts, xs, ys, ks = replay.t, replay.x, replay.y, replay.keys
    n = len(ts)
    queue_i = 0
    active: list[_Obj] = []
    cur_actions: frozenset = frozenset()
    prev_t = None
    prev_pos = None
    prev_actions: frozenset = frozenset()

    def pending_times(lo: float, hi: float) -> list[float]:
        """Moments in (lo, hi) where lazer would judge something between two frames, plus
        regular steps while a slider is in progress (live play updates tracking far more
        often than the ~60 Hz a replay stores)."""
        out = []
        for s in active:
            o = s.obj
            if o.is_spinner:
                if not s.judged and lo < o.end_time < hi:
                    out.append(o.end_time)
                continue
            if not s.judged:
                tm = s.time + w_meh + 1e-6
                if lo < tm < hi:
                    out.append(tm)
            if o.is_slider and not s.all_judged:
                for nd in s.nested:
                    if nd.judged:
                        continue
                    if nd.kind == "tail":
                        for tm in (nd.time + TAIL_LENIENCY, nd.time):
                            if lo < tm < hi:
                                out.append(tm)
                    elif lo < nd.time < hi:
                        out.append(nd.time)
                if lo < s.end < hi:
                    out.append(s.end)
                if tracking_step and s.time < hi and lo < s.end:
                    a, b = max(lo, s.time), min(hi, s.end)
                    k = math.floor((a - lo) / tracking_step) + 1
                    tm = lo + k * tracking_step
                    while tm < b:
                        out.append(tm)
                        tm += tracking_step
        return sorted(set(out))

    def activate(t: float):
        nonlocal queue_i, active
        changed = False
        while queue_i < len(states) and states[queue_i].lifetime_start <= t:
            active.append(states[queue_i])
            queue_i += 1
            changed = True
        if changed or len(active) > 32:
            active = [s for s in active if not s.all_judged or _end_time(s) > t - 1000]

    for fi in range(n):
        if ctx["stopped"]:
            break
        t = float(ts[fi])
        pos = (float(xs[fi]), float(ys[fi]))
        k = int(ks[fi])
        actions = frozenset(a for a, bits in ((LEFT, KEY_M1 | KEY_K1), (RIGHT, KEY_M2 | KEY_K2)) if k & bits)

        if prev_t is not None and t > prev_t:
            ctx["on_frame"] = False
            for tm in pending_times(prev_t, t):
                activate(tm)
                f = (tm - prev_t) / (t - prev_t)
                ipos = (prev_pos[0] + (pos[0] - prev_pos[0]) * f, prev_pos[1] + (pos[1] - prev_pos[1]) * f)
                update(tm, ipos, prev_actions, with_spin=False)
            ctx["on_frame"] = True
        activate(t)

        # physical presses for the tapping analysis (lazer only records left/right actions)
        if replay.is_lazer:
            phys = {"L": LEFT in actions, "R": RIGHT in actions}
        else:
            phys = {"K1": bool(k & KEY_K1), "K2": bool(k & KEY_K2),
                    "M1": bool(k & KEY_M1) and not (k & KEY_K1), "M2": bool(k & KEY_M2) and not (k & KEY_K2)}
        new_left = new_right = None
        for key, down in phys.items():
            if down and key not in open_press:
                p = Press(len(presses), key, t, pos[0], pos[1])
                presses.append(p)
                open_press[key] = p
                if key in ("L", "K1", "M1") and new_left is None:
                    new_left = p
                elif key in ("R", "K2", "M2") and new_right is None:
                    new_right = p
            elif not down and key in open_press:
                open_press.pop(key).release = t

        cur_actions = actions
        for a, p in ((LEFT, new_left), (RIGHT, new_right)):
            if a in actions and a not in prev_actions:
                press(t, pos, a, p)
        update(t, pos, actions, with_spin=True)
        prev_t, prev_pos, prev_actions = t, pos, actions

    # replay ended before these objects were judged (quit / failed play): unplayed
    for s in states:
        r = s.res
        if s.obj.is_slider and s.judged and r.result == -1:
            r.result = r.head_result if not classic_slider else -1
        if r.result == -1:
            r.head_hit = False
            r.miss_reason = None
        elif r.head_result == -1 and not s.obj.is_spinner:
            r.head_result = MISS
    for p in open_press.values():
        p.release = None

    for s in states:
        if s.res.result != -1:
            classify_miss_reason(s, pb, replay)

    counts = {GREAT: stats["great"], OK: stats["ok"], MEH: stats["meh"], MISS: stats["miss"]}
    return SimResult(results, presses, counts, max_combo, radius, (pb.hit300, pb.hit100, pb.hit50), "lazer",
                     lazer_stats=dict(stats))
