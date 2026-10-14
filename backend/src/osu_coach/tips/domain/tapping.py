"""Tips about tapping: timing, streams and key use."""

from __future__ import annotations

import math

from osu_coach.profile.domain import Profile
from osu_coach.settings.domain import Setup
from osu_coach.tips.domain.common import Tip, _nan, _pct


def _timing_tips(p: Profile, s: Setup):
    t = p.tapping
    tips = []
    me, n = t.get("mean_error"), p.overview.get("objects", 0)
    if not _nan(me) and abs(me) >= 7 and n >= 300:
        word = "early" if me < 0 else "late"
        tips.append(
            Tip(
                "Accuracy",
                f"You hit {abs(me):.0f} ms {word} on average",
                2,
                f"Mean hit error {me:+.1f} ms over {n} notes (UR {t.get('ur', math.nan):.0f}).",
                [
                    "If this is the same on every map, it is an offset problem: lazer → Settings → Audio → "
                    "'Calibrate using last play'; stable → Options → Audio → Offset wizard.",
                    f"If it is mostly on jumps, you are {'rushing' if me < 0 else 'reacting'} — tap with the "
                    "music, not when the cursor arrives.",
                ],
                {"bias_ms": round(me, 1)},
            )
        )
    r300 = t.get("three_hundred_rate_single")
    if not _nan(r300) and r300 < 0.8:
        tips.append(
            Tip(
                "Accuracy",
                "Your timing spread is wide",
                2 if r300 < 0.7 else 1,
                f"Only {_pct(r300)} 300s on non-stream notes (UR {t.get('ur_single', math.nan):.0f}).",
                [
                    "Play maps ~1★ below your comfort level and aim for 95%+ accuracy (Accuracy playlist).",
                    "Turn on the hit-error meter and try to keep the marks in the middle.",
                    "Tap with relaxed fingers; tension makes timing jumpy.",
                ],
            )
        )
    if not _nan(t.get("timing_miss_share")) and t["timing_miss_share"] >= 0.3:
        tips.append(
            Tip(
                "Accuracy",
                "Many misses come from tapping too early/late",
                2,
                f"{_pct(t['timing_miss_share'])} of misses had the cursor on the note but the tap outside "
                "the 50 window.",
                [
                    "Practice rhythm reading: easier maps with mixed rhythms, listen to the "
                    "song first, use Half Time to learn tricky parts."
                ],
            )
        )
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
        tips.append(
            Tip(
                "Tapping",
                "Your stream speed",
                2 if limit else 1,
                "Bursts/streams (1/4 notes): " + ", ".join(ev) + ".",
                [
                    f"Train streams around {target}-{target + 10} BPM (the 'Tapping speed' playlist), then step up "
                    "by ~10 BPM when they feel clean.",
                    "Alternate strictly; keep fingers close to the keys; tap from the fingers, not the arm.",
                    "Rate tools: lazer 'Rate adjust'/DT, stable DT/HT for slower/faster practice.",
                ],
                {"stream_comfort_bpm": comfort, "stream_limit_bpm": limit},
            )
        )
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
            tips.append(
                Tip(
                    "Tapping",
                    "You fall behind in long streams",
                    2,
                    f"Your timing gets {slope:.1f} ms later with every note inside streams "
                    f"(first half {t['early_half_err']:+.0f} ms → second half {t['late_half_err']:+.0f} ms)." + onset,
                    [
                        "Speed/stamina limit: practice slightly slower streams for longer (Stamina playlist).",
                        "Relax — tension makes you slow down; breathe through long streams.",
                        "Keyboard: a lower actuation point helps (see Keyboard tips).",
                    ],
                )
            )
        elif slope <= -0.6:
            tips.append(
                Tip(
                    "Tapping",
                    "You rush streams",
                    1,
                    f"Your timing gets {abs(slope):.1f} ms earlier with every note inside streams.",
                    ["Listen to the music and count; don't let the fingers run ahead of the song."],
                )
            )
    return tips


def _key_usage_tips(p: Profile, s: Setup):
    t = p.tapping
    tips = []
    alt = t.get("alternation_in_streams")
    if not _nan(alt) and alt < 0.7:
        tips.append(
            Tip(
                "Tapping",
                "You don't alternate keys in streams",
                2,
                f"Only {_pct(alt)} of stream notes were hit with the other key than the previous note.",
                [
                    "Use both fingers in strict alternation for every burst/stream.",
                    "Start slowly (120-150 BPM streams) until alternation is automatic.",
                ],
            )
        )
    mb = t.get("mouse_button_share")
    if not _nan(mb) and mb > 0.2:
        where = (
            "lazer: Settings → Input → Mouse → 'Disable mouse buttons during gameplay'"
            if s.client == "lazer"
            else "stable: Options → Input → 'Disable mouse buttons in play mode'"
        )
        tips.append(
            Tip(
                "Tapping",
                "Many taps come from mouse/pen buttons",
                2,
                f"{_pct(mb)} of presses were M1/M2 (pen tip or mouse clicks).",
                ["Tap with keyboard keys (e.g. Z/X) — they are faster and don't move the cursor.", where],
            )
        )
    shares = t.get("key_share") or {}
    kb = {k: v for k, v in shares.items() if k in ("K1", "K2")} or {k: v for k, v in shares.items() if k in ("L", "R")}
    if len(kb) == 2 and max(kb.values()) / max(sum(kb.values()), 1e-9) > 0.75 and t.get("press_count", 0) > 500:
        k, v = max(kb.items(), key=lambda kv: kv[1])
        label = {"L": "the left key", "R": "the right key"}.get(k, k)
        tips.append(
            Tip(
                "Tapping",
                "You rely mostly on one key",
                1,
                f"{label} gets {v / sum(kb.values()):.0%} of presses.",
                ["Alternate on 1/2 rhythms too (or at least in every burst) so both fingers get trained."],
            )
        )
    ex = t.get("extra_presses_per_100")
    if not _nan(ex) and ex >= 3:
        tips.append(
            Tip(
                "Tapping",
                "Extra taps that hit nothing",
                1,
                f"{ex:.1f} presses per 100 notes landed near a note but hit nothing and weren't aimed at "
                "it (over-tapping, double taps).",
                ["In bursts, count the notes; don't mash.", "If you use rapid trigger, see the keyboard tip."],
            )
        )
    return tips
