"""Tips engine: turns a replay profile + the player's setup into concrete advice.

Every tip carries the evidence (numbers measured from the replays) and concrete
actions, and — where the data supports it — exact settings to try (tablet area,
mouse sensitivity, rapid-trigger values). Rules of thumb used:

* tablet area: overaim -> area too small (too sensitive) -> enlarge; underaim ->
  shrink; change in small steps (5-10 %) and keep a setting for days
  (osu! community guides, rgbeing's aim-analyzer cheat-sheet for
  skew/scale/rotation);
* rapid trigger (hall-effect keyboards): osu! players typically sit around
  0.3-1.0 mm actuation with 0.1-0.3 mm RT sensitivity; very low values (0.1 mm)
  cause chatter / accidental double taps, too high values miss fast taps.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import pandas as pd

from .profile import Profile, SKILL_LABELS

PLAYFIELD_SCREEN_FRACTION = 0.8   # osu! playfield height = 80 % of screen height


@dataclass
class Setup:
    device: str = "tablet"            # tablet | mouse
    handedness: str = "right"         # right | left
    area_w_mm: float | None = None
    area_h_mm: float | None = None
    area_x_mm: float | None = None    # area centre on the tablet (OpenTabletDriver X / Y)
    area_y_mm: float | None = None
    screen_w_px: int = 1920
    screen_h_px: int = 1080
    mouse_dpi: int | None = None
    ingame_sens: float | None = None  # osu! sensitivity multiplier
    keyboard: str = "standard"        # standard | rapid_trigger | sayo
    actuation_mm: float | None = None
    rt_press_mm: float | None = None
    rt_release_mm: float | None = None
    # SayoDevice keypad (names as in its web configurator); None = not entered
    sayo_stroke_mm: float | None = None
    sayo_trigger_mm: float | None = None
    sayo_release_mm: float | None = None
    sayo_rt: bool | None = None
    sayo_rt_trigger_mm: float | None = None
    sayo_rt_release_mm: float | None = None
    sayo_full_stroke: bool | None = None
    sayo_rt_upper_mm: float | None = None
    sayo_rt_lower_mm: float | None = None
    client: str = "stable"            # stable | lazer


@dataclass
class Tip:
    category: str
    title: str
    severity: int                      # 1 (nice to know) .. 3 (biggest impact)
    evidence: str
    actions: list[str] = field(default_factory=list)
    settings: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _pct(v: float, digits: int = 1) -> str:
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v * 100:.{digits}f}%"


def _nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def mm_per_osu_px(setup: Setup) -> tuple[float, float] | None:
    """Tablet millimetres per osu!pixel (full-screen mapping assumed)."""
    if not setup.area_w_mm or not setup.area_h_mm:
        return None
    screen_px_per_osu_px = setup.screen_h_px * PLAYFIELD_SCREEN_FRACTION / 384.0
    return (setup.area_w_mm / setup.screen_w_px * screen_px_per_osu_px,
            setup.area_h_mm / setup.screen_h_px * screen_px_per_osu_px)


def _scale_step(r: dict) -> float | None:
    """Area/sensitivity change for over/underaim (fraction), None if the scale is fine."""
    scale = (r["scale_x"] + r["scale_y"]) / 2
    if r["n"] < 60 or 0.96 < scale < 1.04:
        return None
    step = max(min(abs(scale - 1), 0.10), 0.03)
    return step if scale > 1 else -step


def offset_is_sizeable(r: dict) -> bool:
    """A constant click offset worth correcting: clearly measured and big enough to cost hits
    (a few px don't matter; the circle radius is ~25-55 px)."""
    off = math.hypot(r["offset_x"], r["offset_y"])
    return r["n"] >= 80 and off >= max(4.0, 3 * r["offset_se"]) and off >= 0.15 * r["radius"]


def _offset_words(ox: float, oy: float) -> tuple[str, str]:
    return ("left" if ox < 0 else "right"), ("up" if oy < 0 else "down")


def suggest_tablet_area(p: Profile, s: Setup) -> dict | None:
    """Tablet area to try, in OpenTabletDriver terms (width × height, X / Y = centre of the area, mm):
    size from over/underaim, position from a constant click offset. None without a known area."""
    r = p.regression
    if s.device != "tablet" or not r or not (s.area_w_mm and s.area_h_mm):
        return None
    w, h, x, y = s.area_w_mm, s.area_h_mm, s.area_x_mm, s.area_y_mm
    nw, nh, nx, ny = w, h, x, y
    why = []
    step = _scale_step(r)
    if step:
        nw, nh = round(w * (1 + step), 1), round(h * (1 + step), 1)
        why.append(f"you {'over' if step > 0 else 'under'}aim jumps by {abs(step):.0%} → area "
                   f"{'larger' if step > 0 else 'smaller'} (same centre)")
    ox, oy = r["offset_x"], r["offset_y"]
    horiz, vert = _offset_words(ox, oy)
    if offset_is_sizeable(r):
        mm = mm_per_osu_px(s)
        dx, dy = ox * mm[0], oy * mm[1]
        nx = None if x is None else round(x + dx, 1)
        ny = None if y is None else round(y + dy, 1)
        why.append(f"your clicks land {abs(ox):.1f} px {horiz} and {abs(oy):.1f} px {vert} of the centre → move "
                   f"the area {abs(dx):.1f} mm {horiz} and {abs(dy):.1f} mm {vert}")
    else:
        why.append(f"your jumps land centred (constant offset {abs(ox):.1f} px {horiz}, {abs(oy):.1f} px {vert} — "
                   "'Constant offset' on the Aim page; too little to matter) → keep X / Y")
    return {"w": nw, "h": nh, "x": nx, "y": ny, "now": {"w": w, "h": h, "x": x, "y": y},
            "changed": (nw, nh, nx, ny) != (w, h, x, y), "why": why}


# ---------------------------------------------------------------- main entry
def make_tips(p: Profile, setup: Setup | None = None) -> list[Tip]:
    setup = setup or Setup()
    tips: list[Tip] = []
    for rule in (_miss_cause_tip, _calibration_tip, _area_scale_tips, _area_rotation_offset_tips, _quadrant_tips, _direction_tips,
                 _distance_angle_tips, _timing_tips, _stream_tips, _key_usage_tips, _keyboard_tips, _slider_tips,
                 _reading_tips, _consistency_tips):
        try:
            out = rule(p, setup)
        except Exception as exc:  # noqa: BLE001 - one bad rule must not hide the others
            out = [Tip("Internal", f"Could not evaluate {rule.__name__}", 1, str(exc))]
        tips.extend(out or [])
    tips.sort(key=lambda t: -t.severity)
    return tips


# ---------------------------------------------------------------- rules
def _miss_cause_tip(p: Profile, s: Setup):
    mb = p.miss_breakdown
    total = sum(mb.values())
    if total < 10:
        return []
    groups = {
        "aim": mb.get("aim", 0),
        "speed_aim": mb.get("speed_aim", 0),
        "timing": mb.get("early", 0) + mb.get("late", 0),
        "tapping": mb.get("no_tap", 0),
        "reading": mb.get("lost", 0),
        "notelock": mb.get("notelock", 0),
    }
    top, n = max(groups.items(), key=lambda kv: kv[1])
    share = n / total
    text = {
        "aim": ("Most misses are aim misses", "You clicked in time but outside the circle, on jumps or single "
                                              "notes at normal speed."),
        "speed_aim": ("Most misses are speed-aim misses", "You tapped in time, but in streams, bursts or very fast "
                                                          "jumps the cursor couldn't keep up with the tempo."),
        "timing": ("Most misses are timing misses", "Cursor was on the note but you tapped too early/late."),
        "tapping": ("Most misses are missing taps", "Cursor was on the note but no key press arrived in time "
                                                    "(one tap for two notes, finger lag in streams)."),
        "reading": ("Most misses are 'lost' notes", "No tap and the cursor was far away — you didn't see or "
                                                    "didn't understand the note in time."),
        "notelock": ("Many misses are follow-up misses (notelock)", "You tapped the next note while the previous "
                                                                   "one was still active; osu! ignores that tap."),
    }[top]
    actions = {
        "aim": _aim_miss_actions(p),
        "speed_aim": _speed_aim_actions(p),
        "timing": ["Play below your comfort level and aim for 300s, not just hitting notes.",
                   "Tap to the music, not to the approach circle; enable the hit-error meter."],
        "tapping": ["Practice bursts/streams at a lower BPM with strict alternation.",
                    "Count notes in bursts (3, 5, 7 ...) — misses often come from tapping one note too few."],
        "reading": ["Play maps with a slightly lower AR and work your way up.",
                    "Look one or two notes ahead instead of at your cursor."],
        "notelock": ["These are usually caused by the miss right before them: fix the first miss and the "
                     "chain disappears.", "Don't spam-tap to 'catch up' after a mistake; re-find the rhythm."],
    }[top]
    names = {"speed_aim": "speed-aim"}
    breakdown = ", ".join(f"{names.get(k, k)} {v / total:.0%}" for k, v in sorted(groups.items(), key=lambda kv: -kv[1])
                          if v >= 0.5)
    weighted = (getattr(p, "levels", {}) or {}).get("weighted")
    over = (f"{total:.0f} misses (weighted by how close each map is to your level)" if weighted
            else f"{total:.0f} misses")
    return [Tip("Overview", f"{text[0]} ({share:.0%})", 3 if share >= 0.4 else 2,
                f"{text[1]} Miss causes over {over}: {breakdown}.", actions)]


def _aim_miss_where(p: Profile) -> dict[str, int]:
    """Aim misses by kind of pattern: streams (incl. bursts), flow (spaced streams), jumps, single notes."""
    O = getattr(p, "objects", None)
    if O is None or O.empty or "miss_reason" not in O or "pattern" not in O:
        return {}
    cause = O["miss_cause"] if "miss_cause" in O else O["miss_reason"]    # "aim" without speed-aim if split
    m = O[O["played"].astype(bool) & ~O["head_hit"].astype(bool) & (cause == "aim")]
    w = m["w"] if "w" in m else pd.Series(1.0, index=m.index)
    flow = m["spaced_stream"].astype(bool) if "spaced_stream" in m else False
    streams = m["pattern"].isin(["burst", "stream"])
    return {"streams": float(w[streams & ~flow].sum()), "flow": float(w[streams & flow].sum()),
            "jumps": float(w[m["pattern"].isin(["jump", "spaced"])].sum()),
            "single notes": float(w[m["pattern"] == "single"].sum())}


def _aim_miss_actions(p: Profile) -> list[str]:
    jump_advice = ["Focus practice on aim first (the 'Jump aim' playlist in Skill Development).",
                   "Your tablet area / sensitivity is checked from your jumps (Aim page → Aim calibration); a "
                   "separate tip appears only if it is off — otherwise it's precision, not calibration."]
    where = _aim_miss_where(p)
    total = sum(where.values())
    if total < 30:
        return jump_advice
    streams = where["streams"] + where["flow"]
    split = (f"streams and bursts {streams / total:.0%}, jumps {where['jumps'] / total:.0%}, "
             f"single notes {where['single notes'] / total:.0%}")
    if streams / total >= 0.4 and streams >= where["jumps"]:
        playlist = "Flow aim (spaced streams)" if where["flow"] > where["streams"] else "Tapping speed (bursts/streams)"
        return [f"Most of them are in streams and bursts ({split}): you keep tapping but the cursor falls "
                "behind or cuts corners.",
                f"Slow streams down (HT, or the '{playlist}' playlist in Skill Development) until the cursor stays "
                "on every note, then raise the speed step by step.",
                "Move with the stream's shape — a steady motion through the notes, not small jumps between them."]
    return [f"Where they happen: {split}."] + jump_advice


def _speed_aim_actions(p: Profile) -> list[str]:
    """What to do about aim misses in streams / very fast jumps, with the split against the difficulty."""
    acts = []
    sp = (getattr(p, "aim", {}) or {}).get("split", {})
    a, f = sp.get("aim"), sp.get("speed_aim")
    if a and f and a["expected"] > 0 and f["expected"] > 0:
        ra, rf = a["all_misses"] / a["expected"], f["all_misses"] / f["expected"]
        verdict = (" — the fast patterns are the real gap." if rf > 1.15 * ra else
                   " — about the same, so it's mostly that you play many fast patterns." if rf >= 0.87 * ra else
                   " — fast patterns are relatively fine for you.")
        acts.append(f"Against what the difficulty of the notes predicts: fast patterns {rf:.1f}× the expected "
                    f"misses, normal-speed jumps and notes {ra:.1f}×" + verdict)
    flow = ((getattr(p, "skills", {}) or {}).get("flow_aim") or {}).get("score")
    acts += [("Your flow-aim score is low. " if flow is not None and flow < 45 else "")
             + "Practise spaced streams below the tempo where they break (the 'Flow aim (spaced streams)' playlist "
             "in Skill Development, or the same map with HT / a lower rate), then raise the speed by ~10 BPM.",
             "Move with the stream's shape — a steady motion through the notes, not small jumps between them; "
             "keep the arm loose so the cursor can follow the tempo."]
    return acts


def aim_calibration(p: Profile, s: Setup) -> dict | None:
    """What the aim calibration (Aim page) means for the setup: ``scale`` (average), ``step`` (area /
    sensitivity change as a fraction, 0 = keep), ``now`` / ``try`` (text, None if unknown), ``lines``."""
    r = p.regression
    if not r:
        return None
    scale = (r["scale_x"] + r["scale_y"]) / 2
    step = _scale_step(r) or 0.0
    word = "overaim" if scale > 1 else "underaim"
    lines = [f"Aim calibration (Aim page), fitted on {r['n']:,} jumps: you move {_pct(r['scale_x'] - 1)} "
             f"horizontally and {_pct(r['scale_y'] - 1)} vertically compared with the real jump "
             f"(+ = too far), rotation {r['rotation_deg']:+.1f}°, constant offset "
             f"{math.hypot(r['offset_x'], r['offset_y']):.1f} px."]
    now = new = None
    if s.device == "tablet":
        if s.area_w_mm and s.area_h_mm:
            now = f"{s.area_w_mm:g} × {s.area_h_mm:g} mm"
            new = f"{s.area_w_mm * (1 + step):.1f} × {s.area_h_mm * (1 + step):.1f} mm" if step else now
        if step:
            lines.append(f"You {word} jumps by {abs(scale - 1):.0%} → make the tablet area {abs(step):.0%} "
                         f"{'larger (less sensitive)' if step > 0 else 'smaller (more sensitive)'}.")
        else:
            lines.append("Your movement matches the jumps within ±4% → keep your tablet area size.")
        if not (s.area_w_mm and s.area_h_mm):
            lines.append("Enter your area width / height in Your setup to get millimetres.")
    else:
        sens = s.ingame_sens or 1.0
        if s.mouse_dpi:
            now = f"{s.mouse_dpi} DPI × {sens:g}"
            new = (f"{int(round(s.mouse_dpi / scale / 50) * 50)} DPI × {sens:g} (or {s.mouse_dpi} DPI × "
                   f"{sens / scale:.2f})") if step else now
        else:
            now = f"sensitivity {sens:g}"
            new = f"sensitivity {sens / scale:.2f}" if step else now
        if step:
            lines.append(f"You {word} jumps by {abs(scale - 1):.0%} → {'lower' if scale > 1 else 'raise'} your "
                         f"sensitivity by about {abs(scale - 1):.0%}.")
        else:
            lines.append("Your movement matches the jumps within ±4% → keep your sensitivity.")
    return {"scale": scale, "step": step, "now": now, "try": new, "lines": lines, "device": s.device}


def _calibration_tip(p: Profile, s: Setup):
    """The aim calibration as a setup tip — shown whenever it could be measured, also when it says 'keep it'
    (the over/underaim tips give the details when a change is due)."""
    c = aim_calibration(p, s)
    if not c:
        return []
    thing = "tablet area" if c["device"] == "tablet" else "sensitivity"
    if c["step"]:
        title = (f"Aim calibration: {'larger' if c['step'] > 0 else 'smaller'} tablet area"
                 if c["device"] == "tablet" else
                 f"Aim calibration: {'lower' if c['step'] > 0 else 'higher'} sensitivity")
    else:
        title = f"Aim calibration: your {thing} fits"
    acts = c["lines"][1:]
    if c["now"]:
        acts.insert(0, f"Now {c['now']} → try {c['try']}.")
    settings = {"scale": round(c["scale"], 3), "change": round(c["step"], 3)}
    return [Tip("Setup / aim calibration", title, 2 if c["step"] else 1, c["lines"][0], acts, settings)]


def _area_scale_tips(p: Profile, s: Setup):
    r = p.regression
    if not r or r["n"] < 60:
        return []
    sx, sy = r["scale_x"], r["scale_y"]
    scale = (sx + sy) / 2
    tips = []
    evidence = (f"Measured on {r['n']} jumps: you move {_pct(sx - 1)} horizontally and {_pct(sy - 1)} vertically "
                f"compared with the real distance (+ = too far / overaim, - = not far enough / underaim).")
    signed = _scale_step(r) or 0.0
    step = abs(signed)
    if s.device == "tablet":
        if signed > 0:
            settings = None
            act = [f"Make your tablet area about {step:.0%} larger (less sensitive).",
                   "Change in one step, then keep it for several days before judging."]
            if s.area_w_mm and s.area_h_mm:
                nw, nh = s.area_w_mm * (1 + step), s.area_h_mm * (1 + step)
                settings = {"area_mm": [round(nw, 1), round(nh, 1)]}
                act.insert(0, f"Area {s.area_w_mm:g} × {s.area_h_mm:g} mm → {nw:.1f} × {nh:.1f} mm.")
            tips.append(Tip("Tablet area", "You overaim jumps — your area is a bit small", 3, evidence, act, settings))
        elif signed < 0:
            settings = None
            act = [f"Make your tablet area about {step:.0%} smaller (more sensitive), or commit to the full "
                   "movement — undershooting is also common when you aim too carefully.",
                   "Change in one step, then keep it for several days before judging."]
            if s.area_w_mm and s.area_h_mm:
                nw, nh = s.area_w_mm * (1 - step), s.area_h_mm * (1 - step)
                settings = {"area_mm": [round(nw, 1), round(nh, 1)]}
                act.insert(0, f"Area {s.area_w_mm:g} × {s.area_h_mm:g} mm → {nw:.1f} × {nh:.1f} mm.")
            tips.append(Tip("Tablet area", "You underaim jumps — your area is a bit large", 3, evidence, act, settings))
    else:
        if signed:
            word = "lower" if scale > 1 else "raise"
            act = [f"{word.capitalize()} your sensitivity by about {step:.0%}."]
            settings = None
            if s.mouse_dpi:
                new_dpi = s.mouse_dpi / scale
                settings = {"mouse_dpi": int(round(new_dpi / 50) * 50)}
                act.insert(0, f"DPI {s.mouse_dpi} → ~{settings['mouse_dpi']} (or the same change via in-game "
                              f"sensitivity {s.ingame_sens or 1.0:g} → {(s.ingame_sens or 1.0) / scale:.2f}).")
            act.append("Keep Windows pointer acceleration ('Enhance pointer precision') off and raw input on.")
            tips.append(Tip("Mouse sensitivity", f"You {'over' if scale > 1 else 'under'}aim jumps", 3, evidence,
                            act, settings))
    if abs(sx - sy) >= 0.06 and s.device == "tablet":
        act = ["Check that the area's aspect ratio matches your screen (e.g. 16:9 → width/height = 1.78) — "
               "enable 'force proportions'/'lock aspect ratio' in your tablet driver.",
               "If your current ratio is deliberate, correct width and height separately."]
        settings = None
        if s.area_w_mm and s.area_h_mm:
            settings = {"area_mm_separate": [round(s.area_w_mm * sx, 1), round(s.area_h_mm * sy, 1)]}
            act.insert(0, f"Separate correction would be {s.area_w_mm * sx:.1f} × {s.area_h_mm * sy:.1f} mm.")
        tips.append(Tip("Tablet area", "Horizontal and vertical aim are scaled differently", 2,
                        f"Horizontal {_pct(sx - 1)} vs vertical {_pct(sy - 1)}.", act, settings))
    return tips


def _area_rotation_offset_tips(p: Profile, s: Setup):
    r = p.regression
    if not r or r["n"] < 80:
        return []
    tips = []
    rot = r["rotation_deg"]
    if abs(rot) >= 2.5:
        direction = "clockwise" if rot > 0 else "counter-clockwise"
        act = [f"Rotate the tablet area about {abs(rot):.0f}° {direction} in your driver (OpenTabletDriver: "
               "Output → Rotation), or turn the tablet itself slightly to match your arm angle."]
        if s.device == "mouse":
            act = [f"Your movements come out {abs(rot):.0f}° {direction}: check how the mouse sits under your "
                   "hand and the angle of your mousepad/arm."]
        tips.append(Tip("Tablet area" if s.device == "tablet" else "Mouse", f"Your aim is rotated {abs(rot):.1f}° "
                        f"{direction}", 2, f"Fitted on {r['n']} jumps (rotation of your movement vs the real one).",
                        act, {"rotation_deg": round(rot, 1)}))
    ox, oy = r["offset_x"], r["offset_y"]
    if offset_is_sizeable(r):
        horiz, vert = _offset_words(ox, oy)
        evidence = (f"On average your clicks land {abs(ox):.1f} px {horiz} and {abs(oy):.1f} px {vert} of the "
                    f"circle centre (circle radius ≈ {r['radius']:.0f} px).")
        act = []
        settings = None
        mm = mm_per_osu_px(s)
        if s.device == "tablet":
            if mm:
                dx_mm, dy_mm = ox * mm[0], oy * mm[1]
                settings = {"area_shift_mm": [round(dx_mm, 1), round(dy_mm, 1)]}
                act.append(f"Shift the area {abs(dx_mm):.1f} mm {horiz} and {abs(dy_mm):.1f} mm {vert} "
                           "(move it the same way your clicks drift).")
                area = suggest_tablet_area(p, s)
                if area and area["x"] is not None and area["y"] is not None:
                    settings.update(area_x_mm=area["x"], area_y_mm=area["y"])
                    act.insert(0, f"Area position X {s.area_x_mm:g} → {area['x']:g} mm, Y {s.area_y_mm:g} → "
                                  f"{area['y']:g} mm (OpenTabletDriver: X / Y = centre of the area).")
                else:
                    act.append("Enter your area's X / Y in Setup to get the new values.")
            else:
                act.append(f"Shift your tablet area slightly {horiz}/{vert} (the same direction your clicks drift); "
                           "enter your area size in Setup to get millimetres.")
        else:
            act.append("A constant offset with a mouse usually means you look at the edge of the circle — aim for "
                       "the centre number.")
        tips.append(Tip("Tablet area" if s.device == "tablet" else "Aim", "Your clicks are consistently off-centre",
                        1, evidence, act, settings))
    return tips


_QUAD_VEC = {"top-left": (-1, -1), "top-right": (1, -1), "bottom-left": (-1, 1), "bottom-right": (1, 1)}


def _quadrant_tips(p: Profile, s: Setup):
    w = p.worst_quadrant
    if not w:
        return []
    q = w["quadrant"]
    evidence = (f"You miss {_pct(w['miss_rate'])} of notes in the {q} quadrant vs {_pct(w['rest_miss_rate'])} "
                f"elsewhere ({w['relative_risk']:.1f}× more, {w['misses']} misses of {w['objects']} notes).")
    if not w["significant"]:
        return [Tip("Quadrant", f"Most misses happen in the {q} quadrant (not yet a clear pattern)", 1,
                    evidence + " The difference is still small/noisy — check again after more replays.")]
    vx, vy = _QUAD_VEC[q]
    dx, dy = w.get("mean_dx", 0.0) or 0.0, w.get("mean_dy", 0.0) or 0.0
    toward_corner = (dx * vx + dy * vy) / math.sqrt(2)
    actions = []
    if s.device == "tablet":
        far = {"right": "top-left", "left": "top-right"}[s.handedness]
        near = {"right": "bottom-right", "left": "bottom-left"}[s.handedness]
        if toward_corner < -1.0:
            actions.append(f"Your clicks there land {abs(toward_corner):.1f} px short of the notes (towards the "
                           "middle): you don't reach that corner comfortably.")
            actions.append("Do the corner test: rest your hand in your normal position and touch each corner "
                           "of the area — the weak corner must be reachable without stretching or lifting.")
            mm = mm_per_osu_px(s)
            if mm:
                actions.append(f"Shift the area about {abs(dx * mm[0]):.1f} mm {'left' if dx < 0 else 'right'} and "
                               f"{abs(dy * mm[1]):.1f} mm {'up' if dy < 0 else 'down'} so that corner sits closer to "
                               "your hand (or move the tablet itself a little).")
        elif toward_corner > 1.0:
            actions.append(f"You overshoot towards that corner by ~{toward_corner:.1f} px: slow the movement "
                           "down at the end, make sure the tablet doesn't slide (anti-slip pad).")
        if q == far:
            actions.append("This is your far corner: move from the forearm/elbow, not just the wrist, and make sure "
                           "the desk edge or keyboard doesn't stop your arm.")
        elif q == near:
            actions.append("This is the corner nearest your hand: give the wrist room — move the keyboard away, "
                           "don't anchor the wrist on the tablet edge, check the pen doesn't hit the bezel.")
        else:
            actions.append("Check that your arm isn't blocked on that side (desk edge, keyboard, armrest) and that "
                           "the area isn't placed too close to the tablet border.")
    else:
        actions += ["Make sure the mousepad has room in that direction and your arm isn't stopped by the "
                    "desk/keyboard.",
                    "If you lift and re-centre the mouse a lot, consider a slightly higher sensitivity."]
    actions.append(f"Practice: jump maps from the 'Jump aim' playlist; in each retry, watch the {q} jumps and "
                   "commit to the full movement.")
    return [Tip("Quadrant", f"Your weakest quadrant is {q.upper()}", 3, evidence, actions,
                {"weak_quadrant": q, "mean_error_px": [round(dx, 1), round(dy, 1)]})]


def _direction_tips(p: Profile, s: Setup):
    d = p.directions
    d = d[d["objects"] >= 60]
    if len(d) < 4:
        return []
    overall = float((d["miss_rate"] * d["objects"]).sum() / d["objects"].sum())
    worst = d["miss_rate"].idxmax()
    row = d.loc[worst]
    rest = d.drop(index=worst)
    n1, p1 = row["objects"], row["miss_rate"]
    n2 = rest["objects"].sum()
    p2 = float((rest["miss_rate"] * rest["objects"]).sum() / n2) if n2 else 0.0
    pooled = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(max(pooled * (1 - pooled) * (1 / n1 + 1 / max(n2, 1)), 1e-12))
    if overall <= 0 or p1 < 1.4 * overall or (p1 - p2) / se < 2.0 or n1 < 100:
        return []
    along = row["along"]
    extra = ""
    if not _nan(along) and abs(along) >= 0.15:
        extra = (" and you tend to " + ("overshoot" if along > 0 else "undershoot") +
                 f" them ({abs(along):.2f} circle radii)")
    return [Tip("Aim", f"Jumps moving {worst} are your weakest direction", 2,
                f"Miss rate on jumps moving {worst}: {_pct(row['miss_rate'])} vs {_pct(overall)} on average{extra}.",
                ["Pick maps with lots of jumps (Jump aim playlist) and pay attention to that movement.",
                 "Tablet: check your wrist/arm can move freely in that direction."])]


def _distance_angle_tips(p: Profile, s: Setup):
    tips = []
    dist = p.distances
    big = dist.loc[["3-4", "4+"]] if set(["3-4", "4+"]) <= set(dist.index.astype(str)) else None
    if big is not None and big["objects"].sum() >= 60:
        along_big = float((big["along"] * big["objects"]).sum() / big["objects"].sum())
        if along_big <= -0.25:
            tips.append(Tip("Aim", "You undershoot big jumps", 2,
                            f"On jumps of 3+ circle diameters your clicks land {abs(along_big):.2f} radii short.",
                            ["Commit to the whole movement; aim 'through' the circle rather than braking early.",
                             "If it also happens on medium jumps, your area may be slightly too big (see area tip)."]))
        elif along_big >= 0.25:
            tips.append(Tip("Aim", "You overshoot big jumps", 2,
                            f"On jumps of 3+ circle diameters your clicks land {along_big:.2f} radii past the note.",
                            ["Relax your grip; stop the movement on the circle instead of flicking past it.",
                             "If it also happens on medium jumps, your area may be slightly too small."]))
    ang = p.angles
    if len(ang) == 3 and (ang["objects"] >= 60).all():
        sharp, wide = ang["miss_rate"].iloc[0], ang["miss_rate"].iloc[2]
        if sharp >= 1.5 * wide and sharp > 0.03:
            tips.append(Tip("Aim", "Back-and-forth jumps (sharp angles) are hard for you", 1,
                            f"Sharp-angle miss rate {_pct(sharp)} vs wide angles {_pct(wide)}.",
                            ["Practice snap aim: maps with triangles and zig-zag jumps (Jump aim playlist).",
                             "Stop on each note; don't let momentum carry you past it."]))
        elif wide >= 1.5 * sharp and wide > 0.03:
            tips.append(Tip("Aim", "Flowing/linear jumps are hard for you", 1,
                            f"Wide-angle miss rate {_pct(wide)} vs sharp angles {_pct(sharp)}.",
                            ["Practice flow aim (Flow aim playlist): keep the cursor moving smoothly through notes.",
                             "Relax the arm and follow through instead of stopping on every circle."]))
    return tips


def _timing_tips(p: Profile, s: Setup):
    t = p.tapping
    tips = []
    me, n = t.get("mean_error"), p.overview.get("objects", 0)
    if not _nan(me) and abs(me) >= 7 and n >= 300:
        word = "early" if me < 0 else "late"
        tips.append(Tip("Accuracy", f"You hit {abs(me):.0f} ms {word} on average", 2,
                        f"Mean hit error {me:+.1f} ms over {n} notes (UR {t.get('ur', math.nan):.0f}).",
                        ["If this is the same on every map, it is an offset problem: lazer → Settings → Audio → "
                         "'Calibrate using last play'; stable → Options → Audio → Offset wizard.",
                         f"If it is mostly on jumps, you are {'rushing' if me < 0 else 'reacting'} — tap with the "
                         "music, not when the cursor arrives."],
                        {"bias_ms": round(me, 1)}))
    r300 = t.get("three_hundred_rate_single")
    if not _nan(r300) and r300 < 0.8:
        tips.append(Tip("Accuracy", "Your timing spread is wide", 2 if r300 < 0.7 else 1,
                        f"Only {_pct(r300)} 300s on non-stream notes (UR {t.get('ur_single', math.nan):.0f}).",
                        ["Play maps ~1★ below your comfort level and aim for 95%+ accuracy (Accuracy playlist).",
                         "Turn on the hit-error meter and try to keep the marks in the middle.",
                         "Tap with relaxed fingers; tension makes timing jumpy."]))
    if not _nan(t.get("timing_miss_share")) and t["timing_miss_share"] >= 0.3:
        tips.append(Tip("Accuracy", "Many misses come from tapping too early/late", 2,
                        f"{_pct(t['timing_miss_share'])} of misses had the cursor on the note but the tap outside "
                        "the 50 window.", ["Practice rhythm reading: easier maps with mixed rhythms, listen to the "
                                           "song first, use Half Time to learn tricky parts."]))
    return tips


def _stream_tips(p: Profile, s: Setup):
    t = p.tapping
    tips = []
    comfort, limit = t.get("comfort_bpm"), t.get("limit_bpm")
    prof = p.stream_profile
    if prof is not None and not prof.empty and (comfort or limit):
        ev = []
        if comfort:
            ev.append(f"clean up to ~{comfort}-{comfort + 9} BPM")
        if limit:
            row = prof[prof["bpm_bin"] == limit].iloc[0]
            ev.append(f"breaks down from ~{limit} BPM ({_pct(row['miss_rate'])} misses)")
        target = (comfort or (limit - 20 if limit else 150)) + 10
        tips.append(Tip("Tapping", "Your stream speed", 2 if limit else 1,
                        "Bursts/streams (1/4 notes): " + ", ".join(ev) + ".",
                        [f"Train streams around {target}-{target + 10} BPM (the 'Tapping speed' playlist), then step up "
                         "by ~10 BPM when they feel clean.",
                         "Alternate strictly; keep fingers close to the keys; tap from the fingers, not the arm.",
                         "Rate tools: lazer 'Rate adjust'/DT, stable DT/HT for slower/faster practice."],
                        {"stream_comfort_bpm": comfort, "stream_limit_bpm": limit}))
    slope = t.get("slope_ms_per_note")
    fb = getattr(p, "fall_behind", None) or {}
    onset = ""
    if fb.get("start_note"):
        onset = f" Your precision in long streams starts to drop after about {fb['start_note']} notes"
        if fb.get("start_seconds") is not None:
            onset += f" (≈ {fb['start_seconds']:.1f} s at {fb['bpm']:.0f} BPM)"
        onset += "."
    if not _nan(slope) and t.get("n", 0) >= 60:
        if slope >= 0.6:
            tips.append(Tip("Tapping", "You fall behind in long streams", 2,
                            f"Your timing gets {slope:.1f} ms later with every note inside streams "
                            f"(first half {t['early_half_err']:+.0f} ms → second half {t['late_half_err']:+.0f} ms)."
                            + onset,
                            ["Speed/stamina limit: practice slightly slower streams for longer (Stamina playlist).",
                             "Relax — tension makes you slow down; breathe through long streams.",
                             "Keyboard: a lower actuation point helps (see Keyboard tips)."]))
        elif slope <= -0.6:
            tips.append(Tip("Tapping", "You rush streams", 1,
                            f"Your timing gets {abs(slope):.1f} ms earlier with every note inside streams.",
                            ["Listen to the music and count; don't let the fingers run ahead of the song."]))
    return tips


def _key_usage_tips(p: Profile, s: Setup):
    t = p.tapping
    tips = []
    alt = t.get("alternation_in_streams")
    if not _nan(alt) and alt < 0.7:
        tips.append(Tip("Tapping", "You don't alternate keys in streams", 2,
                        f"Only {_pct(alt)} of stream notes were hit with the other key than the previous note.",
                        ["Use both fingers in strict alternation for every burst/stream.",
                         "Start slowly (120-150 BPM streams) until alternation is automatic."]))
    mb = t.get("mouse_button_share")
    if not _nan(mb) and mb > 0.2:
        where = ("lazer: Settings → Input → Mouse → 'Disable mouse buttons during gameplay'"
                 if s.client == "lazer" else "stable: Options → Input → 'Disable mouse buttons in play mode'")
        tips.append(Tip("Tapping", "Many taps come from mouse/pen buttons", 2,
                        f"{_pct(mb)} of presses were M1/M2 (pen tip or mouse clicks).",
                        ["Tap with keyboard keys (e.g. Z/X) — they are faster and don't move the cursor.", where]))
    shares = t.get("key_share") or {}
    kb = {k: v for k, v in shares.items() if k in ("K1", "K2")} or {k: v for k, v in shares.items() if k in ("L", "R")}
    if len(kb) == 2 and max(kb.values()) / max(sum(kb.values()), 1e-9) > 0.75 and t.get("press_count", 0) > 500:
        k, v = max(kb.items(), key=lambda kv: kv[1])
        label = {"L": "the left key", "R": "the right key"}.get(k, k)
        tips.append(Tip("Tapping", "You rely mostly on one key", 1,
                        f"{label} gets {v / sum(kb.values()):.0%} of presses.",
                        ["Alternate on 1/2 rhythms too (or at least in every burst) so both fingers get trained."]))
    ex = t.get("extra_presses_per_100")
    if not _nan(ex) and ex >= 3:
        tips.append(Tip("Tapping", "Extra taps that hit nothing", 1,
                        f"{ex:.1f} presses per 100 notes landed near a note but hit nothing and weren't aimed at "
                        "it (over-tapping, double taps).",
                        ["In bursts, count the notes; don't mash.", "If you use rapid trigger, see the keyboard tip."]))
    return tips


def rt_baseline(speed_bpm: float | None) -> dict:
    """Starting values by stream speed (community ranges; adjust by feel)."""
    if speed_bpm is None or speed_bpm < 170:
        return {"actuation_mm": (0.8, 1.2), "rt_mm": (0.3, 0.4), "note": "beginner-friendly, fewer accidental taps"}
    if speed_bpm < 220:
        return {"actuation_mm": (0.5, 0.9), "rt_mm": (0.2, 0.3), "note": "balanced for 170-220 BPM streams"}
    return {"actuation_mm": (0.3, 0.6), "rt_mm": (0.1, 0.2), "note": "fast streams; watch for double taps"}


SAYO_FIELDS = {  # configurator name -> Setup field
    "Stroke": "sayo_stroke_mm", "Trigger": "sayo_trigger_mm", "Release": "sayo_release_mm",
    "RT Mode": "sayo_rt", "RT Trigger": "sayo_rt_trigger_mm", "RT Release": "sayo_rt_release_mm",
    "Full Stroke": "sayo_full_stroke", "RT Upper Bound": "sayo_rt_upper_mm", "RT Lower Bound": "sayo_rt_lower_mm",
}
SAYO_STEP = 0.05   # the configurator's step


def _mm(v: float) -> float:
    return round(round(v / SAYO_STEP) * SAYO_STEP, 2)


def _tapping_signals(p: Profile) -> dict:
    t = p.tapping
    breaks = sum(p.slider_breaks.values())
    misses = max(sum(p.miss_breakdown.values()), 1)
    return {"speed": t.get("comfort_bpm") or t.get("limit_bpm"), "chatter": t.get("chatter_per_1000", 0) or 0,
            "extra": t.get("extra_presses_per_100", 0) or 0, "overlap": t.get("overlap_in_streams"),
            "slope": t.get("slope_ms_per_note"), "released": round(p.slider_breaks.get("released", 0)),
            "breaks": round(breaks), "no_tap": round(p.miss_breakdown.get("no_tap", 0)), "no_tap_share": p.miss_breakdown.get("no_tap", 0) / misses}


def sayo_settings(p: Profile, s: Setup) -> dict:
    """SayoDevice values to try, from the tapping in the replays: ``now`` (entered or a starting point),
    ``new``, ``reasons`` (what the replays show) and ``checks`` (settings that don't fit together).

    How the settings act: Trigger / Release = fixed press / reset depth; inside the RT zone
    (RT Upper Bound .. RT Lower Bound, or the whole stroke with Full Stroke) the key presses after moving
    down RT Trigger and releases after moving up RT Release, wherever it is. Too small RT values or an
    RT zone that starts above the Trigger point give presses from resting fingers; too large ones make
    fast taps and early releases from wobbling fingers miss."""
    sig = _tapping_signals(p)
    base = rt_baseline(sig["speed"])
    stroke = s.sayo_stroke_mm or 4.0
    trigger = s.sayo_trigger_mm if s.sayo_trigger_mm is not None else _mm(sum(base["actuation_mm"]) / 2)
    rt_mm = _mm(sum(base["rt_mm"]) / 2)
    now = {"Stroke": stroke, "Trigger": trigger,
           "Release": s.sayo_release_mm if s.sayo_release_mm is not None else _mm(trigger - SAYO_STEP),
           "RT Mode": True if s.sayo_rt is None else bool(s.sayo_rt),
           "RT Trigger": s.sayo_rt_trigger_mm if s.sayo_rt_trigger_mm is not None else rt_mm,
           "RT Release": s.sayo_rt_release_mm if s.sayo_rt_release_mm is not None else rt_mm,
           "Full Stroke": bool(s.sayo_full_stroke),
           "RT Upper Bound": s.sayo_rt_upper_mm if s.sayo_rt_upper_mm is not None else trigger,
           "RT Lower Bound": s.sayo_rt_lower_mm if s.sayo_rt_lower_mm is not None else _mm(stroke - SAYO_STEP)}
    entered = any(getattr(s, f) is not None for f in SAYO_FIELDS.values())
    new = dict(now)
    reasons, checks = [], []
    double = sig["chatter"] >= 5 or sig["extra"] >= 3
    if double:
        new["RT Trigger"] = _mm(max(now["RT Trigger"] + SAYO_STEP, 0.15))
        new["RT Release"] = _mm(now["RT Release"] + SAYO_STEP)
        reasons.append(f"double presses ({sig['chatter']:.1f} re-presses within 20 ms per 1000, {sig['extra']:.1f} "
                       "extra taps per 100 notes) → RT Trigger / RT Release less sensitive")
        if now["RT Upper Bound"] < now["Trigger"]:
            new["RT Upper Bound"] = now["Trigger"]
            reasons.append("RT Upper Bound = Trigger, so rapid trigger can't fire from a resting finger above "
                           "your trigger point")
    if sig["breaks"] >= 10 and sig["released"] / sig["breaks"] >= 0.4:
        new["RT Release"] = max(new["RT Release"], _mm(now["RT Release"] + SAYO_STEP))
        reasons.append(f"{sig['released']} of {sig['breaks']} slider breaks were the key letting go mid-slider "
                       "→ RT Release higher, so finger wobble doesn't release")
    if not double and not _nan(sig["slope"]) and sig["slope"] >= 0.6:
        new["RT Trigger"] = _mm(max(now["RT Trigger"] - SAYO_STEP, 0.1))
        reasons.append("you fall behind as streams go on → RT Trigger lower, so presses register sooner")
    if not double and not _nan(sig["overlap"]) and sig["overlap"] >= 0.5:
        new["RT Release"] = _mm(max(min(new["RT Release"], now["RT Release"] - SAYO_STEP), 0.1))
        reasons.append(f"keys overlap on {sig['overlap']:.0%} of stream taps → RT Release lower, so they let go "
                       "sooner")
    if not double and sig["no_tap_share"] >= 0.25:
        new["RT Trigger"] = _mm(max(min(new["RT Trigger"], now["RT Trigger"] - SAYO_STEP), 0.1))
        reasons.append(f"{sig['no_tap']} misses had the cursor on the note but no press → RT Trigger lower")
        if now["RT Lower Bound"] < stroke - 0.1:
            new["RT Lower Bound"] = _mm(stroke - SAYO_STEP)
            reasons.append("RT Lower Bound near the full stroke, so rapid trigger still works when you press "
                           "keys all the way down")
    if not now["RT Mode"] and sig["speed"] and sig["speed"] >= 200 and not double:
        new["RT Mode"] = True
        reasons.append(f"you stream ~{sig['speed']} BPM → RT Mode on lets keys reset without a full lift")
    # settings that don't work together
    if now["Release"] >= now["Trigger"]:
        new["Release"] = _mm(now["Trigger"] - SAYO_STEP)
        checks.append(f"Release ({now['Release']:.2f} mm) must be above Trigger ({now['Trigger']:.2f} mm), "
                      "otherwise the key can't reset cleanly")
    if now["RT Lower Bound"] >= stroke:
        new["RT Lower Bound"] = _mm(stroke - SAYO_STEP)
        checks.append(f"RT Lower Bound ({now['RT Lower Bound']:.2f} mm) at the very bottom of the stroke "
                      f"({stroke:.2f} mm) is a common cause of stuck keys and slider breaks — keep it "
                      f"{SAYO_STEP} mm or more above")
    if now["RT Mode"] and not now["Full Stroke"] and new["RT Upper Bound"] > now["Trigger"]:
        checks.append(f"between Trigger ({now['Trigger']:.2f} mm) and RT Upper Bound "
                      f"({new['RT Upper Bound']:.2f} mm) rapid trigger is off")
    if now["RT Mode"] and not now["Full Stroke"] and new["RT Upper Bound"] < now["Trigger"] and not double:
        checks.append(f"RT Upper Bound ({now['RT Upper Bound']:.2f} mm) is above Trigger ({now['Trigger']:.2f} mm): "
                      "rapid trigger works from there, i.e. before your trigger point. Your replays show no "
                      "presses from resting fingers, so that's fine")
    if not 3.0 <= stroke <= 4.5:
        checks.append(f"Stroke {stroke:.2f} mm: set it to your switch's full travel (4.0 mm for most magnetic "
                      "switches), or the calibration is off")
    return {"now": now, "new": new, "reasons": reasons, "checks": checks, "entered": entered, "signals": sig}


def _sayo_tip(p: Profile, s: Setup) -> list[Tip]:
    r = sayo_settings(p, s)
    sig, now, new = r["signals"], r["now"], r["new"]
    changed = [k for k in SAYO_FIELDS if new[k] != now[k]]

    def show(k, v):
        return ("on" if v else "off") if isinstance(v, bool) else f"{v:.2f} mm"
    act = []
    if not r["entered"]:
        base = ", ".join(f"{k} {show(k, v)}" for k, v in new.items())
        act.append(f"Starting point for ~{sig['speed'] or '?'} BPM streams: {base}. Enter your current values in "
                   "Setup to get changes based on your replays.")
    else:
        act += [f"{k}: {show(k, now[k])} → {show(k, new[k])}" for k in changed]
    if r["reasons"]:
        act.append("Why: " + "; ".join(r["reasons"]) + ".")
    act += [c[0].upper() + c[1:] + "." for c in r["checks"]]
    act.append(f"Change one value at a time, in {SAYO_STEP:g} mm steps, and play the same map a few times to "
               "compare.")
    fits = r["entered"] and not changed
    title = "Your SayoDevice settings fit your tapping" if fits else "SayoDevice settings for your tapping"
    evidence = (f"Stream comfort speed ≈ {sig['speed'] or 'unknown'} BPM; double presses {sig['chatter']:.1f} per "
                f"1000 presses; extra taps {sig['extra']:.1f} per 100 notes; {sig['released']} of {sig['breaks']} "
                "slider breaks were key releases.")
    severity = 2 if r["reasons"] or (r["checks"] and changed) else 1
    return [Tip("Keys / SayoDevice", title, severity, evidence, act, dict(new))]


def _keyboard_tips(p: Profile, s: Setup):
    if s.keyboard == "sayo":
        return _sayo_tip(p, s)
    t = p.tapping
    speed = t.get("comfort_bpm") or t.get("limit_bpm")
    chatter = t.get("chatter_per_1000", 0) or 0
    extra = t.get("extra_presses_per_100", 0) or 0
    overlap = t.get("overlap_in_streams")
    slope = t.get("slope_ms_per_note")
    released = round(p.slider_breaks.get("released", 0))
    breaks = round(sum(p.slider_breaks.values()))
    no_tap = round(p.miss_breakdown.get("no_tap", 0))
    misses = max(sum(p.miss_breakdown.values()), 1)
    if s.keyboard == "rapid_trigger":
        base = rt_baseline(speed)
        act = [f"Starting point: actuation {base['actuation_mm'][0]}-{base['actuation_mm'][1]} mm, rapid-trigger "
               f"sensitivity (press & release) {base['rt_mm'][0]}-{base['rt_mm'][1]} mm, continuous rapid trigger "
               f"on ({base['note']})."]
        act_mm = s.actuation_mm or sum(base["actuation_mm"]) / 2
        rt_mm = s.rt_release_mm or s.rt_press_mm or sum(base["rt_mm"]) / 2
        new_act, new_rt = act_mm, rt_mm
        reasons = []
        if chatter >= 5 or extra >= 3:
            new_rt = min(rt_mm + 0.1, 0.6)
            new_act = min(act_mm + 0.2, 2.0)
            reasons.append(f"double taps/chatter detected ({chatter:.1f} re-presses <20 ms per 1000, "
                           f"{extra:.1f} extra taps per 100 notes) → less sensitive")
        if breaks >= 10 and released / breaks >= 0.4 and chatter >= 2:
            new_rt = max(new_rt, rt_mm + 0.1)
            reasons.append(f"{released} of {breaks} slider breaks were key releases mid-slider → release "
                           "sensitivity a bit higher so finger wobble doesn't release")
        if not _nan(slope) and slope >= 0.6 and not reasons:
            new_act = max(act_mm - 0.2, 0.3)
            reasons.append("you fall behind in streams → a shallower actuation point")
        if not _nan(overlap) and overlap >= 0.5 and chatter < 5:
            new_rt = max(rt_mm - 0.05, 0.1)
            reasons.append(f"keys overlap on {overlap:.0%} of stream taps → let them reset sooner (lower RT value)")
        if no_tap / misses >= 0.25 and not (chatter >= 5):
            new_act = max(min(new_act, act_mm - 0.1), 0.3)
            reasons.append(f"{no_tap} misses had no tap at all → keys may not register; lower actuation")
        settings = {"actuation_mm": round(new_act, 2), "rt_sensitivity_mm": round(new_rt, 2),
                    "continuous_rt": True}
        if reasons:
            act.append("Based on your replays: " + "; ".join(reasons) + f". Try actuation {new_act:.1f} mm, "
                       f"RT {new_rt:.2f} mm.")
        act.append("Change one value at a time by 0.1 mm and play the same map a few times to compare.")
        return [Tip("Keyboard / Rapid trigger", "Rapid-trigger settings for your tapping", 2 if reasons else 1,
                    f"Stream comfort speed ≈ {speed or 'unknown'} BPM; chatter {chatter:.1f}/1000 presses; "
                    f"extra taps {extra:.1f}/100 notes.", act, settings)]
    tips = []
    if speed and speed >= 200 and not _nan(slope) and slope >= 0.6:
        tips.append(Tip("Keyboard / Rapid trigger", "Your keyboard may be holding your streams back", 1,
                        f"You stream ~{speed} BPM and fall behind as streams go on.",
                        ["A hall-effect keyboard/keypad with rapid trigger (or lighter linear switches) resets "
                         "keys faster.", "Set the Setup → keyboard type to get rapid-trigger values."]))
    if chatter >= 8:
        tips.append(Tip("Keyboard / Rapid trigger", "Possible key chatter", 1,
                        f"{chatter:.1f} same-key re-presses within 20 ms per 1000 presses.",
                        ["Mechanical switches can chatter; try different keys or clean/replace the switch."]))
    return tips


def _slider_tips(p: Profile, s: Setup):
    sl = p.sliders
    if sl.get("sliders", 0) < 30:
        return []
    tips = []
    br = sl.get("break_rate", 0)
    if br >= 0.04:
        reasons = p.slider_breaks
        top = max(reasons.items(), key=lambda kv: kv[1])[0] if reasons else "follow"
        acts = {
            "released": ["You let go of the key before the slider ended — hold until the end, even on short "
                         "and repeating sliders."],
            "follow": ["Your cursor left the follow circle — slow down on sliders, follow the ball, watch for "
                       "reverse arrows and fast sliders."],
            "key_swap": ["You switched keys inside the slider. osu! keeps tracking only with the key you hit the "
                         "head with (lazer: until the other key is let go; stable: releasing that key can break it). "
                         "Keep holding the first key until the end."],
        }[top]
        tips.append(Tip("Sliders", "Slider breaks cost you combo", 2 if br >= 0.08 else 1,
                        f"{_pct(br)} of sliders broke after a good head ({', '.join(f'{k} {v:.0f}' for k, v in reasons.items())}).",
                        acts + ["Practice: 'Slider control' playlist (slider-heavy maps)."]))
    em = sl.get("end_miss_rate")
    if not _nan(em) and em >= 0.08:
        tips.append(Tip("Sliders", "You often miss slider ends (100s)", 1, f"{_pct(em)} of slider ends missed.",
                        ["Keep the cursor and key on the slider until it disappears; don't leave early for the "
                         "next note."]))
    return tips


def _reading_tips(p: Profile, s: Setup):
    r = p.reading
    tips = []
    ls = r.get("lost_share")
    if not _nan(ls) and ls >= 0.25 and sum(p.miss_breakdown.values()) >= 20:
        tips.append(Tip("Reading", "You lose track of notes", 2,
                        f"{_pct(ls)} of misses had no tap and the cursor far away from the note.",
                        ["Play slightly lower AR, then raise it step by step (Reading playlist).",
                         "Learn hard sections with Half Time; look ahead to the next notes, not at your cursor."]))
    d, sp = r.get("dense_ratio"), r.get("sparse_ratio")
    if not _nan(d) and not _nan(sp) and sp > 0 and d >= 1.3 * sp and (r.get("dense_misses") or 0) >= 20:
        tips.append(Tip("Reading", "Dense sections (many notes on screen) are hard for you", 1,
                        f"With ≥{r.get('dense_threshold', 0):.0f} notes on screen you miss {d:.1f}× as often as their "
                        f"difficulty predicts, vs {sp:.1f}× elsewhere.",
                        ["Reading practice: maps with overlapping patterns at your level; take it slow with HT "
                         "first."]))
    hi, lo, mid = r.get("high_ar_ratio"), r.get("low_ar_ratio"), r.get("mid_ar_ratio")
    if not _nan(hi) and not _nan(mid) and mid > 0 and hi >= 1.3 * mid and (r.get("high_ar_misses") or 0) >= 20:
        tips.append(Tip("Reading", "High approach rate (AR 9.5+) hurts you", 1,
                        f"At AR ≥ 9.5 you miss {hi:.1f}× as often as the difficulty predicts, vs {mid:.1f}× at "
                        f"AR 7-9.5 ({_pct(r.get('high_ar_miss_rate'))} vs {_pct(r.get('mid_ar_miss_rate'))} raw).",
                        ["Practice AR 9-9.5 maps until comfortable before going higher (DT raises AR too)."]))
    if not _nan(lo) and not _nan(mid) and mid > 0 and lo >= 1.3 * mid and (r.get("low_ar_misses") or 0) >= 20:
        tips.append(Tip("Reading", "Low approach rate (AR ≤ 7) confuses you", 1,
                        f"At AR ≤ 7 you miss {lo:.1f}× as often as the difficulty predicts, vs {mid:.1f}× at AR 7-9.5.",
                        ["Play some low-AR maps on purpose; focus on rhythm instead of waiting for the approach "
                         "circle."]))
    return tips


def _consistency_tips(p: Profile, s: Setup):
    c = p.consistency
    tips = []
    r = c.get("miss_after_miss_ratio")
    if not _nan(r) and r >= 3.0:
        tips.append(Tip("Consistency", "Misses come in chains", 2,
                        f"Right after a miss you miss {r:.1f}× more often than the difficulty of the next notes "
                        "explains (typical: about 2×).",
                        ["After a mistake, keep tapping the rhythm and re-find the pattern — don't freeze or mash.",
                         "Practice full combos on easier maps to build calm, then step up."]))
    es, eo = c.get("end_miss_share"), c.get("end_object_share")
    if not _nan(es) and not _nan(eo) and eo > 0 and es >= 1.6 * eo and sum(p.miss_breakdown.values()) >= 20:
        tips.append(Tip("Consistency", "You miss more near the end of maps", 1,
                        f"{_pct(es)} of misses happen in the last 20% of maps.",
                        ["Stamina/nerves: play longer maps (Stamina playlist) and practice finishing songs.",
                         "Keep breathing and keep the grip loose in the last part."]))
    return tips


def practice_plan(p: Profile) -> list[str]:
    """A simple daily routine built around the weakest skills."""
    weak = [SKILL_LABELS[k] for k in p.weaknesses] or ["your weakest skill"]
    comfort = p.levels.get("comfort_stars")
    lvl = f"{comfort:.1f}★" if comfort and not math.isnan(comfort) else "your comfort level"
    return [
        f"Warm-up (10 min): 2-3 maps about 1★ below {lvl}, aiming for full combos.",
        f"Focus block (20-30 min): the '{weak[0]}' playlist from Skill Development — repeat each map until the "
        "target in the playlist note is met.",
        f"Push (10 min): one or two maps slightly above {lvl}.",
        "Cool-down: replay a favourite map for fun.",
        "Re-run the analysis after ~20 new replays and compare the scores.",
    ]
