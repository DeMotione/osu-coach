"""What the pages say: skill names and help, miss causes, the wording of the domain's messages, and why a map is
suggested."""

from __future__ import annotations

import math
from dataclasses import replace

from osu_coach.domain.maps.skillset import GoalMaps, Recommendation
from osu_coach.domain.maps.suggestions import Targets, finite_or
from osu_coach.domain.player.messages import Message

# Skill names: short and plain, the words players use. The playlists use the same ones (``suggestions.SKILL_INFO``).
SKILL_LABELS = {
    "aim": "Jumps",
    "flow_aim": "Spaced streams",
    "speed": "Tapping speed",
    "stamina": "Stamina",
    "accuracy": "Accuracy",
    "sliders": "Sliders",
    "reading": "Reading",
    "consistency": "Consistency",
}
# One line under each name: what the skill is, in a player's words.
SKILL_SUMMARIES = {
    "aim": "Hitting notes that are far apart.",
    "flow_aim": "Aiming while you stream: streams and bursts whose notes are spread out.",
    "speed": "Tapping fast streams and bursts cleanly.",
    "stamina": "Keeping up the tapping to the end of long streams.",
    "accuracy": "Hitting single notes on time, for 300s.",
    "sliders": "Following sliders to the end without breaking them.",
    "reading": "Seeing notes in time: high AR, busy parts, HD and FL.",
    "consistency": "Playing well on every map, not just once.",
}

# What each skill measures under Star Levels (Star-Scale IRT); the Comfort Score texts below measure something else.
SKILL_HELP_IRT = {
    "aim": "Jumps: how rarely you miss jumps and spread-out notes with the cursor, given how far and how fast each "
    "jump is.",
    "flow_aim": "Spaced streams: how rarely you miss the notes of streams that are a circle width or more apart, "
    "given their spacing and speed.",
    "speed": "Tapping speed: how rarely you miss stream and burst notes (or hit them for a 50), given their BPM. "
    "Cursor misses on them count for spaced streams instead.",
    "stamina": "Stamina: the same, for notes deep into long streams (after the 16th note, or 30 seconds into "
    "nonstop tapping). If tapping speed holds up there and stamina doesn't, your fingers are getting tired.",
    "accuracy": "Accuracy: how often your hits on single notes (not streams) are 300s, given how tight the 300 window "
    "is (OD, with speed mods) and how hard the pattern is.",
    "sliders": "Sliders: how rarely you break sliders that move (longer than a circle width), given how fast they are "
    "for their map, their shape and their speed changes.",
    "reading": "Reading: how rarely you miss notes, given how quickly they appear (higher AR = less time to see them) "
    "and how many are on screen at once (HD and FL count too).",
}

