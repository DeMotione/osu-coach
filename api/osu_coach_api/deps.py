"""FastAPI dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from osu_coach.profile import Profile

from .jobs import Job
from .schemas.jobs import JOB_MODELS
from .workspace import Workspace


def get_workspace(request: Request) -> Workspace:
    return request.app.state.workspace


def get_profile(ws: Annotated[Workspace, Depends(get_workspace)]) -> Profile:
    """The current profile; 409 ``no_profile`` before anything was analysed."""
    return ws.require_profile()


WorkspaceDep = Annotated[Workspace, Depends(get_workspace)]
ProfileDep = Annotated[Profile, Depends(get_profile)]


def job_view(job: Job):
    return JOB_MODELS[job.kind](id=job.id, kind=job.kind, status=job.status, progress=job.progress,
                                message=job.message, error=job.error, created_at=job.created_at,
                                finished_at=job.finished_at, result=job.result)
