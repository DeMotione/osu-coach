"""Skill goals: a target score for a skill by a date, and how far along you are.

Goals live in the settings (``settings.json``, key ``goals``) as plain dicts:
``{"id", "skill", "start", "target", "created", "deadline", "done"}`` — ``start`` is the skill score when the
goal was set, ``done`` the date it was first reached (None while open). Dates are ISO strings.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass


def new_goal(
    skill: str,
    start: float | None,
    target: float,
    deadline: dt.date,
    *,
    goal_id: str,
    today: dt.date,
    score_source: str = "legacy",
    score_version: int | None = None,
    engine: str | None = None,
) -> dict:
    goal = {
        "id": goal_id,
        "skill": skill,
        "start": None if start is None else round(float(start), 1),
        "target": round(float(target), 1),
        "created": today.isoformat(),
        "deadline": deadline.isoformat(),
        "done": None,
        "score_source": score_source,
    }
    if score_version is not None:
        goal["score_version"] = score_version
    if engine is not None:
        goal["engine"] = engine  # the rating engine whose scores it follows
    return goal


def _num(v) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


@dataclass(frozen=True, slots=True)
class GoalStatus:
    """Where a goal stands (:func:`status`)."""

    current: float | None
    progress: float  # 0–1 of the way from the start score to the target
    left: float | None  # points still missing
    days_left: int  # negative: overdue
    state: str  # "done", "on track", "behind", "overdue" or "no data"


def status(goal: dict, current: float | None, today: dt.date) -> GoalStatus:
    """Where a goal stands (:class:`GoalStatus`). On track = at least as far as the share of the time that has
    passed."""
    cur = _num(current)
    start = _num(goal.get("start"))
    target = float(goal["target"])
    created = dt.date.fromisoformat(goal["created"])
    deadline = dt.date.fromisoformat(goal["deadline"])
    days_left = (deadline - today).days
    if goal.get("done"):
        return GoalStatus(current=cur, progress=1.0, left=0.0, days_left=days_left, state="done")
    if cur is None:
        return GoalStatus(current=None, progress=0.0, left=None, days_left=days_left, state="no data")
    base = start if start is not None else cur
    span = target - base
    progress = 1.0 if cur >= target else (max(0.0, min(1.0, (cur - base) / span)) if span > 0 else 0.0)
    if cur >= target:
        state = "done"
    elif days_left < 0:
        state = "overdue"
    else:
        total = max((deadline - created).days, 1)
        elapsed = min(max((today - created).days, 0), total) / total
        state = "on track" if progress >= elapsed - 0.1 else "behind"
    return GoalStatus(current=cur, progress=progress, left=max(0.0, target - cur), days_left=days_left, state=state)


def update(goals: list[dict], scores: dict, today: dt.date) -> tuple[list[dict], bool]:
    """Mark goals as done (with today's date) once the current score reaches the target. Returns the goals and
    whether anything changed."""
    changed = False
    out = []
    for g in goals:
        g = dict(g)
        cur = _num(scores.get(g["skill"]))
        if not g.get("done") and cur is not None and cur >= float(g["target"]):
            g["done"] = today.isoformat()
            changed = True
        out.append(g)
    return out, changed


def suggested_targets(scores: dict, n: int = 3, step: float = 10.0) -> list[tuple[str, float, float]]:
    """The ``n`` weakest skills with a score, and a target ``step`` points higher (at most 100):
    [(skill, current, target), ...] — a starting point for a training plan."""
    have = [(k, float(v)) for k, v in scores.items() if _num(v) is not None]
    have.sort(key=lambda kv: kv[1])
    return [(k, v, min(100.0, round(v + step))) for k, v in have[:n]]
