"""Progress by month / week / day (the saved history) and skill goals."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import pandas as pd

from osu_coach.app.convert import integer, iso, num, text
from osu_coach.app.errors import ApiError, Invalid, NoProfile, NotFound
from osu_coach.profile.domain import SKILL_LABELS
from osu_coach.progress import goals
from osu_coach.progress import repository as progress
from osu_coach.progress.domain import SKILL_REFERENCE
from osu_coach.progress.schemas import (
    GoalCreate,
    GoalHistory,
    GoalOut,
    GoalsOut,
    HistoryPoint,
    PeriodRow,
    ProgressOut,
    ProgressPlay,
    ProgressPlayer,
    SkillValue,
    SuggestedGoal,
)

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace

PLAN_WEEKS = 4
PLAN_SKILLS = 3
HISTORY_LEAD_DAYS = 14


def short_label(skill: str) -> str:
    return SKILL_LABELS.get(skill, skill).split(" (")[0]


# ------------------------------------------------------------------ progress
def players(ws: Workspace) -> list[ProgressPlayer]:
    conn = progress.connect(ws.cache_dir)
    try:
        return [ProgressPlayer(name=n, plays=c) for n, c in progress.players(conn)]
    finally:
        conn.close()


def _player(ws: Workspace, conn, player: str | None) -> str:
    names = [n for n, _ in progress.players(conn)]
    if not names:
        raise NotFound(
            "Nothing saved yet. Analyse your replays on the Replays page — choose All there once to fill in "
            "your older months.",
            "no_history",
        )
    if player is not None and player in names:
        return player
    if player is not None:
        raise NotFound(f"Nothing saved for {player!r}.", "unknown_player")
    pref = ws.settings().get("player")
    return pref if pref in names else names[0]


def _row(r: dict) -> PeriodRow:
    return PeriodRow(
        key=str(r["month"]),
        plays=int(r["plays"]),
        maps=int(r["maps"]),
        new_maps=int(r["new_maps"]),
        minutes=num(r.get("minutes")),
        comfort_stars=num(r.get("comfort_stars")),
        avg_stars=num(r.get("avg_stars")),
        max_stars_passed=num(r.get("max_stars_passed")),
        max_stars_fc=num(r.get("max_stars_fc")),
        accuracy=num(r.get("accuracy")),
        misses_per_100=num(r.get("misses_per_100")),
        ur=num(r.get("ur")),
        stream_bpm=num(r.get("stream_bpm")),
        few_plays=bool(r.get("few_plays")),
        skills={k: num(r.get(f"skill_{k}")) for k in SKILL_LABELS},
    )


def by_period(
    ws: Workspace, player: str | None, period: str, since: dt.date | None, until: dt.date | None
) -> ProgressOut:
    if since and until and since > until:
        raise Invalid("The start of the date range is after its end.", "bad_date_range")
    conn = progress.connect(ws.cache_dir)
    try:
        name = _player(ws, conn, player)
        days = progress.by_period(conn, name, "day")
        first = dt.date.fromisoformat(str(days["month"].iloc[0])) if len(days) else None
        m = progress.by_period(conn, name, period, since=since, until=until)
    finally:
        conn.close()
    rows = [_row(r) for r in m.to_dict("records")] if "maps" in m else []
    refs = m[SKILL_REFERENCE].dropna() if SKILL_REFERENCE in m else []
    reference = num(refs.iloc[-1]) if len(refs) else None  # the newest: saved by the last analysis
    return ProgressOut(player=name, period=period, first_day=first, skill_reference_stars=reference, rows=rows)


def period_plays(ws: Workspace, player: str | None, period: str, key: str) -> list[ProgressPlay]:
    conn = progress.connect(ws.cache_dir)
    try:
        name = _player(ws, conn, player)
        plays = progress.month_plays(conn, name, key, period)
    finally:
        conn.close()
    out = []
    for r in plays.to_dict("records"):
        result = "full combo" if r["fc"] else ("passed" if r["completed"] else "failed")
        out.append(
            ProgressPlay(
                played_at=iso(r.get("played_at")),
                map=f"{text(r.get('artist')) or ''} – {text(r.get('title')) or ''} [{text(r.get('version')) or ''}]",
                mods=text(r.get("mods")) or "NM",
                stars=num(r.get("stars")),
                accuracy=num(r.get("accuracy")),
                misses=integer(r.get("nmiss")),
                combo=integer(r.get("max_combo")),
                map_combo=integer(r.get("map_max_combo")),
                result=result,
            )
        )
    return out


# ------------------------------------------------------------------ goals
def _scores(ws: Workspace) -> dict:
    p = ws.profile()
    return {k: num((p.experimental_skills.get(k) or {}).get("score")) for k in SKILL_LABELS} if p is not None else {}


def _low_comfort(ws: Workspace) -> bool:
    p = ws.profile()
    comfort = num(p.levels.get("comfort_stars")) if p is not None else None
    return comfort is not None and comfort < 5.5


def _paused_accuracy_goal(g: dict, low_comfort: bool) -> bool:
    return (
        low_comfort
        and g.get("skill") == "accuracy"
        and g.get("score_source") == "experimental"
        and g.get("score_version", 1) < 2
        and not g.get("done")
    )


def _paused(g: dict, low_comfort: bool) -> bool:
    """An open goal that is no longer followed: set on the previous rating scale (before 0.10; its scores can't be
    compared with the Overview's, #70), or an accuracy goal of the recalibrated low-comfort scale."""
    if g.get("done"):
        return False
    return g.get("score_source") != "experimental" or _paused_accuracy_goal(g, low_comfort)


def _goal_score(g: dict, current: dict, low_comfort: bool = False) -> float | None:
    """The goal's skill on the Overview's scale; None for a paused goal and for a reached one of the previous scale."""
    if g.get("score_source") != "experimental" or _paused_accuracy_goal(g, low_comfort):
        return None
    return current.get(g["skill"])


def _plan_targets(scores: dict, open_skills: set[str]) -> list[tuple[str, float, float]]:
    """Use the same measured weak skills and 45-point cutoff as Overview."""
    weak = {k: score for k, score in scores.items() if score is not None and score <= 45 and k not in open_skills}
    return goals.suggested_targets(weak, PLAN_SKILLS)


def _goals(ws: Workspace, scores: dict, low_comfort: bool = False) -> list[dict]:
    """The saved goals, the ones reached by now marked as done (and saved)."""
    gl, changed = [], False
    for g in ws.settings().get("goals") or []:
        updated, reached = goals.update([g], {g["skill"]: _goal_score(g, scores, low_comfort)})
        gl.extend(updated)
        changed |= reached
    if changed:
        ws.update_settings(goals=gl)
    return gl


def _goal_out(g: dict, current, low_comfort: bool = False) -> GoalOut:
    st = goals.status(g, current)
    paused = _paused(g, low_comfort)
    return GoalOut(
        id=g["id"],
        skill=g["skill"],
        label=short_label(g["skill"]),
        start=num(g.get("start")),
        target=float(g["target"]),
        created=dt.date.fromisoformat(g["created"]),
        deadline=dt.date.fromisoformat(g["deadline"]),
        done=dt.date.fromisoformat(g["done"]) if g.get("done") else None,
        current=num(st["current"]),
        progress=None if paused else float(st["progress"]),
        left=num(st["left"]),
        days_left=int(st["days_left"]),
        state="paused" if paused else st["state"],
        score_source="experimental" if g.get("score_source") == "experimental" else "legacy",
    )


def _history(ws: Workspace, gl: list[dict]) -> list[GoalHistory]:
    """The goal skills day by day since the oldest goal (from the saved progress), with the path to each target.
    The saved daily scores are on the Overview's rating scale, so only goals set on that scale get a history."""
    gl = [g for g in gl if g.get("score_source") == "experimental"]
    if not gl:
        return []
    conn = progress.connect(ws.cache_dir)
    try:
        names = [n for n, _ in progress.players(conn)]
        pref = ws.settings().get("player")
        player = pref if pref in names else (names[0] if names else None)
        since = min(dt.date.fromisoformat(g["created"]) for g in gl) - dt.timedelta(days=HISTORY_LEAD_DAYS)
        # the rolling day scores: one day's plays swing too much to follow a goal by
        m = progress.by_period(conn, player, "day", since=since, rolling=True) if player is not None else pd.DataFrame()
    finally:
        conn.close()
    out = []
    for g in gl:
        col = f"skill_{g['skill']}"
        points = []
        if col in m and m[col].notna().any():
            points = [HistoryPoint(day=str(d), score=num(v)) for d, v in zip(m["month"], m[col], strict=True)]
        start = num(g.get("start"))
        target = [
            HistoryPoint(day=g["created"], score=start if start is not None else float(g["target"])),
            HistoryPoint(day=g["deadline"], score=float(g["target"])),
        ]
        out.append(
            GoalHistory(goal_id=g["id"], skill=g["skill"], label=short_label(g["skill"]), points=points, target=target)
        )
    return out


def goals_out(ws: Workspace) -> GoalsOut:
    scores = _scores(ws)
    low_comfort = _low_comfort(ws)
    gl = _goals(ws, scores, low_comfort)
    open_ = [g for g in gl if not g.get("done")]
    done = [g for g in gl if g.get("done")]
    open_out = [_goal_out(g, _goal_score(g, scores, low_comfort), low_comfort) for g in open_]
    have = [
        SkillValue(key=k, label=short_label(k), score=float(scores[k]))
        for k in SKILL_LABELS
        if num(scores.get(k)) is not None
    ]
    open_skills = {g["skill"] for g in open_ if not _paused(g, low_comfort)}
    weak = [s for s in sorted(have, key=lambda s: s.score) if s.score <= 45 and s.key not in open_skills]
    return GoalsOut(
        has_profile=ws.profile() is not None,
        open=open_out,
        done=[_goal_out(g, _goal_score(g, scores, low_comfort), low_comfort) for g in done],
        behind=sum(g.state in ("behind", "overdue") for g in open_out),
        skills=have,
        suggested=[
            SuggestedGoal(skill=k, label=short_label(k), current=cur, target=tg)
            for k, cur, tg in _plan_targets(scores, open_skills)
        ],
        weak_without_goal=weak,
        history=_history(ws, open_ + done) if gl and ws.profile() is not None else [],
    )


def add_goal(ws: Workspace, req: GoalCreate) -> GoalsOut:
    scores = _scores(ws)
    if not scores:
        raise NoProfile("Analyse your replays first — goals follow your skill scores.")
    if num(scores.get(req.skill)) is None:
        raise Invalid(f"{short_label(req.skill)} has no score yet, so it can't be followed.", "skill_without_score")
    if req.deadline < dt.date.today():
        raise Invalid("The deadline is in the past.", "deadline_past")
    if req.target <= scores[req.skill]:
        raise Invalid(
            f"{short_label(req.skill)} is already at {scores[req.skill]:.0f}: pick a higher target.", "target_reached"
        )
    low_comfort = _low_comfort(ws)
    gl = _goals(ws, scores, low_comfort)
    if any(g["skill"] == req.skill and not g.get("done") and not _paused(g, low_comfort) for g in gl):
        raise ApiError(409, "goal_exists", f"There is already a goal for {short_label(req.skill)}: remove it first.")
    ws.update_settings(
        goals=gl
        + [
            goals.new_goal(
                req.skill,
                scores.get(req.skill),
                req.target,
                req.deadline,
                score_source="experimental",
                score_version=2 if req.skill == "accuracy" else None,
            )
        ]
    )
    return goals_out(ws)


def add_plan(ws: Workspace) -> GoalsOut:
    scores = _scores(ws)
    if not any(score is not None for score in scores.values()):
        raise NoProfile("No measured skill ratings yet. Analyse more replays before making a plan.")
    low_comfort = _low_comfort(ws)
    gl = _goals(ws, scores, low_comfort)
    have_open = {g["skill"] for g in gl if not g.get("done") and not _paused(g, low_comfort)}
    deadline = dt.date.today() + dt.timedelta(weeks=PLAN_WEEKS)
    new = [
        goals.new_goal(k, cur, tg, deadline, score_source="experimental", score_version=2 if k == "accuracy" else None)
        for k, cur, tg in _plan_targets(scores, have_open)
    ]
    ws.update_settings(goals=gl + new)
    return goals_out(ws)


def remove_goal(ws: Workspace, goal_id: str) -> GoalsOut:
    gl = ws.settings().get("goals") or []
    if not any(g.get("id") == goal_id for g in gl):
        raise NotFound(f"No goal {goal_id}.", "goal_not_found")
    ws.update_settings(goals=[g for g in gl if g.get("id") != goal_id])
    return goals_out(ws)
