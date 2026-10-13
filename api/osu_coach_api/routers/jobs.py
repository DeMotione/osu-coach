from __future__ import annotations

from fastapi import APIRouter

from ..deps import WorkspaceDep, job_view
from ..errors import responses
from ..schemas.jobs import Job

router = APIRouter(tags=["Jobs"])


@router.get("/jobs", summary="Jobs still running")
def running(ws: WorkspaceDep) -> list[Job]:
    return [job_view(j) for j in ws.jobs.running()]


@router.get("/jobs/{job_id}", summary="A job's progress and result", responses=responses(404))
def get_job(job_id: str, ws: WorkspaceDep) -> Job:
    return job_view(ws.jobs.get(job_id))
