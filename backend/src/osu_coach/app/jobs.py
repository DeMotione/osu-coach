from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter
from pydantic import Field

from osu_coach.app.deps import WorkspaceDep
from osu_coach.app.errors import responses
from osu_coach.exports.schemas import LazerPackJob, OszJob
from osu_coach.jobs.schemas import job_view
from osu_coach.library.schemas import AnalysisJob, ScanJob
from osu_coach.play_goals.schemas import PlayGoalJob

router = APIRouter(tags=["Jobs"])

# The one place that knows every kind of job: ``kind`` picks the model (and so the type of ``result``).
Job = Annotated[ScanJob | AnalysisJob | LazerPackJob | OszJob | PlayGoalJob, Field(discriminator="kind")]
JOB_MODELS = {
    "scan": ScanJob,
    "analysis": AnalysisJob,
    "lazer_pack": LazerPackJob,
    "osz_download": OszJob,
    "play_goal": PlayGoalJob,
}


@router.get("/jobs", summary="Jobs still running")
def running(ws: WorkspaceDep, finished_after: dt.datetime | None = None) -> list[Job]:
    """``finished_after``: also the jobs that finished since then, so a client checking every few seconds sees
    the short ones it didn't start itself (a new play analysed by itself)."""
    if finished_after is not None and finished_after.tzinfo is None:
        finished_after = finished_after.replace(tzinfo=dt.UTC)
    return [job_view(JOB_MODELS[j.kind], j) for j in ws.jobs.running(finished_after)]


@router.get("/jobs/{job_id}", summary="A job's progress and result", responses=responses(404))
def get_job(job_id: str, ws: WorkspaceDep) -> Job:
    job = ws.jobs.get(job_id)
    return job_view(JOB_MODELS[job.kind], job)


@router.post("/jobs/{job_id}/cancel", summary="Stop a job", responses=responses(404, 409))
def cancel_job(job_id: str, ws: WorkspaceDep) -> Job:
    """Only jobs with ``cancellable`` (409 ``not_cancellable`` otherwise). The job stops between two steps, so poll
    it until its status is ``cancelled``; one that finished in the meantime keeps its result."""
    job = ws.jobs.cancel(job_id)
    return job_view(JOB_MODELS[job.kind], job)
