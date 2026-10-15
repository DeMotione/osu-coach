"""Progress by month / week / day (the saved history) and skill goals."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import pandas as pd

from osu_coach.app.convert import integer, iso, num, text
from osu_coach.app.errors import Invalid, NoProfile, NotFound
from osu_coach.profile.domain import SKILL_LABELS
from osu_coach.progress import goals
from osu_coach.progress import repository as progress
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
    return ProgressOut(player=name, period=period, first_day=first, rows=rows)


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


def _legacy_scores(ws: Workspace) -> dict:
    p = ws.profile()
    return {k: num((p.skills.get(k) or {}).get("score")) for k in SKILL_LABELS} if p is not None else {}


def _goal_score(g: dict, current: dict, legacy: dict) -> float | None:
    source = current if g.get("score_source") == "experimental" else legacy
    return source.get(g["skill"])


def _plan_targets(scores: dict, open_skills: set[str]) -> list[tuple[str, float, float]]:
    """Use the same measured weak skills and 45-point cutoff as Overview."""
    weak = {k: score for k, score in scores.items() if score is not None and score <= 45 and k not in open_skills}
    return goals.suggested_targets(weak, PLAN_SKILLS)


def _goals(ws: Workspace, scores: dict, legacy: dict) -> list[dict]:
    """The saved goals, the ones reached by now marked as done (and saved)."""
    gl, changed = [], False
    for g in ws.settings().get("goals") or []:
        updated, reached = goals.update([g], {g["skill"]: _goal_score(g, scores, legacy)})
        gl.extend(updated)
        changed |= reached
    if changed:
        ws.update_settings(goals=gl)
    return gl


def _goal_out(g: dict, current) -> GoalOut:
    st = goals.status(g, current)
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
        progress=float(st["progress"]),
        left=num(st["left"]),
        days_left=int(st["days_left"]),
        state=st["state"],
        score_source="experimental" if g.get("score_source") == "experimental" else "legacy",
    )


def _history(ws: Workspace, gl: list[dict]) -> list[GoalHistory]:
    """The goal skills day by day since the oldest goal (from the saved progress), with the path to each target."""
    gl = [g for g in gl if g.get("score_source") != "experimental"]
    if not gl:
        return []
    conn = progress.connect(ws.cache_dir)
    try:
        names = [n for n, _ in progress.players(conn)]
        pref = ws.settings().get("player")
        player = pref if pref in names else (names[0] if names else None)
        since = min(dt.date.fromisoformat(g["created"]) for g in gl) - dt.timedelta(days=HISTORY_LEAD_DAYS)
        m = progress.by_period(conn, player, "day", since=since) if player is not None else pd.DataFrame()
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
    legacy = _legacy_scores(ws)
    gl = _goals(ws, scores, legacy)
    open_ = [g for g in gl if not g.get("done")]
    done = [g for g in gl if g.get("done")]
    open_out = [_goal_out(g, _goal_score(g, scores, legacy)) for g in open_]
    have = [
        SkillValue(key=k, label=short_label(k), score=float(scores[k]))
        for k in SKILL_LABELS
        if num(scores.get(k)) is not None
    ]
    open_skills = {g["skill"] for g in open_}
    weak = [s for s in sorted(have, key=lambda s: s.score) if s.score <= 45 and s.key not in open_skills]
    return GoalsOut(
        has_profile=ws.profile() is not None,
        open=open_out,
        done=[_goal_out(g, _goal_score(g, scores, legacy)) for g in done],
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
    gl = _goals(ws, scores, _legacy_scores(ws))
    ws.update_settings(
        goals=gl
        + [goals.new_goal(req.skill, scores.get(req.skill), req.target, req.deadline, score_source="experimental")]
    )
    return goals_out(ws)


def add_plan(ws: Workspace) -> GoalsOut:
    scores = _scores(ws)
    if not any(score is not None for score in scores.values()):
        raise NoProfile("No measured skill ratings yet. Analyse more replays before making a plan.")
    gl = _goals(ws, scores, _legacy_scores(ws))
    have_open = {g["skill"] for g in gl if not g.get("done")}
    deadline = dt.date.today() + dt.timedelta(weeks=PLAN_WEEKS)
    new = [
        goals.new_goal(k, cur, tg, deadline, score_source="experimental")
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
