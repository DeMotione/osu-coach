from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from osu_coach.app.deps import ProfileDep, WorkspaceDep
from osu_coach.app.errors import responses
from osu_coach.maps import service as svc
from osu_coach.maps.schemas import HideMaps, Playlist, Suggestions

router = APIRouter(tags=["Maps"])


@router.get("/maps/suggestions", summary="Maps for your weakest skills", responses=responses(409))
def suggestions(ws: WorkspaceDep, p: ProfileDep) -> Suggestions:
    """From the bundled pool of popular ranked maps around your level; maps you played or hid are left out."""
    return svc.suggestions(ws, p)


@router.post("/maps/hidden", summary="Never suggest these maps again", responses=responses(422))
def hide(req: HideMaps, ws: WorkspaceDep) -> int:
    """Returns how many maps are hidden now."""
    return svc.hide(ws, req.md5s)


@router.delete("/maps/hidden", summary="Suggest the hidden maps again")
def unhide(ws: WorkspaceDep) -> int:
    ws.update_settings(hidden_maps=[])
    return 0


@router.get(
    "/playlists", summary="A staged playlist (warm-up / core / push) for one skill", responses=responses(409, 422)
)
def playlist(
    ws: WorkspaceDep,
    skill: str | None = None,
    maps: Annotated[int, Query(ge=6, le=30)] = 15,
    comfort: Annotated[float | None, Query(ge=1.0, le=8.0)] = None,
) -> Playlist:
    """``skill`` defaults to your weakest one; ``comfort``: your level without analysed replays."""
    return svc.playlist(ws, skill, maps, comfort)
