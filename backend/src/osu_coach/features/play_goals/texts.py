"""The play goals' wording: the domain returns codes, these are the texts the page shows for them."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict

from osu_coach.domain.play_goals.models import AccuracyRange, Blocker, Reason, Recommendation
from osu_coach.domain.play_goals.recommend import dynamics as strong_demands

VERDICTS = {
    "fc_done": "Already FCed",
    "fc_near": "FC looks within reach",
    "stretch": "A stretch",
    "beyond": "Beyond current reach",
    "beyond_for_now": "Beyond current reach for now",
    "unknown": "Not enough evidence",
}
TONES = {"fc_done": "good", "fc_near": "good", "stretch": "warn", "beyond": "bad", "beyond_for_now": "bad"}
ACCURACY_EXPLANATION = (
    "Middle 80% of the most recent available comparable completed plays, capped at two per map. "
    "An empirical estimate, not a maximum or a calibrated prediction interval."
)
BLOCKER_TITLES = {
    "sliders": "Slider control",
    "speed": "Stream / burst tapping",
    "reading": "Tracking the next notes",
    "accuracy": "Hit timing",
    "flow_aim": "Spaced-stream aim",
    "aim": "Jump aim",
}
# demand: (what a map leaning on it is, what to train)
DEMANDS = {
    "aim": ("Jumpy", "Jump aim"),
    "flow_aim": ("Flow aim", "Flow aim"),
    "speed": ("Streamy", "Streaming"),
    "reading": ("Reading-heavy", "Reading"),
    "sliders": ("Slider-heavy", "Sliders"),
    "stamina": ("Stamina-heavy", "Stamina"),
}
STAGES = {"starter": "Starter", "core": "Core", "stretch": "Stretch"}


def reason(r: Reason) -> str:
    v = r.values
    match r.code:
        case "fc_exists":
            return "A complete, verified no-break play exists for this map and configuration."
        case "recent_best_breaks":
            return f"Your best of the latest {v[0]} attempt(s) has {v[1]} combo-breaking event(s)."
        case "qualitative":
            return "This is a qualitative assessment, not an FC probability."
        case "recent_best":
            attempts, accuracy, breaks, completed = v
            return (
                f"Your best of the latest {attempts} attempt(s): {accuracy:.1%} accuracy, {breaks} combo-breaking event(s)"
                + ("" if completed else ", did not finish")
                + "."
            )
        case "own_attempts_only":
            return "Based on your attempts of this map only."
        case "stars_above":
            return f"The target is {v[0]:.1f} stars above your typical verified completed maps with these mods."
        case "outside_range":
            return "Its demands are outside your demonstrated range. Train the stepping stones before grinding FC attempts."
        case "peers_no_fc":
            return "Comparable plays support an accuracy estimate, but do not establish this map as a realistic FC yet."
        case "practice_first":
            return "Use the practice objectives, then return with fresh attempts."
        case "needs_evidence":
            return "Needs a verified attempt of this map or enough similar plays with these mods."
    raise ValueError(f"unknown reason {r.code}")


def _skip(r: Reason) -> str:
    v = r.values
    match r.code:
        case "other_client":
            return f"{v[0]} on osu!{v[1]}, target is osu!{v[2]}"
        case "sim_mismatch":
            return "simulation did not match the replay result"
        case "unsupported_mods":
            return f"{v[0]} is not a supported mod setup"
        case "other_mods":
            return f"{v[0]}, target is +{v[1]}"
        case "incomplete":
            return "incomplete map or score data"
    raise ValueError(f"unknown skip reason {r.code}")


def skipped(why: Counter[Reason]) -> str | None:
    if not why:
        return None
    return f"{sum(why.values())} attempt(s) of this map skipped: " + "; ".join(_skip(r) for r in why) + "."


def dynamics(demands: Sequence[str]) -> str:
    """The map's overall character, e.g. Streamy or Jumpy + Reading-heavy."""
    return " + ".join(DEMANDS[k][0] for k in demands) or "Balanced"


def accuracy(estimate: AccuracyRange | None) -> dict | None:
    return None if estimate is None else {**asdict(estimate), "explanation": ACCURACY_EXPLANATION}


def blocker(b: Blocker) -> dict:
    return {
        "skill": b.skill,
        "title": BLOCKER_TITLES[b.skill],
        "observed": True,
        "detail": f"{b.events} breaking event(s) across {b.attempts} attempt(s). "
        "These are replay-derived patterns, not proof of a single underlying cause.",
        "timestamps": list(b.timestamps),
    }


def lacking(skill: str, skills: Mapping[str, float]) -> dict:
    return {
        "skill": skill,
        "title": DEMANDS[skill][1],
        "detail": f"This map leans on it; your score is {skills[skill] * 100:.0f}/100."
        if skill in skills
        else "This map leans on it; you have no score for it yet.",
        "observed": False,
        "timestamps": [],
    }


def _trains(focus: Sequence[dict], mods: str) -> str:
    return ", ".join(b["title"].lower() for b in focus) or (
        "HD reading"
        if "HD" in mods
        else "tempo and control"
        if "DT" in mods
        else "HR precision"
        if "HR" in mods
        else "consistent full-map play"
    )


def recommendation(r: Recommendation, focus: Sequence[dict]) -> dict:
    label = None
    if r.pp is not None:
        label = "Achievable FC scenario (estimate)" if r.projected else "Conditional FC scenario, not a forecast"
    mods = r.map["mods"]
    return {
        "map": {**r.map, "dynamics": dynamics(strong_demands(r.map))},
        "why": f"Trains {_trains(focus, mods)}.",
        "objective": f"Play +{mods}, aim for {r.practice_accuracy:.0%}, no combo breaks.",
        "step_up": "Pass twice, then move up.",
        "accuracy": accuracy(r.accuracy),
        "practice_accuracy": r.practice_accuracy,
        "pp": r.pp,
        "pp_ss": r.pp_ss,
        "pp_accuracy": r.pp_accuracy,
        "pp_label": label,
        "local_best_accuracy": r.local_best_accuracy,
        "achieved": r.achieved,
        "stage": STAGES[r.stage],
    }
