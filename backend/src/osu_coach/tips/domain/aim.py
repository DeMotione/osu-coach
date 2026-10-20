"""Tips about aim: why misses happen, quadrants, directions, distance and angle."""

from __future__ import annotations

import math

import pandas as pd

from osu_coach.profile.domain import Profile
from osu_coach.settings.domain import Setup
from osu_coach.tips.domain.common import Tip, _nan, _pct
from osu_coach.tips.domain.tablet import mm_per_osu_px


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
        "aim": (
            "Most misses are aim misses",
            "You clicked in time but outside the circle, on jumps or single notes at normal speed.",
        ),
        "speed_aim": (
            "Most misses are speed-aim misses",
            "You tapped in time, but in streams, bursts or very fast jumps the cursor couldn't keep up with the tempo.",
        ),
        "timing": ("Most misses are timing misses", "Cursor was on the note but you tapped too early/late."),
        "tapping": (
            "Most misses are missing taps",
            "Cursor was on the note but no key press arrived in time (one tap for two notes, finger lag in streams).",
        ),
        "reading": (
            "Most misses are 'lost' notes",
            "No tap and the cursor was far away — you didn't see or didn't understand the note in time.",
        ),
        "notelock": (
            "Many misses are follow-up misses (notelock)",
            "You tapped the next note while the previous one was still active; osu! ignores that tap.",
        ),
    }[top]
    actions = {
        "aim": _aim_miss_actions(p),
        "speed_aim": _speed_aim_actions(p),
        "timing": [
            "Play below your comfort level and aim for 300s, not just hitting notes.",
            "Tap to the music, not to the approach circle; enable the hit-error meter.",
        ],
        "tapping": [
            "Practice bursts/streams at a lower BPM with strict alternation.",
            "Count notes in bursts (3, 5, 7 ...) — misses often come from tapping one note too few.",
        ],
        "reading": [
            "Play maps with a slightly lower AR and work your way up.",
            "Look one or two notes ahead instead of at your cursor.",
        ],
        "notelock": [
            "These are usually caused by the miss right before them: fix the first miss and the chain disappears.",
            "Don't spam-tap to 'catch up' after a mistake; re-find the rhythm.",
        ],
    }[top]
    names = {"speed_aim": "speed-aim"}
    breakdown = ", ".join(
        f"{names.get(k, k)} {v / total:.0%}" for k, v in sorted(groups.items(), key=lambda kv: -kv[1]) if v >= 0.5
    )
    weighted = (getattr(p, "levels", {}) or {}).get("weighted")
    over = (
        f"{total:.0f} misses (weighted by how close each map is to your level)" if weighted else f"{total:.0f} misses"
    )
    return [
        Tip(
            "Overview",
            f"{text[0]} ({share:.0%})",
            3 if share >= 0.4 else 2,
            f"{text[1]} Miss causes over {over}: {breakdown}.",
            actions,
        )
    ]


def _aim_miss_where(p: Profile) -> dict[str, int]:
    """Aim misses by kind of pattern: streams (incl. bursts), flow (spaced streams), jumps, single notes."""
    O = getattr(p, "objects", None)
    if O is None or O.empty or "miss_reason" not in O or "pattern" not in O:
        return {}
    cause = O["miss_cause"] if "miss_cause" in O else O["miss_reason"]  # "aim" without speed-aim if split
    m = O[O["played"].astype(bool) & ~O["head_hit"].astype(bool) & (cause == "aim")]
    w = m["w"] if "w" in m else pd.Series(1.0, index=m.index)
    flow = m["spaced_stream"].astype(bool) if "spaced_stream" in m else False
    streams = m["pattern"].isin(["burst", "stream"])
    return {
        "streams": float(w[streams & ~flow].sum()),
        "flow": float(w[streams & flow].sum()),
        "jumps": float(w[m["pattern"].isin(["jump", "spaced"])].sum()),
        "single notes": float(w[m["pattern"] == "single"].sum()),
    }


