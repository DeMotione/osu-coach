"""Progress by month / week / day (the saved history) and skill goals."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import pandas as pd

from osu_coach.common.convert import integer, iso, num, text
from osu_coach.common.errors import ApiError, Invalid, NoProfile, NotFound
from osu_coach.common.texts import SKILL_LABELS
from osu_coach.domain.player.engines import ENGINE_LABELS, SCORE, STARS, engine_name, make_engine, measured_scores
from osu_coach.domain.progress import goals
from osu_coach.domain.progress.periods import HISTORY_ENGINE, SKILL_REFERENCE, period_metrics
from osu_coach.domain.replays import scope
from osu_coach.features.progress.schemas import (
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
from osu_coach.infra import clock, progress

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace
    from osu_coach.domain.player import PlaySummary

PLAN_WEEKS = 4
PLAN_SKILLS = 3
HISTORY_LEAD_DAYS = 14
MAX_STARS = 15.0  # the highest target of a goal in stars


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
    pref = ws.settings().player
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
        max_stars_passed_map=text(r.get("max_stars_passed_map")),
        max_stars_fc=num(r.get("max_stars_fc")),
        accuracy=num(r.get("accuracy")),
        misses_per_100=num(r.get("misses_per_100")),
        ur=num(r.get("ur")),
        stream_bpm=num(r.get("stream_bpm")),
        few_plays=bool(r.get("few_plays")),
        skills={k: num(r.get(f"skill_{k}")) for k in SKILL_LABELS},
    )


def _analysed(ws: Workspace, name: str) -> list[PlaySummary] | None:
    """The replays the Overview is built from (the last analysis, All / Best replays) of player ``name``;
    None when nothing of that player is analysed."""
    chosen = [a for a in scope.select(ws.plays, ws.replay_set()) if (a.meta.player or "") == name]
    return chosen or None


def _analysed_metrics(ws: Workspace, name: str, chosen: list[PlaySummary], period: str) -> pd.DataFrame:
    """Skill numbers per ``period`` of the analysed replays, rated at the Overview's comfort level (so a period
    holding all of them shows the Overview's numbers). Kept until the analysis or the choices change."""

    def compute() -> pd.DataFrame:
        prof = ws.profile()
        reference = num(prof.levels.comfort_stars) if prof is not None else None
        # periods in this computer's time zone, as the saved plays are grouped (summarize_periods)
        metrics = period_metrics(chosen, clock.local_tz(), reference=reference, periods=(period,), rolling=False)
        return progress.metrics_frame(metrics)

    return ws.memo(f"progress:{name}:{period}", compute)


def by_period(
    ws: Workspace,
    player: str | None,
    period: str,
    since: dt.date | None,
    until: dt.date | None,
    replays: str = "analysed",
) -> ProgressOut:
    if since and until and since > until:
        raise Invalid("The start of the date range is after its end.", "invalid_date_range")
    conn = progress.connect(ws.cache_dir)
    try:
        name = _player(ws, conn, player)
        chosen = _analysed(ws, name)
        keys = metrics = None
        if replays == "analysed" and chosen is not None:
            keys = [a.key for a in chosen]
            metrics = _analysed_metrics(ws, name, chosen, period)
        days = progress.by_period(conn, name, "day", keys=keys, metrics=metrics)
        first = dt.date.fromisoformat(str(days["month"].iloc[0])) if len(days) else None
        m = progress.by_period(conn, name, period, since=since, until=until, keys=keys, metrics=metrics)
    finally:
        conn.close()
    rows = [_row(r) for r in m.to_dict("records")] if "maps" in m else []
    refs = m[SKILL_REFERENCE].dropna() if SKILL_REFERENCE in m else []
    reference = num(refs.iloc[-1]) if len(refs) else None  # the newest: saved by the last analysis
    return ProgressOut(
        player=name,
        period=period,
        replays="analysed" if keys is not None else "all",
        analysed_plays=len(chosen) if chosen is not None else None,
        first_day=first,
        skill_reference_stars=reference,
        rows=rows,
    )


