"""The Tips & Setup page. Answers 409 ``no_profile`` before replays were analysed."""
from __future__ import annotations

from fastapi import APIRouter

from osu_coach.app.deps import ProfileDep, WorkspaceDep
from osu_coach.app.errors import responses
from osu_coach.tips import schemas as S
from osu_coach.tips import service as pages

router = APIRouter(prefix="/profile", tags=["Analysis"], responses=responses(409))


@router.get("/tips", summary="Tips & Setup: calibration, tips, practice plan")
def tips(ws: WorkspaceDep, p: ProfileDep) -> S.TipsPage:
    return pages.tips_page(ws, p)
