"""The Tips and Setup Tips pages. Both answer 409 ``no_profile`` before replays were analysed."""

from __future__ import annotations

from fastapi import APIRouter

from osu_coach.app.deps import ProfileDep, WorkspaceDep
from osu_coach.app.errors import responses
from osu_coach.tips import service as svc
from osu_coach.tips.schemas import SetupTipsPage, TipsPage

router = APIRouter(prefix="/profile", tags=["Analysis"], responses=responses(409))


@router.get("/tips", summary="Tips: what to practise, and the practice plan")
def tips(ws: WorkspaceDep, p: ProfileDep) -> TipsPage:
    return svc.tips_page(ws, p)


@router.get("/setup-tips", summary="Setup Tips: what to change in your setup, and what to keep")
def setup_tips(ws: WorkspaceDep, p: ProfileDep) -> SetupTipsPage:
    """Tablet area or sensitivity, audio offset and keys: a change only when it is big enough to feel and your misses
    show it costs you, with the exact new values."""
    return svc.setup_tips_page(ws, p)
