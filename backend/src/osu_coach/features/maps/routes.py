from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from osu_coach.app.deps import WorkspaceDep
from osu_coach.common.errors import responses
from osu_coach.common.jobs import job_view
from osu_coach.features.maps import service as svc
from osu_coach.features.maps.schemas import HideMaps, Playlist, PlaylistJob, PlaylistSearchRequest, Suggestions

router = APIRouter(tags=["Maps"])


@router.get("/maps/suggestions", summary="Comfort-level maps for measured weak skills", responses=responses(422))
def suggestions(
    ws: WorkspaceDep,
    kappa: Annotated[float, Query(ge=0)] = 0.5,
    min_relevance: Annotated[float, Query(ge=0, le=1)] = 0.3,
) -> Suggestions:
    """Rank comfort-level maps for skills below the player's expected level."""
    return svc.suggestions(ws, ws.profile(), kappa, min_relevance)


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
    comfort: Annotated[float | None, Query(gt=0)] = None,
    assessed: str | None = None,
    ratings: str | None = None,
    kappa: Annotated[float, Query(ge=0)] = 0.5,
    min_relevance: Annotated[float, Query(ge=0, le=1)] = 0.3,
    exclude_played: bool = True,
) -> Playlist:
    """``skill`` defaults to your weakest one; ``comfort`` and ``ratings`` can supply missing player data."""
    return svc.playlist(ws, skill, comfort, assessed, ratings, kappa, min_relevance, exclude_played)


@router.post(
    "/playlists/search",
    status_code=202,
    summary="Search exact mod and rate configurations",
    responses=responses(409, 422),
)
def search(request: PlaylistSearchRequest, ws: WorkspaceDep) -> PlaylistJob:
    try:
        svc.validate_search(ws, request)
    except ValueError as exc:
        from osu_coach.common.errors import Invalid

        raise Invalid(str(exc), "invalid_recommendation_settings") from exc
    return job_view(
        PlaylistJob,
        ws.jobs.start(
            "playlist", "Searching map configurations", lambda report: svc.search(ws, request, report), cancellable=True
        ),
    )
