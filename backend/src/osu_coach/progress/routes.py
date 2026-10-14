from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from osu_coach.app.deps import WorkspaceDep
from osu_coach.app.errors import responses
from osu_coach.progress.schemas import GoalCreate, GoalsOut, Period, ProgressOut, ProgressPlay, ProgressPlayer
from osu_coach.progress import service as svc

router = APIRouter(tags=["Progress & goals"])


@router.get("/progress/players", summary="Players with saved plays")
def players(ws: WorkspaceDep) -> list[ProgressPlayer]:
    return svc.players(ws)


@router.get("/progress", summary="Progress by month, week or day", responses=responses(404, 422))
def by_period(ws: WorkspaceDep, player: str | None = None, period: Annotated[Period, Query()] = "month",
              since: dt.date | None = None, until: dt.date | None = None) -> ProgressOut:
    """Not weighted by difficulty, so periods stay comparable. ``since`` / ``until``: days on this computer's
    clock, both included."""
    return svc.by_period(ws, player, period, since, until)


@router.get("/progress/plays", summary="The plays of one month, week or day", responses=responses(404))
def plays(ws: WorkspaceDep, key: str, player: str | None = None,
          period: Annotated[Period, Query()] = "month") -> list[ProgressPlay]:
    return svc.period_plays(ws, player, period, key)


@router.get("/goals", summary="Skill goals and how far along you are")
def goals(ws: WorkspaceDep) -> GoalsOut:
    return svc.goals_out(ws)


@router.post("/goals", summary="Add a goal", status_code=201, responses=responses(409, 422))
def add_goal(req: GoalCreate, ws: WorkspaceDep) -> GoalsOut:
    return svc.add_goal(ws, req)


@router.post("/goals/plan", summary="Add a 4-week plan for your 3 weakest skills", status_code=201,
             responses=responses(409))
def add_plan(ws: WorkspaceDep) -> GoalsOut:
    return svc.add_plan(ws)


@router.delete("/goals/{goal_id}", summary="Remove a goal", responses=responses(404))
def remove_goal(goal_id: str, ws: WorkspaceDep) -> GoalsOut:
    return svc.remove_goal(ws, goal_id)