def period_plays(
    ws: Workspace, player: str | None, period: str, key: str, replays: str = "analysed"
) -> list[ProgressPlay]:
    conn = progress.connect(ws.cache_dir)
    try:
        name = _player(ws, conn, player)
        chosen = _analysed(ws, name) if replays == "analysed" else None
        keys = [a.key for a in chosen] if chosen is not None else None
        plays = progress.month_plays(conn, name, key, period, keys=keys)
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
    """The skill scores the plan picks weak skills by: measurements only (an IRT "at least" score is left out)."""
    p = ws.profile()
    if p is None:
        return {}
    measured = measured_scores(p.skill_ratings)
    return {k: num(measured.get(k)) for k in SKILL_LABELS}


def _values(ws: Workspace) -> dict[str, tuple[float, str]]:
    """What a goal for each skill follows now, and in what: the engine's score, or its star level (#129)."""
    p = ws.profile()
    if p is None:
        return {}
    return {k: v for k, v in make_engine(p.engine).goal_values(p.skill_ratings).items() if k in SKILL_LABELS}


def _engine_of(g: dict) -> str:
    """The engine a goal was set with (older goals: Comfort-Based)."""
    return engine_name(g.get("engine"))


def _low_comfort(ws: Workspace) -> bool:
    p = ws.profile()
    comfort = num(p.levels.comfort_stars) if p is not None else None
    return comfort is not None and comfort < 5.5


def _paused_accuracy_goal(g: dict, low_comfort: bool) -> bool:
    return (
        low_comfort
        and g["skill"] == "accuracy"
        and g.get("score_source") == "experimental"
        and g.get("score_version", 1) < 2
        and not g.get("done")
    )


def _pause_reason(g: dict, low_comfort: bool, engine: str, values: dict) -> str | None:
    """Why an open goal isn't followed now (None: it is): an older rating scale, a recalibrated accuracy goal, set
    with the other engine, or counted in another unit than the skill is now (a score goal of Star Levels from before
    its goals were in stars)."""
    if g.get("done"):
        return None
    if g.get("score_source") != "experimental":
        return "old_scale"
    if _paused_accuracy_goal(g, low_comfort):
        return "accuracy"
    if _engine_of(g) != engine:
        return "engine"
    now = values.get(g["skill"])
    if now is not None and now[1] != goals.unit_of(g):
        return "unit"
    return None


def _followed(g: dict, engine: str) -> bool:
    """Set on the current scale with the current engine (also when reached)."""
    return g.get("score_source") == "experimental" and _engine_of(g) == engine


def _goal_value(g: dict, values: dict, low_comfort: bool, engine: str) -> float | None:
    """The goal's skill now, in the goal's unit; None for a paused goal."""
    now = values.get(g["skill"])
    if _pause_reason(g, low_comfort, engine, values) or not _followed(g, engine) or now is None:
        return None
    return now[0] if now[1] == goals.unit_of(g) else None


def _plan_targets(scores: dict, values: dict, open_skills: set[str]) -> list[tuple[str, float, float, str]]:
    """The skills the Overview counts as weak (score 45 or less) without a goal, weakest first: (skill, now,
    target, unit), the target a step higher (10 points, or half a star on Star Levels)."""
    weak = {
        k: score
        for k, score in scores.items()
        if score is not None and score <= 45 and k not in open_skills and k in values
    }
    return [(k, values[k][0], goals.next_target(*values[k]), values[k][1]) for k in goals.weakest(weak, PLAN_SKILLS)]


def _save_goals(ws: Workspace, gl: list[dict]) -> None:
    """Save these goals, and the saved ones the pages can't read as they are (a hand edit to fix, not to lose)."""
    ws.update_settings(goals=gl + ws.settings().unreadable_goals)


def _goals(ws: Workspace, values: dict, low_comfort: bool = False) -> list[dict]:
    """The saved goals, the ones reached by now marked as done (and saved)."""
    gl, changed = [], False
    engine = ws.rating_engine()
    for g in ws.settings().goals or []:
        value = _goal_value(g, values, low_comfort, engine)
        updated, reached = goals.update([g], {g["skill"]: value}, today=clock.today())
        gl.extend(updated)
        changed |= reached
    if changed:
        _save_goals(ws, gl)
    return gl


