from __future__ import annotations

from fastapi import APIRouter

from osu_coach.analyse import service as svc
from osu_coach.analyse.schemas import AnalysisJob, AnalysisRequest, AnalysisStatus
from osu_coach.app.deps import WorkspaceDep
from osu_coach.app.errors import responses
from osu_coach.jobs.schemas import job_view
from osu_coach.library.service import require_library

router = APIRouter(tags=["Replays"])


@router.post("/analysis", summary="Analyse replays (background job)", status_code=202, responses=responses(409, 422))
def analyse(req: AnalysisRequest, ws: WorkspaceDep) -> AnalysisJob:
    require_library(ws)
    return job_view(AnalysisJob, ws.jobs.start("analysis", "Analysing replays", lambda report: svc.run_analysis(ws, req, report)))


@router.get("/analysis", summary="The analysed replays")
def analysis(ws: WorkspaceDep) -> AnalysisStatus:
    return svc.analysis_status(ws)
