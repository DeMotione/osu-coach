"""Keyboard tips: rapid trigger values and SayoDevice settings."""
from __future__ import annotations

from osu_coach.profile.domain import Profile
from osu_coach.settings.domain import Setup
from osu_coach.tips.domain.common import Tip, _nan


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
    # SayoDevice: RT Trigger must not be larger than RT Release (the device rejects / misbehaves otherwise)
    if now["RT Trigger"] > now["RT Release"]:
        checks.append(f"RT Trigger ({now['RT Trigger']:.2f} mm) must not be larger than RT Release "
                      f"({now['RT Release']:.2f} mm)")
    if new["RT Trigger"] > new["RT Release"]:
        if new["RT Release"] < now["RT Release"]:
            # Release was lowered on purpose (keys overlap): bring Trigger down with it
            new["RT Trigger"] = new["RT Release"]
            reasons.append(f"RT Trigger lowered to {new['RT Trigger']:.2f} mm too, since it can't be larger than "
                           "RT Release")
        else:
            new["RT Release"] = new["RT Trigger"]
            reasons.append(f"RT Release raised to {new['RT Release']:.2f} mm too, since RT Trigger can't be "
                           "larger than it")
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