def _aim_miss_actions(p: Profile) -> list[str]:
    jump_advice = [
        "Focus practice on aim first (the 'Jump aim' playlist in Goals & Training).",
        "Your tablet area / sensitivity is checked from your jumps (Aim page → Aim calibration); a "
        "separate tip appears only if it is off — otherwise it's precision, not calibration.",
    ]
    where = _aim_miss_where(p)
    total = sum(where.values())
    if total < 30:
        return jump_advice
    streams = where["streams"] + where["flow"]
    split = (
        f"streams and bursts {streams / total:.0%}, jumps {where['jumps'] / total:.0%}, "
        f"single notes {where['single notes'] / total:.0%}"
    )
    if streams / total >= 0.4 and streams >= where["jumps"]:
        playlist = "Flow aim (spaced streams)" if where["flow"] > where["streams"] else "Tapping speed (bursts/streams)"
        return [
            f"Most of them are in streams and bursts ({split}): you keep tapping but the cursor falls "
            "behind or cuts corners.",
            f"Slow streams down (HT, or the '{playlist}' playlist in Goals & Training) until the cursor stays "
            "on every note, then raise the speed step by step.",
            "Move with the stream's shape — a steady motion through the notes, not small jumps between them.",
        ]
    return [f"Where they happen: {split}."] + jump_advice


def _speed_aim_actions(p: Profile) -> list[str]:
    """What to do about aim misses in streams / very fast jumps, with the split against the difficulty."""
    acts = []
    sp = (getattr(p, "aim", {}) or {}).get("split", {})
    a, f = sp.get("aim"), sp.get("speed_aim")
    if a and f and a["expected"] > 0 and f["expected"] > 0:
        ra, rf = a["all_misses"] / a["expected"], f["all_misses"] / f["expected"]
        verdict = (
            " — the fast patterns are the real gap."
            if rf > 1.15 * ra
            else " — about the same, so it's mostly that you play many fast patterns."
            if rf >= 0.87 * ra
            else " — fast patterns are relatively fine for you."
        )
        acts.append(
            f"Against what the difficulty of the notes predicts: fast patterns {rf:.1f}× the expected "
            f"misses, normal-speed jumps and notes {ra:.1f}×" + verdict
        )
    flow = ((getattr(p, "skills", {}) or {}).get("flow_aim") or {}).get("score")
    acts += [
        ("Your flow-aim score is low. " if flow is not None and flow < 45 else "")
        + "Practise spaced streams below the tempo where they break (the 'Flow aim (spaced streams)' playlist "
        "in Goals & Training, or the same map with HT / a lower rate), then raise the speed by ~10 BPM.",
        "Move with the stream's shape — a steady motion through the notes, not small jumps between them; "
        "keep the arm loose so the cursor can follow the tempo.",
    ]
    return acts


_QUAD_VEC = {"top-left": (-1, -1), "top-right": (1, -1), "bottom-left": (-1, 1), "bottom-right": (1, 1)}


