from __future__ import annotations

from fastapi import APIRouter, Request

from osu_coach.app.deps import WorkspaceDep
from osu_coach.system import service
from osu_coach.system.schemas import Health, Meta

router = APIRouter(tags=["System"])


@router.get("/health", summary="Is the API up")
def health(request: Request, ws: WorkspaceDep) -> Health:
    return service.health(web_app=request.app.state.web_dir is not None, data_dir=ws.cache_dir)


@router.get("/meta", summary="Labels and choices shared by every page")
def meta(request: Request) -> Meta:
    return service.meta(api_docs=request.app.state.api_docs)