def _goal_out(g: dict, values: dict, low_comfort: bool, engine: str) -> GoalOut:
    current = _goal_value(g, values, low_comfort, engine)
    st = goals.status(g, current, today=clock.today())
    reason = _pause_reason(g, low_comfort, engine, values)
    return GoalOut(
        id=g["id"],
        skill=g["skill"],
        label=short_label(g["skill"]),
        start=num(g.get("start")),
        target=float(g["target"]),
        created=dt.date.fromisoformat(g["created"]),
        deadline=dt.date.fromisoformat(g["deadline"]),
        done=dt.date.fromisoformat(g["done"]) if g.get("done") else None,
        current=num(st.current),
        progress=None if reason else st.progress,
        left=num(st.left),
        days_left=st.days_left,
        state="paused" if reason else st.state,
        score_source="experimental" if g.get("score_source") == "experimental" else "legacy",
        unit=goals.unit_of(g),
        paused_reason=reason,
        engine_label=ENGINE_LABELS[_engine_of(g)],
    )


def _history(ws: Workspace, gl: list[dict], values: dict, engine: str) -> list[GoalHistory]:
    """The goals followed with the current engine, day by day since the oldest one, with the path to each target.
    The saved daily scores are rated by one engine (``HISTORY_ENGINE``): a score goal set with it has them; any
    other (a goal in stars) has its value today. A goal in another unit than its skill now isn't on the chart."""
    gl = [
        g for g in gl if _followed(g, engine) and values.get(g["skill"], (0, goals.unit_of(g)))[1] == goals.unit_of(g)
    ]
    if not gl:
        return []
    m = pd.DataFrame()
    if engine == HISTORY_ENGINE and any(goals.unit_of(g) == SCORE for g in gl):
        conn = progress.connect(ws.cache_dir)
        try:
            names = [n for n, _ in progress.players(conn)]
            pref = ws.settings().player
            player = pref if pref in names else (names[0] if names else None)
            since = min(dt.date.fromisoformat(g["created"]) for g in gl) - dt.timedelta(days=HISTORY_LEAD_DAYS)
            # the rolling day scores: one day's plays swing too much to follow a goal by
            if player is not None:
                m = progress.by_period(conn, player, "day", since=since, rolling=True)
        finally:
            conn.close()
    out = []
    for g in gl:
        unit = goals.unit_of(g)
        col = f"skill_{g['skill']}"
        points = []
        if unit == SCORE and engine == HISTORY_ENGINE and col in m and m[col].notna().any():
            points = [HistoryPoint(day=str(d), score=num(v)) for d, v in zip(m["month"], m[col], strict=True)]
        else:
            now = values.get(g["skill"])
            if now is not None and now[1] == unit:
                points = [HistoryPoint(day=clock.today().isoformat(), score=now[0])]
        start = num(g.get("start"))
        target = [
            HistoryPoint(day=g["created"], score=start if start is not None else float(g["target"])),
            HistoryPoint(day=g["deadline"], score=float(g["target"])),
        ]
        out.append(
            GoalHistory(
                goal_id=g["id"],
                skill=g["skill"],
                label=short_label(g["skill"]),
                unit=unit,
                points=points,
                target=target,
            )
        )
    return out


def _skill_value(k: str, scores: dict, values: dict) -> SkillValue:
    value, unit = values[k]
    score = num(scores.get(k))
    return SkillValue(key=k, label=short_label(k), score=score if score is not None else value, value=value, unit=unit)


def _shown(value: float, unit: str) -> str:
    return f"{value:.2f}★" if unit == STARS else f"{value:.0f}"


