"""Tips about sliders, reading and consistency."""

from __future__ import annotations

from osu_coach.profile.domain import Profile
from osu_coach.settings.domain import Setup
from osu_coach.tips.domain.common import Tip, _nan, _pct


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
            "released": [
                "You let go of the key before the slider ended — hold until the end, even on short "
                "and repeating sliders."
            ],
            "follow": [
                "Your cursor left the follow circle — slow down on sliders, follow the ball, watch for "
                "reverse arrows and fast sliders."
            ],
            "key_swap": [
                "You switched keys inside the slider. osu! keeps tracking only with the key you hit the "
                "head with (lazer: until the other key is let go; stable: releasing that key can break it). "
                "Keep holding the first key until the end."
            ],
        }[top]
        tips.append(
            Tip(
                "Sliders",
                "Slider breaks cost you combo",
                2 if br >= 0.08 else 1,
                f"{_pct(br)} of sliders broke after a good head ({', '.join(f'{k} {v:.0f}' for k, v in reasons.items())}).",
                acts + ["Practice: 'Slider control' playlist (slider-heavy maps)."],
            )
        )
    em = sl.get("end_miss_rate")
    if not _nan(em) and em >= 0.08:
        tips.append(
            Tip(
                "Sliders",
                "You often miss slider ends (100s)",
                1,
                f"{_pct(em)} of slider ends missed.",
                ["Keep the cursor and key on the slider until it disappears; don't leave early for the next note."],
            )
        )
    return tips


def _reading_tips(p: Profile, s: Setup):
    r = p.reading
    tips = []
    ls = r.get("lost_share")
    if not _nan(ls) and ls >= 0.25 and sum(p.miss_breakdown.values()) >= 20:
        tips.append(
            Tip(
                "Reading",
                "You lose track of notes",
                2,
                f"{_pct(ls)} of misses had no tap and the cursor far away from the note.",
                [
                    "Play slightly lower AR, then raise it step by step (Reading playlist).",
                    "Learn hard sections with Half Time; look ahead to the next notes, not at your cursor.",
                ],
            )
        )
    d, sp = r.get("dense_ratio"), r.get("sparse_ratio")
    if not _nan(d) and not _nan(sp) and sp > 0 and d >= 1.3 * sp and (r.get("dense_misses") or 0) >= 20:
        tips.append(
            Tip(
                "Reading",
                "Dense sections (many notes on screen) are hard for you",
                1,
                f"With ≥{r.get('dense_threshold', 0):.0f} notes on screen you miss {d:.1f}× as often as their "
                f"difficulty predicts, vs {sp:.1f}× elsewhere.",
                ["Reading practice: maps with overlapping patterns at your level; take it slow with HT first."],
            )
        )
    hi, lo, mid = r.get("high_ar_ratio"), r.get("low_ar_ratio"), r.get("mid_ar_ratio")
    if not _nan(hi) and not _nan(mid) and mid > 0 and hi >= 1.3 * mid and (r.get("high_ar_misses") or 0) >= 20:
        tips.append(
            Tip(
                "Reading",
                "High approach rate (AR 9.5+) hurts you",
                1,
                f"At AR ≥ 9.5 you miss {hi:.1f}× as often as the difficulty predicts, vs {mid:.1f}× at "
                f"AR 7-9.5 ({_pct(r.get('high_ar_miss_rate'))} vs {_pct(r.get('mid_ar_miss_rate'))} raw).",
                ["Practice AR 9-9.5 maps until comfortable before going higher (DT raises AR too)."],
            )
        )
    if not _nan(lo) and not _nan(mid) and mid > 0 and lo >= 1.3 * mid and (r.get("low_ar_misses") or 0) >= 20:
        tips.append(
            Tip(
                "Reading",
                "Low approach rate (AR ≤ 7) confuses you",
                1,
                f"At AR ≤ 7 you miss {lo:.1f}× as often as the difficulty predicts, vs {mid:.1f}× at AR 7-9.5.",
                ["Play some low-AR maps on purpose; focus on rhythm instead of waiting for the approach circle."],
            )
        )
    return tips


def _consistency_tips(p: Profile, s: Setup):
    c = p.consistency
    tips = []
    r = c.get("miss_after_miss_ratio")
    if not _nan(r) and r >= 3.0:
        tips.append(
            Tip(
                "Consistency",
                "Misses come in chains",
                2,
                f"Right after a miss you miss {r:.1f}× more often than the difficulty of the next notes "
                "explains (typical: about 2×).",
                [
                    "After a mistake, keep tapping the rhythm and re-find the pattern — don't freeze or mash.",
                    "Practice full combos on easier maps to build calm, then step up.",
                ],
            )
        )
    es, eo = c.get("end_miss_share"), c.get("end_object_share")
    if not _nan(es) and not _nan(eo) and eo > 0 and es >= 1.6 * eo and sum(p.miss_breakdown.values()) >= 20:
        tips.append(
            Tip(
                "Consistency",
                "You miss more near the end of maps",
                1,
                f"{_pct(es)} of misses happen in the last 20% of maps.",
                [
                    "Stamina/nerves: play longer maps (Stamina playlist) and practice finishing songs.",
                    "Keep breathing and keep the grip loose in the last part.",
                ],
            )
        )
    return tips
