"""What the pages say: skill names and help, miss causes, the wording of the domain's messages, and why a map is
suggested."""

from __future__ import annotations

import math
from dataclasses import replace

from osu_coach.domain.maps.skillset import GoalMaps, Recommendation
from osu_coach.domain.maps.suggestions import Targets, finite_or
from osu_coach.domain.player.messages import Message

SKILL_LABELS = {
    "aim": "Jump aim",
    "flow_aim": "Flow aim (spaced streams)",
    "speed": "Tapping speed (bursts/streams)",
    "stamina": "Stamina",
    "accuracy": "Accuracy (timing)",
    "sliders": "Slider control",
    "reading": "Reading (AR / BPM changes)",
    "consistency": "Consistency",
}
# Shown when the cursor is on a skill bar (Overview): what the skill measures, how the rating is worked out
# (``ratings.py``) and what raises it. Keep in step with ``ratings.ratings``.
BEST_PER_SETUP = "each map/mod setup counts once (its best play), best first and each next one 5% less"
SKILL_HELP = {
    "aim": (
        "Jump aim: how fast the cursor has to move between jumps and spaced notes (2+ circle widths apart, "
        "not streams), distance ÷ time, and whether you land those jumps.",
        "Score: per passed play the average cursor speed of its 30 fastest jumps × (share of them you hit)^0.8; "
        f"{BEST_PER_SETUP}; 50 = typical for your comfort level, +25 per doubling. Needs 3 different map/mod setups.",
        "Jump maps slightly above your comfort level until you can hold the combo; keep your tablet area / "
        "sensitivity fixed while you do.",
    ),
    "flow_aim": (
        "Spaced streams: bursts and streams (3+ notes in a row) whose notes are about a circle width or "
        "more apart, so the cursor has to keep moving while you tap: spacing × BPM × how much "
        "of the map flows, and whether you hit those notes.",
        "Score: per passed play the cursor speed of its 50 fastest spaced-stream notes × (notes ÷ 100)^0.25 × "
        f"(share of them you hit)^0.8; {BEST_PER_SETUP}; 50 = typical for your comfort level, +25 per doubling.",
        "Spaced-stream maps at a BPM you can tap cleanly, then raise the BPM step by step. Move the arm "
        "in one smooth motion instead of stopping on every note.",
    ),
    "speed": (
        "Tapping speed: how fast you tap bursts and streams (3+ notes) cleanly: no finger miss (no tap, "
        "too early or late, notelock; cursor misses don't count) and 80%+ of the notes as 300s.",
        f"Score: per play the 3rd fastest clean run; {BEST_PER_SETUP}; 50 = the stream speed typical for your "
        "comfort level, 10% faster ≈ +10.",
        "Stream and burst maps 10–20 BPM above the speed you tap cleanly, in short sets with relaxed "
        "fingers. See the Tapping page for your clean stream speed.",
    ),
    "stamina": (
        "Stamina: for how long you keep a high tempo before your fingers give in (you start "
        "undertapping), not how accurate you stay.",
        "Score: the fastest tempo you kept up for 10 s, 30 s, 1, 2 and 5 min while pressing 90%+ of the "
        f"notes (overstreaming is fine); {BEST_PER_SETUP}, against your comfort level's typical tempo for that "
        "long; 10% faster ≈ +10. Average of the durations measured on 3+ setups.",
        "Play stream-heavy maps that are a little longer than usual and keep tapping to the end, even "
        "when accuracy drops; make the stretches longer first, then faster.",
    ),
    "accuracy": (
        "Hit timing on single notes (not in streams): the share of hit notes that were not 300s. Lower is better.",
        "Score: 50 − level-dependent points × log2(non-300 rate ÷ assumed OD- and comfort-matched rate), "
        "clipped to 0–100. At 4.5★ and OD 8, 90% 300s scores 50 and 80% scores 20; from 5.5★ up "
        "the previous reference and slope apply. Needs 60+ hit single notes.",
        "Play maps you can full-combo and aim for 300s, not the combo. If your hits lean early or late "
        "(Tapping page), fix your offset first.",
    ),
    "sliders": (
        "Slider control: how hard the sliders are that you follow to the end without a break: "
        "speed, length, shape, speed changes and how soon the next note comes.",
        "Score: per play your 30 hardest sliders (whose head you hit), average difficulty × share held³; "
        f"{BEST_PER_SETUP}, against your comfort level's typical value, +25 per doubling.",
        "Play maps with long, curved and fast sliders and follow every one to its end; mix slow and fast "
        "sliders. Many short sliders don't raise it.",
    ),
    "reading": (
        "Reading: lower AR than usual for the map's difficulty on maps with many circles per second "
        "(HD / FL count too), decent accuracy on those maps, and BPM changes you read and hit accurately.",
        "Score: per passed map 2^((usual AR \u2212 AR) / 3 \u00d7 circles per second \u00f7 5) \u00d7 (up to "
        "\u00d71.5 for BPM changes hit as 300s) \u00d7 accuracy^8; "
        f"{BEST_PER_SETUP}; 50 = usual AR at 95%, +25 per doubling.",
        "Play busy maps a little below the AR you're used to (or with HD) and keep the accuracy up; maps "
        "with BPM changes, hitting the first notes after each change on time.",
    ),
    "consistency": (
        "Consistency: how steadily you keep your combo and your accuracy from map to map on the maps up to a star "
        "below a star rating (at 6.2★: maps of 5.2–6.2★ with mods; harder maps never count): at your comfort level, "
        "and in the comparison at each star rating.",
        "Score: every play gets a map score from how much of the combo you hold (10% of the max combo = 0, 30% "
        "= 0.48, 50% = 0.70, a full combo = 1: holding big parts counts, not only full combos) and your accuracy "
        "(88% = 0, 94% = 1). The better of the two counts 70%, the other 30%, and a play that keeps less than about "
        "20% of the combo fades to 0. Each map counts once (its plays averaged), a map a star easier half as much as "
        "one at the star rating; consistency = your usual map score minus half how much it swings between maps. "
        "Needs 8 different maps; the more maps, the more reliable.",
        "Play many different maps of that star rating instead of retrying one: keep long stretches of combo and "
        "your accuracy up on every one, rather than chasing one great result.",
    ),
}
MISS_LABELS = {
    "aim": "aim — tapped in time but outside the circle (jumps and single notes)",
    "speed_aim": "speed-aim — tapped in time, but the cursor couldn't keep up with a stream, burst or very fast jump",
    "early": "too early — cursor on the note, tap outside the hit window",
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
    "accuracy": "hit windows (OD)",
    "sliders": "sliders",
    "reading": "approach rates (AR)",
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
            return "Comfort not established"
        case "not_enough_data":
            return "Not enough data"
        case "insufficient_challenge":
            return "Insufficient challenge"
        case "need_maps":
            return f"Need {v['maps']} relevant map/mod configurations"
        case "best_per_setup":
            return "Best per map/mod configuration; 0.95 rank decay"
        case "stamina_mean":
            return "Mean of measured duration scores; easy or untested durations stay unknown"
        case "accuracy_gate":
            return f"Need {v['heads']} timing heads after the DT accuracy >{v['dt_accuracy']:.0%} evidence gate"
        case "accuracy_measured":
            return "Effective-OD-matched non-300 share on eligible hit single heads"
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
            return "Fitted from every note against its difficulty (Star-Scale IRT)"
        case "irt_provisional":
            return "Fitted from every note, but still uncertain: more plays near your limit narrow it"
        case "irt_untested":
            return f"At least {v['tested']:.1f}★: you held what you played, so its limit isn't tested yet"
        case "irt_not_enough":
            return "Not enough notes near your limit to measure it yet"
        case "irt_failed":
            return "The fit didn't settle on one answer: no number is shown"
        case "irt_play_harder":
            return f"Play maps with {_IRT_TESTS[v['skill']]} harder than {v['stars']:.1f}★ to find your limit."
        case "irt_play_at":
            return f"Play maps with {_IRT_TESTS[v['skill']]} of about {v['stars']:.1f}★ to measure it."
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
