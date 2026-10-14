"""The analysis pages. All of them answer 409 ``no_profile`` before replays were analysed."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from osu_coach.api.deps import ProfileDep, WorkspaceDep
from osu_coach.api.errors import responses
from osu_coach.api.schemas import profile as S
from osu_coach.api.schemas.insights import Clicks
from osu_coach.api.services import insights, pages

router = APIRouter(prefix="/profile", tags=["Analysis"], responses=responses(409))


@router.get("/summary", summary="Player, replays and level of the current analysis")
def summary(ws: WorkspaceDep, p: ProfileDep) -> S.ProfileSummary:
    return pages.summary(ws, p)


@router.get("/replays", summary="The analysed replays (newest first)")
def replays(p: ProfileDep) -> list[S.AnalysedReplay]:
    return pages.analysed_replays(p)


@router.get("/overview", summary="Overview: level, skills, miss causes, top tips")
def overview(ws: WorkspaceDep, p: ProfileDep) -> S.Overview:
    return pages.overview(ws, p)


@router.get("/aim", summary="Aim: quadrants, playfield, directions, distances, calibration")
def aim(ws: WorkspaceDep, p: ProfileDep) -> S.AimPage:
    return pages.aim(ws, p)


@router.get("/clicks", summary="Where your clicks land")
def clicks(ws: WorkspaceDep, p: ProfileDep, view: Literal["screen", "movement"] = "screen") -> Clicks:
    """``screen``: as on screen (a constant offset shows); ``movement``: jumps only, turned so every jump goes right
    (over / undershoot)."""
    return ws.memo(f"clicks:{view}", lambda: insights.clicks(p.objects, view))


@router.get("/tapping", summary="Tapping: timing, stream speed, stamina, keys")
def tapping(ws: WorkspaceDep, p: ProfileDep) -> S.TappingPage:
    return pages.tapping(ws, p)


@router.get("/sliders-reading", summary="Sliders & Reading")
def sliders_reading(ws: WorkspaceDep, p: ProfileDep) -> S.SlidersReadingPage:
    return pages.sliders_reading(ws, p)


@router.get("/tips", summary="Tips & Setup: calibration, tips, practice plan")
def tips(ws: WorkspaceDep, p: ProfileDep) -> S.TipsPage:
    return pages.tips_page(ws, p)
