"""Tips about tapping: timing, streams and key use."""

from __future__ import annotations

from osu_coach.common import frames
from osu_coach.domain.player import Profile
from osu_coach.domain.player.setup import Setup
from osu_coach.features.tips.rules.common import Tip, is_nan, pct
from osu_coach.features.tips.rules.setup import SAME_BIAS, timing_bias


def timing_tips(p: Profile, s: Setup):
    t = p.tapping
    tips = []
    me, n = t.mean_error, p.overview.objects
    bias = timing_bias(p)
    offset = bias is not None and bias["same"] >= SAME_BIAS  # the same on every map: Setup Tips → Audio offset
    if not is_nan(me) and abs(me) >= 7 and n >= 300 and not offset:
        word = "early" if me < 0 else "late"
        tips.append(
            Tip(
                "Accuracy",
                f"You hit {abs(me):.0f} ms {word} on average",
                2,
                f"Mean hit error {me:+.1f} ms over {n} notes (UR {t.ur:.0f}), not the same on every "
                "map, so it's your timing rather than the offset.",
                [
                    f"You are {'rushing' if me < 0 else 'reacting'}: tap with the music, not when the cursor arrives.",
                    "Turn on the hit-error meter and keep the marks in the middle.",
                ],
                {"bias_ms": round(me, 1)},
            )
        )
    r300 = t.three_hundred_rate_single
    if not is_nan(r300) and r300 < 0.8:
        tips.append(
            Tip(
                "Accuracy",
                "Your timing spread is wide",
                2 if r300 < 0.7 else 1,
                f"Only {pct(r300)} 300s on non-stream notes (UR {t.ur_single:.0f}).",
                [
                    "Play maps ~1★ below your comfort level and aim for 95%+ accuracy (Accuracy playlist).",
                    "Turn on the hit-error meter and try to keep the marks in the middle.",
                    "Tap with relaxed fingers; tension makes timing jumpy.",
                ],
            )
        )
    if not is_nan(t.timing_miss_share) and t.timing_miss_share >= 0.3:
        tips.append(
            Tip(
                "Accuracy",
                "Many misses come from tapping too early/late",
                2,
                f"{pct(t.timing_miss_share)} of misses had the cursor on the note but the tap outside the 50 window.",
                [
                    "Practice rhythm reading: easier maps with mixed rhythms, listen to the "
                    "song first, use Half Time to learn tricky parts."
                ],
            )
        )
    return tips


def stream_tips(p: Profile, s: Setup):
    t = p.tapping
    tips = []
    comfort, limit = t.comfort_bpm, t.limit_bpm
    prof = frames.stream_profile(p)
    if prof is not None and not prof.empty and (comfort or limit):
        ev = []
        if comfort:
            ev.append(f"clean up to ~{comfort}-{comfort + 9} BPM")
        if limit:
            row = prof[prof["bpm_bin"] == limit].iloc[0]
            ev.append(f"breaks down from ~{limit} BPM ({pct(row['miss_rate'])} misses)")
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
    slope = t.slope_ms_per_note
    fb = frames.fall_behind(p)
    onset = ""
    if fb.get("start_note"):
        onset = f" Your precision in long streams starts to drop after about {fb['start_note']} notes"
        if fb.get("start_seconds") is not None:
            onset += f" (≈ {fb['start_seconds']:.1f} s at {fb['bpm']:.0f} BPM)"
        onset += "."
    if not is_nan(slope) and t.n >= 60:
        if slope >= 0.6:
            tips.append(
                Tip(
                    "Tapping",
                    "You fall behind in long streams",
                    2,
                    f"Your timing gets {slope:.1f} ms later with every note inside streams "
                    f"(first half {t.early_half_err:+.0f} ms → second half {t.late_half_err:+.0f} ms)." + onset,
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


def key_usage_tips(p: Profile, s: Setup):
    t = p.tapping
    tips = []
    alt = t.alternation_in_streams
    if not is_nan(alt) and alt < 0.7:
        tips.append(
            Tip(
                "Tapping",
                "You don't alternate keys in streams",
                2,
                f"Only {pct(alt)} of stream notes were hit with the other key than the previous note.",
                [
                    "Use both fingers in strict alternation for every burst/stream.",
                    "Start slowly (120-150 BPM streams) until alternation is automatic.",
                ],
            )
        )
    mb = t.mouse_button_share
    if not is_nan(mb) and mb > 0.2:
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
                f"{pct(mb)} of presses were M1/M2 (pen tip or mouse clicks).",
                ["Tap with keyboard keys (e.g. Z/X) — they are faster and don't move the cursor.", where],
            )
        )
    shares = t.key_share or {}
    kb = {k: v for k, v in shares.items() if k in ("K1", "K2")} or {k: v for k, v in shares.items() if k in ("L", "R")}
    if len(kb) == 2 and max(kb.values()) / max(sum(kb.values()), 1e-9) > 0.75 and (t.press_count or 0) > 500:
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
    ex = t.extra_presses_per_100
    if not is_nan(ex) and ex >= 3:
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