# Shown when the cursor is on a skill (Overview): what the skill is, how its Comfort Score is worked out
# (``ratings.py``) and what raises it. Keep in step with ``ratings.ratings``.
BEST_PER_SETUP = (
    "Each map and mod setup counts once (your best play on it); your best counts fully, each next one 5% less"
)
COMFORT_50 = "50 = what maps at your comfort level ask for (assumed from ranked maps, not compared with other players)"
SKILL_HELP = {
    "aim": (
        "Jumps: notes two or more circle widths apart (not streams) that you move the cursor to. Looks at how fast "
        "the cursor has to travel between them and how many of them you land.",
        "For each map you passed: the cursor speed of its 30 fastest jumps, lowered by the share you missed. "
        f"{BEST_PER_SETUP}. {COMFORT_50}; twice the speed = +25. Needs 3 different map/mod setups.",
        "Play jump maps a little above your comfort level until you can keep the combo. Don't change your tablet "
        "area or sensitivity while you do.",
    ),
    "flow_aim": (
        "Spaced streams: streams and bursts (3+ notes in a row) whose notes are about a circle width or more apart, "
        "so the cursor has to keep moving while you tap. Looks at how fast the cursor moves and how many of those "
        "notes you hit.",
        "For each map you passed: the cursor speed of its 50 fastest spaced-stream notes, a little higher the more "
        f"of them the map has, lowered by the share you missed. {BEST_PER_SETUP}. {COMFORT_50}; twice the speed = "
        "+25.",
        "Play spaced-stream maps at a BPM you can tap cleanly, then raise the BPM step by step. Move your arm in one "
        "smooth motion instead of stopping on every note.",
    ),
    "speed": (
        "Tapping speed: the fastest streams and bursts (3+ notes) you tap cleanly: no finger misses (no tap, too "
        "early or late, notelock) and at least 80% 300s. Cursor misses don't count here; they belong to spaced "
        "streams.",
        f"For each map: your 3rd fastest clean run. {BEST_PER_SETUP}. 50 = the stream speed maps at your comfort "
        "level ask for (assumed); 10% faster ≈ +10.",
        "Play stream and burst maps 10–20 BPM above the speed you tap cleanly, in short sets with relaxed fingers. "
        "The Tapping page shows your clean stream speed.",
    ),
    "stamina": (
        "Stamina: how long you can keep tapping fast before your fingers give in and you start missing taps. It's "
        "about keeping up, not about accuracy.",
        "The fastest tempo you kept up for 10 s, 30 s, 1, 2 and 5 minutes while pressing at least 90% of the notes "
        f"(extra taps are fine). {BEST_PER_SETUP}. Each length is compared with the tempo maps at your comfort level "
        "ask for over that long (assumed); 10% faster ≈ +10. The score is the average of the lengths measured on "
        "3+ setups.",
        "Play stream-heavy maps a little longer than usual and keep tapping to the end, even when your accuracy "
        "drops. Make the streams longer first, then faster.",
    ),
    "accuracy": (
        "Accuracy: how many of your hits on single notes (not streams) are 300s. Fewer 100s and 50s = better.",
        "Your share of hits that weren't 300s, compared with what is expected at your comfort level and the maps' "
        "OD. At 4.5★ and OD 8, 90% 300s scores 50 and 80% scores 20; from 5.5★ up, the reference and slope stay "
        "where they are at 5.5★. Needs 60+ hit single notes.",
        "Play maps you can full combo and go for 300s, not for the combo. If your hits are mostly early or late "
        "(see the Tapping page), fix your offset first.",
    ),
    "sliders": (
        "Sliders: how hard the sliders are that you follow to the end without breaking them: their speed, length, "
        "shape, speed changes and how soon the next note comes.",
        "For each map: your 30 hardest sliders (whose head you hit), their average difficulty times (the share you "
        f"held)³. {BEST_PER_SETUP}. {COMFORT_50}; twice as hard = +25.",
        "Play maps with long, curved and fast sliders and follow every one to its end; mix slow and fast sliders. "
        "Lots of short sliders don't raise it.",
    ),
    "reading": (
        "Reading: playing busy maps (many circles per second) at a lower AR than usual for their difficulty, or with "
        "HD or FL, while keeping your accuracy, and hitting BPM changes on time.",
        "For each map you passed: 2^((usual AR − AR) ÷ 3 × circles per second ÷ 5), up to ×1.5 for BPM changes "
        f"hit as 300s, × accuracy⁸. {BEST_PER_SETUP}. 50 = the usual AR for the map at 95% accuracy; twice as "
        "hard = +25.",
        "Play busy maps a little below the AR you're used to (or with HD) and keep your accuracy up. On maps with "
        "BPM changes, hit the first notes after each change on time.",
    ),
    "consistency": (
        "Consistency: how steady your combo and accuracy are from map to map. Uses your maps from one star below a "
        "star rating up to it (at 6.2★: maps of 5.2–6.2★ with mods); harder maps never count. Shown at your comfort "
        "level and at each star rating you compare with.",
        "Every play gets a map score from how much of the combo you hold (10% of the max combo = 0, 30% = 0.48, "
        "50% = 0.70, a full combo = 1: holding big parts counts, not only full combos) and your accuracy (88% = 0, "
        "94% = 1). The better of the two counts 70%, the other 30%, and a play that keeps less than about 20% of "
        "the combo fades to 0. Each map counts once (its plays averaged), a map a star easier half as much as one "
        "at the star rating. Consistency = your usual map score minus half of how much it swings between maps. "
        "Needs 8 different maps; the more maps, the more reliable.",
        "Play many different maps of that star rating instead of retrying one. Keep long stretches of combo and "
        "your accuracy up on every one, rather than chasing one great result.",
    ),
}
MISS_LABELS = {
    "aim": "aim — tapped in time but outside the circle (jumps and single notes)",
    "speed_aim": "speed-aim — tapped in time, but the cursor couldn't keep up with a stream, burst or very fast jump",
    "early": "too early — cursor on the note, tap before the hit window",
    "late": "too late — cursor on the note, tap after the hit window",
    "no_tap": "no tap — cursor was on the note but no key was pressed",
    "lost": "lost — no tap and the cursor far away (didn't see / read it)",
    "notelock": "notelock — tap ignored because the previous note was still active",
}

