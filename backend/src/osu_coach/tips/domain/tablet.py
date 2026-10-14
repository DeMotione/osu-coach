"""Tablet area: millimetres per osu!pixel, the area to try, and the aim calibration tips."""

from __future__ import annotations

import math

from osu_coach.profile.domain import Profile
from osu_coach.settings.domain import Setup
from osu_coach.tips.domain.common import PLAYFIELD_SCREEN_FRACTION, Tip, _pct


def mm_per_osu_px(setup: Setup) -> tuple[float, float] | None:
    """Tablet millimetres per osu!pixel (full-screen mapping assumed)."""
    if not setup.area_w_mm or not setup.area_h_mm:
        return None
    screen_px_per_osu_px = setup.screen_h_px * PLAYFIELD_SCREEN_FRACTION / 384.0
    return (
        setup.area_w_mm / setup.screen_w_px * screen_px_per_osu_px,
        setup.area_h_mm / setup.screen_h_px * screen_px_per_osu_px,
    )


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
        why.append(
            f"you {'over' if step > 0 else 'under'}aim jumps by {abs(step):.0%} → area "
            f"{'larger' if step > 0 else 'smaller'} (same centre)"
        )
    ox, oy = r["offset_x"], r["offset_y"]
    horiz, vert = _offset_words(ox, oy)
    if offset_is_sizeable(r):
        mm = mm_per_osu_px(s)
        dx, dy = ox * mm[0], oy * mm[1]
        nx = None if x is None else round(x + dx, 1)
        ny = None if y is None else round(y + dy, 1)
        why.append(
            f"your clicks land {abs(ox):.1f} px {horiz} and {abs(oy):.1f} px {vert} of the centre → move "
            f"the area {abs(dx):.1f} mm {horiz} and {abs(dy):.1f} mm {vert}"
        )
    else:
        why.append(
            f"your jumps land centred (constant offset {abs(ox):.1f} px {horiz}, {abs(oy):.1f} px {vert} — "
            "'Constant offset' on the Aim page; too little to matter) → keep X / Y"
        )
    return {
        "w": nw,
        "h": nh,
        "x": nx,
        "y": ny,
        "now": {"w": w, "h": h, "x": x, "y": y},
        "changed": (nw, nh, nx, ny) != (w, h, x, y),
        "why": why,
    }


def aim_calibration(p: Profile, s: Setup) -> dict | None:
    """What the aim calibration (Aim page) means for the setup: ``scale`` (average), ``step`` (area /
    sensitivity change as a fraction, 0 = keep), ``now`` / ``try`` (text, None if unknown), ``lines``."""
    r = p.regression
    if not r:
        return None
    scale = (r["scale_x"] + r["scale_y"]) / 2
    step = _scale_step(r) or 0.0
    word = "overaim" if scale > 1 else "underaim"
    lines = [
        f"Aim calibration (Aim page), fitted on {r['n']:,} jumps: you move {_pct(r['scale_x'] - 1)} "
        f"horizontally and {_pct(r['scale_y'] - 1)} vertically compared with the real jump "
        f"(+ = too far), rotation {r['rotation_deg']:+.1f}°, constant offset "
        f"{math.hypot(r['offset_x'], r['offset_y']):.1f} px."
    ]
    now = new = None
    if s.device == "tablet":
        if s.area_w_mm and s.area_h_mm:
            now = f"{s.area_w_mm:g} × {s.area_h_mm:g} mm"
            new = f"{s.area_w_mm * (1 + step):.1f} × {s.area_h_mm * (1 + step):.1f} mm" if step else now
        if step:
            lines.append(
                f"You {word} jumps by {abs(scale - 1):.0%} → make the tablet area {abs(step):.0%} "
                f"{'larger (less sensitive)' if step > 0 else 'smaller (more sensitive)'}."
            )
        else:
            lines.append("Your movement matches the jumps within ±4% → keep your tablet area size.")
        if not (s.area_w_mm and s.area_h_mm):
            lines.append("Enter your area width / height in Your setup to get millimetres.")
    else:
        sens = s.ingame_sens or 1.0
        if s.mouse_dpi:
            now = f"{s.mouse_dpi} DPI × {sens:g}"
            new = (
                (
                    f"{int(round(s.mouse_dpi / scale / 50) * 50)} DPI × {sens:g} (or {s.mouse_dpi} DPI × "
                    f"{sens / scale:.2f})"
                )
                if step
                else now
            )
        else:
            now = f"sensitivity {sens:g}"
            new = f"sensitivity {sens / scale:.2f}" if step else now
        if step:
            lines.append(
                f"You {word} jumps by {abs(scale - 1):.0%} → {'lower' if scale > 1 else 'raise'} your "
                f"sensitivity by about {abs(scale - 1):.0%}."
            )
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
        title = (
            f"Aim calibration: {'larger' if c['step'] > 0 else 'smaller'} tablet area"
            if c["device"] == "tablet"
            else f"Aim calibration: {'lower' if c['step'] > 0 else 'higher'} sensitivity"
        )
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
    evidence = (
        f"Measured on {r['n']} jumps: you move {_pct(sx - 1)} horizontally and {_pct(sy - 1)} vertically "
        f"compared with the real distance (+ = too far / overaim, - = not far enough / underaim)."
    )
    signed = _scale_step(r) or 0.0
    step = abs(signed)
    if s.device == "tablet":
        if signed > 0:
            settings = None
            act = [
                f"Make your tablet area about {step:.0%} larger (less sensitive).",
                "Change in one step, then keep it for several days before judging.",
            ]
            if s.area_w_mm and s.area_h_mm:
                nw, nh = s.area_w_mm * (1 + step), s.area_h_mm * (1 + step)
                settings = {"area_mm": [round(nw, 1), round(nh, 1)]}
                act.insert(0, f"Area {s.area_w_mm:g} × {s.area_h_mm:g} mm → {nw:.1f} × {nh:.1f} mm.")
            tips.append(Tip("Tablet area", "You overaim jumps — your area is a bit small", 3, evidence, act, settings))
        elif signed < 0:
            settings = None
            act = [
                f"Make your tablet area about {step:.0%} smaller (more sensitive), or commit to the full "
                "movement — undershooting is also common when you aim too carefully.",
                "Change in one step, then keep it for several days before judging.",
            ]
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
                act.insert(
                    0,
                    f"DPI {s.mouse_dpi} → ~{settings['mouse_dpi']} (or the same change via in-game "
                    f"sensitivity {s.ingame_sens or 1.0:g} → {(s.ingame_sens or 1.0) / scale:.2f}).",
                )
            act.append("Keep Windows pointer acceleration ('Enhance pointer precision') off and raw input on.")
            tips.append(
                Tip("Mouse sensitivity", f"You {'over' if scale > 1 else 'under'}aim jumps", 3, evidence, act, settings)
            )
    if abs(sx - sy) >= 0.06 and s.device == "tablet":
        act = [
            "Check that the area's aspect ratio matches your screen (e.g. 16:9 → width/height = 1.78) — "
            "enable 'force proportions'/'lock aspect ratio' in your tablet driver.",
            "If your current ratio is deliberate, correct width and height separately.",
        ]
        settings = None
        if s.area_w_mm and s.area_h_mm:
            settings = {"area_mm_separate": [round(s.area_w_mm * sx, 1), round(s.area_h_mm * sy, 1)]}
            act.insert(0, f"Separate correction would be {s.area_w_mm * sx:.1f} × {s.area_h_mm * sy:.1f} mm.")
        tips.append(
            Tip(
                "Tablet area",
                "Horizontal and vertical aim are scaled differently",
                2,
                f"Horizontal {_pct(sx - 1)} vs vertical {_pct(sy - 1)}.",
                act,
                settings,
            )
        )
    return tips


