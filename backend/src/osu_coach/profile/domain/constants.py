"""Skill names, help texts and the thresholds the profile modules share."""

from __future__ import annotations

QUADRANTS = ["top-left", "top-right", "bottom-left", "bottom-right"]
DIR8 = ["right", "down-right", "down", "down-left", "left", "up-left", "up", "up-right"]
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
# Shown when the cursor is on a skill bar (Overview): what the skill measures, how the score is worked out,
# and what raises it. Keep in step with ``_skills`` / ``stamina_score``.
MISS_MODEL_SCORE = (
    "Score: your misses here vs what your own miss model expects for each note's difficulty; "
    "hardest plays count most (pp-style). 50 = as expected; each halving of misses = +35."
)
SKILL_HELP = {
    "aim": (
        "Jump aim: distance × speed × combo. Jumps and spaced notes (2+ circle widths apart, not "
        "streams): how fast the cursor has to move (distance ÷ time), and whether you hold the combo.",
        "Score: per passed map the 30 fastest jumps' cursor speed × (your combo ÷ max combo)^0.8, like pp; "
        "maps weighted like osu! pp; 50 = typical for your level, +25 per doubling.",
        "Jump maps slightly above your comfort level until you can hold the combo; keep your tablet area / "
        "sensitivity fixed while you do.",
    ),
    "flow_aim": (
        "Spaced streams: bursts and streams (3+ notes in a row) whose notes are about a circle width or "
        "more apart, so the cursor has to keep moving while you tap: spacing × BPM × how much "
        "of the map flows × combo.",
        "Score: per passed map the 50 fastest notes' cursor speed × (notes ÷ 100)^0.25 × "
        "(combo ÷ max combo)^0.8; maps weighted like pp; 50 = typical for your level.",
        "Spaced-stream maps at a BPM you can tap cleanly, then raise the BPM step by step. Move the arm "
        "in one smooth motion instead of stopping on every note.",
    ),
    "speed": (
        "Tapping speed: how fast you tap bursts and streams (3+ notes) cleanly: no finger miss (no tap, "
        "too early or late, notelock; cursor misses don't count) and 80%+ of the notes as 300s.",
        "Score: per map the 3rd fastest clean run; maps weighted like osu! pp (fastest 100%, then 1/(replays) "
        "less each); 50 = the stream speed typical for your level, 10% faster ≈ +10.",
        "Stream and burst maps 10–20 BPM above the speed you tap cleanly, in short sets with relaxed "
        "fingers. See the Tapping page for your clean stream speed.",
    ),
    "stamina": (
        "Stamina: for how long you keep a high tempo before your fingers give in (you start "
        "undertapping), not how accurate you stay.",
        "Score: the fastest tempo you kept up for 10 s, 30 s, 1, 2 and 5 min while pressing 90%+ of the "
        "notes (overstreaming is fine); maps weighted like osu! pp, against your level's typical tempo "
        "for that long; 10% faster ≈ +10. Average of the durations.",
        "Play stream-heavy maps that are a little longer than usual and keep tapping to the end, even "
        "when accuracy drops; make the stretches longer first, then faster.",
    ),
    "accuracy": (
        "Hit timing on single notes (not in streams): how many of them you hit as 300s.",
        "Score: (300 share − 50%) ÷ 49% × 100, so 99% 300s = 100 and 50% = 0 (top players' plays on "
        "single notes: 95–100%). Needs 60+ single notes.",
        "Play maps you can full-combo and aim for 300s, not the combo. If your hits lean early or late "
        "(Tapping page), fix your offset first.",
    ),
    "sliders": (
        "Slider control: how hard the sliders are that you follow to the end without a break: "
        "speed, length, shape, speed changes and how soon the next note comes.",
        "Score: per map your 30 hardest sliders (whose head you hit), average difficulty × share held³; "
        "maps weighted like osu! pp, against your level's typical value, +25 per doubling.",
        "Play maps with long, curved and fast sliders and follow every one to its end; mix slow and fast "
        "sliders. Many short sliders don't raise it.",
    ),
    "reading": (
        "Reading: lower AR than usual for the map's difficulty on maps with many circles per second "
        "(HD / FL count too), decent accuracy on those maps, and BPM changes you read and hit accurately.",
        "Score: per passed map 2^((usual AR \u2212 AR) / 3 \u00d7 circles per second \u00f7 5) \u00d7 (up to "
        "\u00d71.5 for BPM changes hit as 300s) \u00d7 accuracy^8; maps weighted like pp; 50 = usual AR at 95%.",
        "Play busy maps a little below the AR you're used to (or with HD) and keep the accuracy up; maps "
        "with BPM changes, hitting the first notes after each change on time.",
    ),
    "consistency": (
        "Consistency: does one miss make you miss more? The 10 notes after each miss are checked "
        "(notelock is ignored).",
        "Score: misses after a miss vs what the difficulty predicts there. A ratio of 2.0 (typical) "
        "= 50; each halving = +30, each doubling = −30.",
        "After a miss, reset and play the next note as if the combo were fresh; full-combo runs on "
        "easier maps build this.",
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
TAP_MISSES = ("early", "late", "no_tap", "notelock", "lost")  # misses of the fingers, not of the cursor
FAST_JUMP_MS = 125.0  # jumps this close in time (1/2 at 240 BPM, real time) are "very fast"

# ---- difficulty weighting


LOW_DATA_REPLAYS = 30  # fewer replays than this: every skill is marked "few data"
LOW_DATA_MAPS = 10  # ... or a skill measured on fewer maps
LOW_DATA_NOTES = 2000  # accuracy: single notes
FEW_MISSES = 3  # fewer misses than this (and expected) can't be compared: "too few misses to tell"
FEW_MISSES_NOTES = 500  # ... for consistency, on at least this many notes
ACCURACY_ZERO = 0.50  # accuracy score: 0 at 50% 300s on single notes ...
ACCURACY_TOP = 0.99  # ... 100 at 99% (top players' reference plays: 95–100%, median 98%)