def goals_out(ws: Workspace) -> GoalsOut:
    scores = _scores(ws)
    values = _values(ws)
    low_comfort = _low_comfort(ws)
    engine = ws.rating_engine()
    gl = _goals(ws, values, low_comfort)
    open_ = [g for g in gl if not g.get("done")]
    done = [g for g in gl if g.get("done")]
    open_out = [_goal_out(g, values, low_comfort, engine) for g in open_]
    have = [_skill_value(k, scores, values) for k in SKILL_LABELS if k in values]
    open_skills = {g["skill"] for g in open_ if not _pause_reason(g, low_comfort, engine, values)}
    weak = [s for s in sorted(have, key=lambda s: s.score) if s.score <= 45 and s.key not in open_skills]
    return GoalsOut(
        has_profile=ws.profile() is not None,
        open=open_out,
        done=[_goal_out(g, values, low_comfort, engine) for g in done],
        behind=sum(g.state in ("behind", "overdue") for g in open_out),
        skills=have,
        suggested=[
            SuggestedGoal(skill=k, label=short_label(k), current=cur, target=tg, unit=unit)
            for k, cur, tg, unit in _plan_targets(scores, values, open_skills)
        ],
        weak_without_goal=weak,
        history=_history(ws, open_ + done, values, engine) if gl and ws.profile() is not None else [],
    )


def add_goal(ws: Workspace, req: GoalCreate) -> GoalsOut:
    values = _values(ws)
    if ws.profile() is None:
        raise NoProfile("Analyse your replays first — goals follow your skill scores.")
    if req.skill not in values:
        raise Invalid(f"{short_label(req.skill)} has no score yet, so it can't be followed.", "skill_without_score")
    if req.deadline < clock.today():
        raise Invalid("The deadline is in the past.", "deadline_past")
    now, unit = values[req.skill]
    if unit == STARS and req.target > MAX_STARS:
        raise Invalid(f"A goal in stars goes up to {MAX_STARS:.0f}★.", "target_out_of_range")
    if req.target <= now:
        raise Invalid(
            f"{short_label(req.skill)} is already at {_shown(now, unit)}: pick a higher target.", "target_reached"
        )
    low_comfort = _low_comfort(ws)
    engine = ws.rating_engine()
    gl = _goals(ws, values, low_comfort)
    if any(
        g["skill"] == req.skill and not g.get("done") and not _pause_reason(g, low_comfort, engine, values) for g in gl
    ):
        raise ApiError(409, "goal_exists", f"There is already a goal for {short_label(req.skill)}: remove it first.")
    _save_goals(
        ws,
        gl
        + [
            goals.new_goal(
                req.skill,
                now,
                req.target,
                req.deadline,
                goal_id=_new_id(),
                today=clock.today(),
                score_source="experimental",
                score_version=2 if req.skill == "accuracy" else None,
                engine=engine,
                unit=unit,
            )
        ],
    )
    return goals_out(ws)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def add_plan(ws: Workspace) -> GoalsOut:
    scores = _scores(ws)
    values = _values(ws)
    if not values:
        raise NoProfile("No measured skill ratings yet. Analyse more replays before making a plan.")
    low_comfort = _low_comfort(ws)
    engine = ws.rating_engine()
    gl = _goals(ws, values, low_comfort)
    have_open = {g["skill"] for g in gl if not g.get("done") and not _pause_reason(g, low_comfort, engine, values)}
    deadline = clock.today() + dt.timedelta(weeks=PLAN_WEEKS)
    new = [
        goals.new_goal(
            k,
            cur,
            tg,
            deadline,
            goal_id=_new_id(),
            today=clock.today(),
            score_source="experimental",
            score_version=2 if k == "accuracy" else None,
            engine=engine,
            unit=unit,
        )
        for k, cur, tg, unit in _plan_targets(scores, values, have_open)
    ]
    _save_goals(ws, gl + new)
    return goals_out(ws)


def remove_goal(ws: Workspace, goal_id: str) -> GoalsOut:
    gl = ws.settings().goals or []
    if not any(g["id"] == goal_id for g in gl):
        raise NotFound(f"No goal {goal_id}.", "goal_not_found")
    _save_goals(ws, [g for g in gl if g["id"] != goal_id])
    return goals_out(ws)