def _quadrant_tips(p: Profile, s: Setup):
    w = p.worst_quadrant
    if not w:
        return []
    q = w["quadrant"]
    evidence = (
        f"You miss {_pct(w['miss_rate'])} of notes in the {q} quadrant vs {_pct(w['rest_miss_rate'])} "
        f"elsewhere ({w['relative_risk']:.1f}× more, {w['misses']} misses of {w['objects']} notes)."
    )
    if not w["significant"]:
        return [
            Tip(
                "Quadrant",
                f"Most misses happen in the {q} quadrant (not yet a clear pattern)",
                1,
                evidence + " The difference is still small/noisy — check again after more replays.",
            )
        ]
    vx, vy = _QUAD_VEC[q]
    dx, dy = w.get("mean_dx", 0.0) or 0.0, w.get("mean_dy", 0.0) or 0.0
    toward_corner = (dx * vx + dy * vy) / math.sqrt(2)
    actions = []
    if s.device == "tablet":
        far = {"right": "top-left", "left": "top-right"}[s.handedness]
        near = {"right": "bottom-right", "left": "bottom-left"}[s.handedness]
        if toward_corner < -1.0:
            actions.append(
                f"Your clicks there land {abs(toward_corner):.1f} px short of the notes (towards the "
                "middle): you don't reach that corner comfortably."
            )
            actions.append(
                "Do the corner test: rest your hand in your normal position and touch each corner "
                "of the area — the weak corner must be reachable without stretching or lifting."
            )
            mm = mm_per_osu_px(s)
            if mm:
                actions.append(
                    f"Shift the area about {abs(dx * mm[0]):.1f} mm {'left' if dx < 0 else 'right'} and "
                    f"{abs(dy * mm[1]):.1f} mm {'up' if dy < 0 else 'down'} so that corner sits closer to "
                    "your hand (or move the tablet itself a little)."
                )
        elif toward_corner > 1.0:
            actions.append(
                f"You overshoot towards that corner by ~{toward_corner:.1f} px: slow the movement "
                "down at the end, make sure the tablet doesn't slide (anti-slip pad)."
            )
        if q == far:
            actions.append(
                "This is your far corner: move from the forearm/elbow, not just the wrist, and make sure "
                "the desk edge or keyboard doesn't stop your arm."
            )
        elif q == near:
            actions.append(
                "This is the corner nearest your hand: give the wrist room — move the keyboard away, "
                "don't anchor the wrist on the tablet edge, check the pen doesn't hit the bezel."
            )
        else:
            actions.append(
                "Check that your arm isn't blocked on that side (desk edge, keyboard, armrest) and that "
                "the area isn't placed too close to the tablet border."
            )
    else:
        actions += [
            "Make sure the mousepad has room in that direction and your arm isn't stopped by the desk/keyboard.",
            "If you lift and re-centre the mouse a lot, consider a slightly higher sensitivity.",
        ]
    actions.append(
        f"Practice: jump maps from the 'Jump aim' playlist; in each retry, watch the {q} jumps and "
        "commit to the full movement."
    )
    return [
        Tip(
            "Quadrant",
            f"Your weakest quadrant is {q.upper()}",
            3,
            evidence,
            actions,
            {"weak_quadrant": q, "mean_error_px": [round(dx, 1), round(dy, 1)]},
        )
    ]


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
        extra = (
            " and you tend to "
            + ("overshoot" if along > 0 else "undershoot")
            + f" them ({abs(along):.2f} circle radii)"
        )
    return [
        Tip(
            "Aim",
            f"Jumps moving {worst} are your weakest direction",
            2,
            f"Miss rate on jumps moving {worst}: {_pct(row['miss_rate'])} vs {_pct(overall)} on average{extra}.",
            [
                "Pick maps with lots of jumps (Jump aim playlist) and pay attention to that movement.",
                "Tablet: check your wrist/arm can move freely in that direction.",
            ],
        )
    ]


def _distance_angle_tips(p: Profile, s: Setup):
    tips = []
    dist = p.distances
    big = dist.loc[["3-4", "4+"]] if set(["3-4", "4+"]) <= set(dist.index.astype(str)) else None
    if big is not None and big["objects"].sum() >= 60:
        along_big = float((big["along"] * big["objects"]).sum() / big["objects"].sum())
        if along_big <= -0.25:
            tips.append(
                Tip(
                    "Aim",
                    "You undershoot big jumps",
                    2,
                    f"On jumps of 3+ circle diameters your clicks land {abs(along_big):.2f} radii short.",
                    [
                        "Commit to the whole movement; aim 'through' the circle rather than braking early.",
                        "If it also happens on medium jumps, your area may be slightly too big (see area tip).",
                    ],
                )
            )
        elif along_big >= 0.25:
            tips.append(
                Tip(
                    "Aim",
                    "You overshoot big jumps",
                    2,
                    f"On jumps of 3+ circle diameters your clicks land {along_big:.2f} radii past the note.",
                    [
                        "Relax your grip; stop the movement on the circle instead of flicking past it.",
                        "If it also happens on medium jumps, your area may be slightly too small.",
                    ],
                )
            )
    ang = p.angles
    if len(ang) == 3 and (ang["objects"] >= 60).all():
        sharp, wide = ang["miss_rate"].iloc[0], ang["miss_rate"].iloc[2]
        if sharp >= 1.5 * wide and sharp > 0.03:
            tips.append(
                Tip(
                    "Aim",
                    "Back-and-forth jumps (sharp angles) are hard for you",
                    1,
                    f"Sharp-angle miss rate {_pct(sharp)} vs wide angles {_pct(wide)}.",
                    [
                        "Practice snap aim: maps with triangles and zig-zag jumps (Jump aim playlist).",
                        "Stop on each note; don't let momentum carry you past it.",
                    ],
                )
            )
        elif wide >= 1.5 * sharp and wide > 0.03:
            tips.append(
                Tip(
                    "Aim",
                    "Flowing/linear jumps are hard for you",
                    1,
                    f"Wide-angle miss rate {_pct(wide)} vs sharp angles {_pct(sharp)}.",
                    [
                        "Practice flow aim (Flow aim playlist): keep the cursor moving smoothly through notes.",
                        "Relax the arm and follow through instead of stopping on every circle.",
                    ],
                )
            )
    return tips