# what each skill is measured on, the unit of that measure, and the maps that test it
_TESTS = {
    "aim": ("the cursor speed of your hardest jumps", "{:.1f} circle widths/s", "jumps", "bigger or faster jumps"),
    "flow_aim": (
        "the cursor speed of your fastest spaced streams",
        "{:.1f} circle widths/s",
        "spaced streams",
        "wider or faster spaced streams",
    ),
    "speed": ("your fastest bursts and streams", "{:.0f} BPM", "bursts or streams", "faster bursts and streams"),
    "sliders": ("the difficulty of your hardest sliders", "{:.1f}", "sliders", "long, fast or curvy sliders"),
    "reading": ("", "", "", ""),  # never untested; too few maps: see _needs
}


_IRT_TESTS = {
    "aim": "jumps",
    "flow_aim": "spaced streams",
    "speed": "streams",
    "stamina": "long streams",
    "accuracy": "tight hit windows (high OD)",
    "sliders": "sliders",
    "reading": "fast-appearing notes (high AR)",
}


def _maps(n: int) -> str:
    return f"{n} more different map{'s' if n > 1 else ''}"


def message(m: Message | None) -> str | None:
    """The text of a rating's reason or needs."""
    if m is None:
        return None
    v = m.values
    match m.code:
        case "comfort_unknown":
            return "Your comfort level isn't known yet"
        case "not_enough_data":
            return "Not enough data"
        case "insufficient_challenge":
            return "Your maps haven't pushed this skill enough yet"
        case "need_maps":
            return f"Needs {v['maps']} different map/mod setups that test it"
        case "best_per_setup":
            return "Your best play on each map/mod setup; each next one counts 5% less"
        case "stamina_mean":
            return "Average over the stream lengths measured; lengths your maps haven't tested stay unknown"
        case "accuracy_gate":
            return (
                f"Needs {v['heads']} hit single notes; DT plays only count above {v['dt_accuracy']:.0%} accuracy "
                "(evidence gate)"
            )
        case "accuracy_measured":
            return "Share of 300s on your hit single notes, compared at each map's OD"
        case "consistency_held":
            return f"Combo and accuracy held across {v['maps']} different maps of {v['low']:.1f}–{v['high']:.1f}★"
        case "harder_maps":
            what, unit, _, harder = _TESTS[v["skill"]]
            return (
                f"You held almost everything you played, but {what} so far ({unit.format(v['tested'])}) is below what "
                f"your comfort level expects ({unit.format(v['expected'])}): play maps with {harder} to find your limit."
            )
        case "more_maps":
            if v["skill"] == "reading":
                return f"Pass {_maps(v['more'])} to get a score."
            return f"Play {_maps(v['more'])} with {_TESTS[v['skill']][2]} to get a score."
        case "stamina_harder":
            return (
                f"You kept up with almost every stretch you played, but your densest {v['seconds']}-second stretch so "
                f"far ({v['tested']:.0f} BPM of 1/4 notes) is below what your comfort level expects "
                f"({v['expected']:.0f} BPM): play maps with longer streams or dense 1/4 sections."
            )
        case "stamina_maps":
            return f"Play {v['maps']} different maps with streams or dense 1/4 sections of at least 10 seconds."
        case "irt_measured":
            return "Worked out from every note you hit or missed and how hard it was"
        case "irt_provisional":
            return "A rough estimate so far: more plays near your limit will sharpen it"
        case "irt_untested":
            maps = f" (up to {v['maps']:.1f}★)" if v.get("maps") else ""
            return f"You almost never fail {_IRT_TESTS[v['skill']]} on the maps you played{maps}"
        case "irt_not_enough":
            return "Not enough notes near your limit to measure it yet"
        case "irt_failed":
            return "The calculation didn't settle on one answer, so no number is shown"
        case "irt_play_harder":
            return (
                f"Play maps a bit above your level (around {v['level']:.1f}★) with plenty of "
                f"{_IRT_TESTS[v['skill']]} to find your limit."
            )
        case "irt_play_at":
            return f"Play more maps around your level ({v['level']:.1f}★) with {_IRT_TESTS[v['skill']]} to measure it."
        case "comfort_first":
            return (
                "First your comfort level: pass 3 different maps (with at most 2 misses per 100 notes) and analyse "
                f"your replays. Then play {v['maps']} different maps up to a star below it."
            )
        case "consistency_maps":
            which = f"your {v['stars']:.1f}★ comfort level" if v["comfort"] else f"{v['stars']:g}★"
            return (
                f"Play {_maps(v['more'])} between {v['low']:.1f}★ and {v['high']:.1f}★ (with mods; the closer to "
                f"{v['high']:.1f}★, the more it counts), then analyse your replays again: consistency at {which} is "
                f"scored from {v['maps']} different maps up to a star below it ({v['so_far']} so far), and the more "
                "you play, the more reliable it gets. Harder maps don't count. Passed and failed plays both count; "
                "playing a map you already have again doesn't add one."
            )
    raise ValueError(f"unknown message {m.code}")