def _area_rotation_offset_tips(p: Profile, s: Setup):
    r = p.regression
    if not r or r["n"] < 80:
        return []
    tips = []
    rot = r["rotation_deg"]
    if abs(rot) >= 2.5:
        direction = "clockwise" if rot > 0 else "counter-clockwise"
        act = [
            f"Rotate the tablet area about {abs(rot):.0f}° {direction} in your driver (OpenTabletDriver: "
            "Output → Rotation), or turn the tablet itself slightly to match your arm angle."
        ]
        if s.device == "mouse":
            act = [
                f"Your movements come out {abs(rot):.0f}° {direction}: check how the mouse sits under your "
                "hand and the angle of your mousepad/arm."
            ]
        tips.append(
            Tip(
                "Tablet area" if s.device == "tablet" else "Mouse",
                f"Your aim is rotated {abs(rot):.1f}° {direction}",
                2,
                f"Fitted on {r['n']} jumps (rotation of your movement vs the real one).",
                act,
                {"rotation_deg": round(rot, 1)},
            )
        )
    ox, oy = r["offset_x"], r["offset_y"]
    if offset_is_sizeable(r):
        horiz, vert = _offset_words(ox, oy)
        evidence = (
            f"On average your clicks land {abs(ox):.1f} px {horiz} and {abs(oy):.1f} px {vert} of the "
            f"circle centre (circle radius ≈ {r['radius']:.0f} px)."
        )
        act = []
        settings = None
        mm = mm_per_osu_px(s)
        if s.device == "tablet":
            if mm:
                dx_mm, dy_mm = ox * mm[0], oy * mm[1]
                settings = {"area_shift_mm": [round(dx_mm, 1), round(dy_mm, 1)]}
                act.append(
                    f"Shift the area {abs(dx_mm):.1f} mm {horiz} and {abs(dy_mm):.1f} mm {vert} "
                    "(move it the same way your clicks drift)."
                )
                area = suggest_tablet_area(p, s)
                if area and area["x"] is not None and area["y"] is not None:
                    settings.update(area_x_mm=area["x"], area_y_mm=area["y"])
                    act.insert(
                        0,
                        f"Area position X {s.area_x_mm:g} → {area['x']:g} mm, Y {s.area_y_mm:g} → "
                        f"{area['y']:g} mm (OpenTabletDriver: X / Y = centre of the area).",
                    )
                else:
                    act.append("Enter your area's X / Y in Setup to get the new values.")
            else:
                act.append(
                    f"Shift your tablet area slightly {horiz}/{vert} (the same direction your clicks drift); "
                    "enter your area size in Setup to get millimetres."
                )
        else:
            act.append(
                "A constant offset with a mouse usually means you look at the edge of the circle — aim for "
                "the centre number."
            )
        tips.append(
            Tip(
                "Tablet area" if s.device == "tablet" else "Aim",
                "Your clicks are consistently off-centre",
                1,
                evidence,
                act,
                settings,
            )
        )
    return tips
