"""Setup tips: what to change in your setup (tablet area or sensitivity, audio offset, keys) and only when the
replays show it is worth it.

A change is suggested only when all three hold:

* it is big enough to feel: on your long jumps (the longest quarter of them) it moves where you land by at least
  :data:`FELT_SHIFT` circle radii; a click offset is at least :data:`FELT_OFFSET` radii on every note; centring your
  timing wins at least :data:`FELT_300S` of 300s;
* it costs you: your misses lean the way the change fixes (past or short of the note, to one side, early or late
  on most plays), at least :data:`LEAN_SHARE` of :data:`LEAN_MIN` or more;
* the fix is a value you can set: the new millimetres, sensitivity, offset or key setting.

Otherwise the advice is to keep the setting, or that there isn't enough data yet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from osu_coach.profile.domain import Profile, played_notes
from osu_coach.settings.domain import Setup
from osu_coach.tips.domain.common import PLAYFIELD_SCREEN_FRACTION

FELT_SHIFT = 0.2  # circle radii a change moves where you land on long jumps: from here you feel it
FELT_OFFSET = 0.15  # circle radii every click is off by: from here moving the area is worth it
FELT_300S = 0.01  # share of 300s that centring your timing wins: from here the audio offset is worth changing
LEAN_SHARE = 0.6  # this share of your misses must lean the way the change fixes ...
LEAN_MIN = 30  # ... out of at least this many misses
MIN_JUMPS = 200  # jumps before the tablet area / sensitivity is checked
LONG_JUMP = 0.75  # long jumps: the longest quarter (quantile of the jump length)
MIN_PLAYS = 10  # plays with 100+ hits before the audio offset is checked
SAME_BIAS = 0.7  # share of plays early (or late) for the bias to be the offset, not the maps
MIN_PRESSES = 2000  # key presses before the keys are checked
DOUBLE_PER_1000 = 5.0  # same-key re-presses within 20 ms per 1000 presses: keys fire twice
EXTRA_PER_100 = 3.0  # taps that hit nothing, per 100 notes
CHATTER_PER_1000 = 8.0  # re-presses on a plain keyboard: a chattering switch
RELEASES_PER_1000 = 1.0  # sliders broken by a key letting go, per 1000 sliders
SAYO_STEP = 0.05  # the SayoDevice configurator's step (mm)

ORDER = ("area_size", "sensitivity", "area_position", "area_rotation", "offset", "keys")
VERDICT_ORDER = {"change": 0, "unknown": 1, "keep": 2}


@dataclass
class Change:
    """One setting: what it is now (None = not entered) and what to set it to."""

    setting: str
    now: str | None
    to: str


@dataclass
class Advice:
    key: str
    title: str
    verdict: str  # "change" | "keep" | "unknown"
    why: str
    changes: list[Change] = field(default_factory=list)
    where: str | None = None


def mm_per_osu_px(setup: Setup) -> tuple[float, float] | None:
    """Tablet millimetres per osu!pixel (full-screen mapping assumed)."""
    if not setup.area_w_mm or not setup.area_h_mm:
        return None
    screen_px_per_osu_px = setup.screen_h_px * PLAYFIELD_SCREEN_FRACTION / 384.0
    return (
        setup.area_w_mm / setup.screen_w_px * screen_px_per_osu_px,
        setup.area_h_mm / setup.screen_h_px * screen_px_per_osu_px,
    )


def _jumps(p: Profile) -> pd.DataFrame:
    """The jumps of the aim calibration (hits and aim misses of notes 1.5+ circle widths from the previous one), with
    the movement they asked for (``ix`` / ``iy``, osu!px), its length in circle radii and whether it is mostly
    sideways (``horizontal``)."""
    O = getattr(p, "objects", None)
    need = {"start_x", "start_y", "x", "y", "err_dx", "err_dy", "dist_norm", "radius", "along", "cross"}
    if O is None or O.empty or not need <= set(O.columns):
        return pd.DataFrame()
    P = played_notes(O)
    J = P[(P["head_hit"] | (P["miss_reason"] == "aim")) & (P["dist_norm"] >= 1.5)]
    J = J.dropna(subset=["start_x", "start_y", "err_dx", "err_dy"])
    ix, iy = J["x"] - J["start_x"], J["y"] - J["start_y"]
    return J.assign(
        ix=ix, iy=iy, length=np.hypot(ix, iy) / J["radius"].clip(lower=1.0), horizontal=ix.abs() >= iy.abs()
    )


def _long_misses(J: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """The misses on long jumps, and how long a long jump is (circle radii)."""
    long = float(J["length"].quantile(LONG_JUMP))
    return J[(J["length"] >= long) & ~J["head_hit"].astype(bool)], long


def _share(lean: pd.Series) -> tuple[float, int]:
    return (float(lean.mean()) if len(lean) else math.nan), int(len(lean))


def _leans(share: float, n: int) -> bool:
    return n >= LEAN_MIN and share >= LEAN_SHARE


# ---------------------------------------------------------------- tablet area size / mouse sensitivity
def _size(p: Profile, s: Setup, J: pd.DataFrame) -> Advice:
    r = p.regression
    tablet = s.device == "tablet"
    key, title = ("area_size", "Tablet area size") if tablet else ("sensitivity", "Sensitivity")
    if tablet:
        axes = [
            ("width", "sideways", r["scale_x"], J[J["horizontal"]]),
            ("height", "up and down", r["scale_y"], J[~J["horizontal"]]),
        ]
    else:  # one sensitivity for both directions
        axes = [("", "", (r["scale_x"] + r["scale_y"]) / 2, J)]
    checked = []
    for name, way, scale, jumps in axes:
        if len(jumps) < LEAN_MIN:
            continue
        misses, long = _long_misses(jumps)
        share, n = _share(misses["along"] > 0 if scale > 1 else misses["along"] < 0)
        checked.append(
            {"name": name, "way": way, "scale": scale, "shift": abs(scale - 1) * long, "share": share, "n": n}
        )
    felt = [a for a in checked if a["shift"] >= FELT_SHIFT]
    due = [a for a in felt if _leans(a["share"], a["n"])]
    worst = max(checked, key=lambda a: abs(a["scale"] - 1), default=None)
    if worst is None:
        return Advice(key, title, "unknown", "Not enough jumps yet to check it.")
    if not due:
        off = abs(worst["scale"] - 1)
        if felt and all(a["n"] < LEAN_MIN for a in felt):
            return Advice(
                key,
                title,
                "unknown",
                f"Your movement is {off:.0%} off, but there are too few misses on long jumps yet to tell if it costs you.",
            )
        if felt:
            return Advice(
                key,
                title,
                "keep",
                f"Your movement is {off:.0%} off, but your misses land short as often as past: keep it.",
            )
        return Advice(
            key, title, "keep", f"You land on the notes: your movement is within {max(off, 0.01):.0%} of the jumps."
        )
    a = max(due, key=lambda x: x["shift"])
    over = a["scale"] > 1
    way = f" {a['way']}" if len(due) == 1 and a["way"] else ""
    why = (
        f"You {'overshoot' if over else 'fall short on'} long jumps{way}: your movement is {abs(a['scale'] - 1):.0%} "
        f"too {'long' if over else 'short'}, and {a['share']:.0%} of those misses land {'past' if over else 'short of'} the note."
    )
    if tablet:
        changes = []
        for b in due:
            now = s.area_w_mm if b["name"] == "width" else s.area_h_mm
            to = (
                f"{now * b['scale']:.1f} mm"
                if now
                else f"{abs(b['scale'] - 1):.0%} {'larger' if b['scale'] > 1 else 'smaller'}"
            )
            changes.append(Change(f"Area {b['name']}", f"{now:g} mm" if now else None, to))
        where = "Your tablet driver (OpenTabletDriver: Output → Area)."
        if not (s.area_w_mm and s.area_h_mm):
            where += " Enter your area in Your setup for exact millimetres."
        return Advice(key, title, "change", why, changes, where)
    sens = s.ingame_sens or 1.0
    changes = [Change("osu! sensitivity", f"{sens:.2f}", f"{sens / a['scale']:.2f}")]
    if s.mouse_dpi:
        changes.append(Change("or mouse DPI", str(s.mouse_dpi), str(int(round(s.mouse_dpi / a["scale"] / 50) * 50))))
    return Advice(key, title, "change", why, changes, "osu!: Settings → Input → Sensitivity (or your mouse software).")


# ---------------------------------------------------------------- tablet area position
def _direction(dx: float, dy: float) -> str:
    """Where a small displacement points, in words: only the parts that matter ("left", "left and down")."""
    size = math.hypot(dx, dy)
    parts = []
    if abs(dx) >= 0.35 * size:
        parts.append("right" if dx > 0 else "left")
    if abs(dy) >= 0.35 * size:
        parts.append("down" if dy > 0 else "up")
    return " and ".join(parts)


def _position(p: Profile, s: Setup) -> Advice:
    r = p.regression
    ox, oy = r["offset_x"], r["offset_y"]
    off = math.hypot(ox, oy)
    title = "Tablet area position"
    if off < 1e-9 or off / r["radius"] < FELT_OFFSET or off < 3 * r["offset_se"]:
        return Advice("area_position", title, "keep", "Your clicks are centred on the notes.")
    O = played_notes(p.objects)
    misses = O[(O["miss_reason"] == "aim") & ~O["head_hit"].astype(bool)].dropna(subset=["err_dx", "err_dy"])
    share, n = _share((misses["err_dx"] * ox + misses["err_dy"] * oy) > 0)
    where_to = _direction(ox, oy)
    if not _leans(share, n):
        return Advice(
            "area_position",
            title,
            "keep",
            f"Your clicks land {off:.0f} px {where_to} of the notes, but your misses don't lean that way: keep it.",
        )
    why = (
        f"Your clicks land {off:.0f} px {where_to} of every note, and {share:.0%} of your aim misses are on that side."
    )
    mm = mm_per_osu_px(s)
    where = "Your tablet driver (OpenTabletDriver: Output → X / Y, the centre of the area)."
    if mm and s.area_x_mm is not None and s.area_y_mm is not None:
        changes = [
            Change("Area X", f"{s.area_x_mm:g} mm", f"{s.area_x_mm + ox * mm[0]:.1f} mm"),
            Change("Area Y", f"{s.area_y_mm:g} mm", f"{s.area_y_mm + oy * mm[1]:.1f} mm"),
        ]
    elif mm:
        dx, dy = ox * mm[0], oy * mm[1]
        changes = [Change("Area position", None, f"move it {math.hypot(dx, dy):.1f} mm {_direction(dx, dy)}")]
        where += " Enter its X / Y in Your setup for the exact values."
    else:
        changes = [Change("Area position", None, f"move it a little {where_to}")]
        where += " Enter your area in Your setup for millimetres."
    return Advice("area_position", title, "change", why, changes, where)


# ---------------------------------------------------------------- tablet area rotation
def _rotation(p: Profile, J: pd.DataFrame) -> Advice:
    rot = p.regression["rotation_deg"]
    misses, long = _long_misses(J)
    turn = "clockwise" if rot > 0 else "counter-clockwise"
    title = "Tablet area rotation"
    if abs(math.radians(rot)) * long < FELT_SHIFT:
        return Advice("area_rotation", title, "keep", f"Your jumps go straight ({abs(rot):.1f}° off).")
    share, n = _share(misses["cross"] > 0 if rot > 0 else misses["cross"] < 0)
    if not _leans(share, n):
        return Advice(
            "area_rotation",
            title,
            "keep",
            f"Your jumps turn {abs(rot):.1f}° {turn}, but your misses don't lean that way: keep it.",
        )
    return Advice(
        "area_rotation",
        title,
        "change",
        f"Your jumps come out turned {abs(rot):.1f}° {turn}, and {share:.0%} of your long-jump misses land on that side.",
        [Change("Area rotation", None, f"turn it {abs(rot):.0f}° {turn}")],
        "Your tablet driver (OpenTabletDriver: Output → Rotation).",
    )


# ---------------------------------------------------------------- audio offset
def timing_bias(p: Profile) -> dict | None:
    """Your hit timing play by play: ``bias`` = the median of the plays' average hit error (ms, − early, + late),
    ``same`` = the share of plays on that side, ``plays``, and ``gain`` = how many more 300s (share) centring it
    would win. None with fewer than :data:`MIN_PLAYS` plays of 100+ hits."""
    m = p.replays
    if m is None or m.empty or "mean_error" not in m:
        return None
    hits = m[["n300", "n100", "n50"]].fillna(0).sum(axis=1)
    plays = m[(hits >= 100) & m["mean_error"].notna()]
    if len(plays) < MIN_PLAYS:
        return None
    bias = float(plays["mean_error"].median())
    same = float((np.sign(plays["mean_error"]) == np.sign(bias)).mean()) if bias else 0.0
    sigma = (p.tapping.get("ur_single") or p.tapping.get("ur") or 0) / 10
    window = float(np.median(np.clip(80 - 6 * plays["od"].astype(float), 10, None))) if "od" in plays else 32.0

    def great(b: float) -> float:  # share of hits within the 300 window, timing ~ N(b, sigma)
        if not sigma or not math.isfinite(sigma):
            return 1.0
        z = sigma * math.sqrt(2)
        return 0.5 * (math.erf((window - b) / z) - math.erf((-window - b) / z))

    return {"bias": bias, "same": same, "plays": len(plays), "gain": great(0.0) - great(bias)}


def _offset(p: Profile, s: Setup) -> Advice:
    title = "Audio offset"
    t = timing_bias(p)
    if t is None:
        return Advice("offset", title, "unknown", "Not enough plays yet to check it.")
    b = t["bias"]
    word = "early" if b < 0 else "late"
    if t["gain"] < FELT_300S:
        return Advice("offset", title, "keep", f"Your hits are centred ({abs(b):.1f} ms {word} on average).")
    if t["same"] < SAME_BIAS:
        return Advice(
            "offset",
            title,
            "keep",
            f"You hit {abs(b):.0f} ms {word}, but not on every map: that's timing, not the offset (see Tips).",
        )
    why = (
        f"You hit {abs(b):.0f} ms {word} on {t['same']:.0%} of your plays, the same on every map, so it's the offset. "
        f"Centring it gives about {t['gain']:.0%} more 300s."
    )
    if s.client == "lazer":  # lazer suggests its offset minus your average hit error
        change = Change("Audio offset", None, f"{abs(b):.0f} ms {'higher' if b < 0 else 'lower'}")
        where = "lazer: Settings → Audio → Offset, or play a map and press 'Calibrate using last play'."
    else:
        change = Change("Universal offset", None, f"correct {abs(b):.0f} ms of {word} hitting")
        where = "osu!stable: Options → Audio → Offset wizard (it measures it for you)."
    return Advice("offset", title, "change", why, [change], where)


# ---------------------------------------------------------------- keys
def _mm(v: float) -> float:
    return round(round(v / SAYO_STEP) * SAYO_STEP, 2)


def _keys(p: Profile, s: Setup) -> Advice:
    t = p.tapping
    title = {"sayo": "SayoDevice", "rapid_trigger": "Rapid trigger"}.get(s.keyboard, "Keys")
    presses = t.get("press_count") or 0
    if presses < MIN_PRESSES:
        return Advice("keys", title, "unknown", "Not enough key presses yet to check them.")
    chatter = t.get("chatter_per_1000") or 0.0
    extra = t.get("extra_presses_per_100") or 0.0
    sliders = (getattr(p, "sliders", {}) or {}).get("sliders") or 0
    breaks = getattr(p, "slider_breaks", {}) or {}
    released = breaks.get("released", 0)
    plain = s.keyboard not in ("sayo", "rapid_trigger")
    double = chatter >= (CHATTER_PER_1000 if plain else DOUBLE_PER_1000) or (not plain and extra >= EXTRA_PER_100)
    letting_go = (
        not plain
        and released >= 10
        and sliders > 0
        and released / sliders * 1000 >= RELEASES_PER_1000
        and released / max(sum(breaks.values()), 1) >= 0.4
    )
    reasons = []
    if double:
        reasons.append(
            f"your keys fire twice: {chatter:.1f} double presses per 1000 presses"
            if chatter >= DOUBLE_PER_1000
            else f"{extra:.1f} extra taps per 100 notes hit nothing"
        )
    if letting_go:
        reasons.append(f"{released:.0f} sliders broke because a key let go mid-slider")
    if plain:
        if not double:
            return Advice("keys", title, "keep", "No double presses in your replays.")
        return Advice(
            "keys",
            title,
            "change",
            f"A key chatters: {chatter:.1f} double presses per 1000 presses.",
            [Change("Switch", None, "clean it, or try other keys")],
        )
    changes = (
        _sayo_changes(s, double, letting_go, t, reasons) if s.keyboard == "sayo" else _rt_changes(s, double, letting_go)
    )
    if not changes:
        return Advice("keys", title, "keep", "No double presses or keys letting go mid-slider in your replays.")
    why = reasons[0][0].upper() + reasons[0][1:] + (f"; {reasons[1]}" if len(reasons) > 1 else "") + "."
    entered = all(c.now is not None for c in changes)
    where = (
        "SayoDevice web configurator (sayodevice.com → Key stroke)."
        if s.keyboard == "sayo"
        else "Your keyboard's software."
    )
    if not entered:
        where += " Enter your current values in Your setup for exact numbers."
    return Advice("keys", title, "change", why, changes, where)


def _rt_changes(s: Setup, double: bool, letting_go: bool) -> list[Change]:
    """Rapid-trigger keyboard: less sensitive when keys fire twice or let go mid-slider."""
    if not (double or letting_go):
        return []
    rt = s.rt_release_mm or s.rt_press_mm
    changes = [
        Change(
            "Rapid-trigger sensitivity", f"{rt:.2f} mm" if rt else None, f"{rt + 0.1:.2f} mm" if rt else "0.1 mm higher"
        )
    ]
    if double:
        act = s.actuation_mm
        changes.append(
            Change(
                "Actuation point", f"{act:.1f} mm" if act else None, f"{act + 0.2:.1f} mm" if act else "0.2 mm deeper"
            )
        )
    return changes


def _sayo_changes(s: Setup, double: bool, letting_go: bool, t: dict, reasons: list[str]) -> list[Change]:
    """SayoDevice: rapid trigger less sensitive when keys fire twice (and never active above the trigger point), RT
    Release higher when keys let go mid-slider, RT on for fast streams, and values the device can't work with."""
    trig, rel = s.sayo_trigger_mm, s.sayo_release_mm
    rt_trig, rt_rel, upper = s.sayo_rt_trigger_mm, s.sayo_rt_release_mm, s.sayo_rt_upper_mm
    changes: list[Change] = []

    def mm(v: float | None) -> str | None:
        return None if v is None else f"{v:.2f} mm"

    if double:
        new_trig = _mm(max(rt_trig + SAYO_STEP, 0.15)) if rt_trig is not None else None
        new_rel = _mm(rt_rel + SAYO_STEP) if rt_rel is not None else None
        if new_trig is not None and new_rel is not None:
            new_rel = max(new_rel, new_trig)  # the device needs RT Trigger <= RT Release
        changes.append(Change("RT Trigger", mm(rt_trig), mm(new_trig) or f"{SAYO_STEP:g} mm higher"))
        changes.append(Change("RT Release", mm(rt_rel), mm(new_rel) or f"{SAYO_STEP:g} mm higher"))
        rt_trig, rt_rel = new_trig, new_rel
        if upper is not None and trig is not None and upper < trig:  # rapid trigger fires above the trigger point
            changes.append(Change("RT Upper Bound", mm(upper), mm(trig)))
    if letting_go and not double:
        new_rel = _mm(rt_rel + SAYO_STEP) if rt_rel is not None else None
        changes.append(Change("RT Release", mm(rt_rel), mm(new_rel) or f"{SAYO_STEP:g} mm higher"))
        rt_rel = new_rel
    speed = t.get("comfort_bpm") or 0
    if s.sayo_rt is False and speed >= 200:
        changes.append(Change("RT Mode", "off", "on"))
        reasons.append(f"you stream {speed:.0f} BPM, and rapid trigger resets keys without a full lift")
    # values the device can't work with, whatever the replays show
    if rt_trig is not None and rt_rel is not None and rt_trig > rt_rel and not double:
        changes.append(Change("RT Trigger", mm(rt_trig), mm(rt_rel)))
        reasons.append("RT Trigger can't be larger than RT Release")
    if trig is not None and rel is not None and rel >= trig:
        changes.append(Change("Release", mm(rel), mm(_mm(trig - SAYO_STEP))))
        reasons.append("Release must sit above Trigger, or the key can't reset")
    return changes


# ---------------------------------------------------------------- all of it
def setup_advice(p: Profile, s: Setup) -> list[Advice]:
    """Every setup check for this device: the changes first, then what can't be told yet, then what to keep."""
    out: list[Advice] = []
    J = _jumps(p)
    if not p.regression or len(J) < MIN_JUMPS:
        title = "Tablet area" if s.device == "tablet" else "Sensitivity"
        out.append(
            Advice(
                "area_size" if s.device == "tablet" else "sensitivity",
                title,
                "unknown",
                f"Not enough jumps yet to check it ({MIN_JUMPS} needed).",
            )
        )
    else:
        out.append(_size(p, s, J))
        if s.device == "tablet":  # a mouse can't be moved or turned in a setting
            out += [_position(p, s), _rotation(p, J)]
    out += [_offset(p, s), _keys(p, s)]
    return sorted(out, key=lambda a: (VERDICT_ORDER[a.verdict], ORDER.index(a.key)))
