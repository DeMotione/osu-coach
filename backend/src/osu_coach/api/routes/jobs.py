from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter
from pydantic import Field

from osu_coach.api.deps import WorkspaceDep
from osu_coach.api.errors import responses
from osu_coach.api.schemas.exports import LazerPackJob, OszJob
from osu_coach.api.schemas.jobs import job_view
from osu_coach.api.schemas.library import AnalysisJob, ScanJob

router = APIRouter(tags=["Jobs"])

# The one place that knows every kind of job: ``kind`` picks the model (and so the type of ``result``).
Job = Annotated[ScanJob | AnalysisJob | LazerPackJob | OszJob, Field(discriminator="kind")]
JOB_MODELS = {"scan": ScanJob, "analysis": AnalysisJob, "lazer_pack": LazerPackJob, "osz_download": OszJob}


@router.get("/jobs", summary="Jobs still running")
def running(ws: WorkspaceDep) -> list[Job]:
    return [job_view(JOB_MODELS[j.kind], j) for j in ws.jobs.running()]


@router.get("/jobs/{job_id}", summary="A job's progress and result", responses=responses(404))
def get_job(job_id: str, ws: WorkspaceDep) -> Job:
    job = ws.jobs.get(job_id)
    return job_view(JOB_MODELS[job.kind], job)