# ------------------------------------------------------------------ maps
def why(r, skill: str, t: Targets) -> str:
    g = lambda k, d=math.nan: finite_or(r.get(k), d)  # noqa: E731
    if skill == "aim":
        return f"{g('jump_share') + g('spaced_share'):.0%} jumps, ~{g('jump_dist', 0):.1f} circles apart"
    if skill == "flow_aim":
        return f"{g('spaced_stream_share'):.0%} spaced streams"
    if skill in ("speed", "stamina"):
        bpm = g("stream_bpm")
        bpm = g("burst_bpm") if math.isnan(bpm) else bpm
        if skill == "speed":
            bpm = g("speed_bpm", max(g("stream_bpm", 0), g("burst_bpm", 0)))
        run = int(g("max_run", 0))
        kind = "streams" if run >= 9 else "bursts"
        if skill == "stamina":
            long_runs = int(g("long_runs", 0))
            extra = f", {long_runs} streams of 16+ notes" if long_runs else f", longest {run} notes"
            return f"{kind} at ~{bpm:.0f} BPM (1/4){extra}"
        return f"{kind} at ~{bpm:.0f} BPM (1/4), longest {run} notes"
    if skill == "accuracy":
        return f"OD {g('od'):g}, {g('circle_share'):.0%} circles"
    if skill == "sliders":
        tricky = ", tricky slider paths" if g("slider_factor", 1) < 0.97 else ""
        return f"{g('slider_share'):.0%} sliders, {g('reverse_share'):.0%} with repeats{tricky}"
    if skill == "reading":
        return f"AR {g('ar'):g}, up to {g('density_p90', 0):.0f} notes on screen"
    if skill == "consistency":
        return f"evenly hard from start to end ({g('evenness', 0):.0%})"
    if skill == "quadrant" and t.quadrant:
        return f"{g('q_' + t.quadrant.replace('-', '_')):.0%} of its jumps land {t.quadrant}"
    return f"{g('stars'):.2f}★, popular"


def explain(ranked: Recommendation, skill: str, targets: Targets | None) -> Recommendation:
    """The recommenders' result with each map's ``why`` filled in (empty without targets)."""

    def explained(goal: GoalMaps) -> GoalMaps:
        maps = tuple(replace(m, why=why(m.map, skill, targets) if targets is not None else "") for m in goal.maps)
        return replace(goal, maps=maps)

    return replace(ranked, goals={name: explained(goal) for name, goal in ranked.goals.items()})
