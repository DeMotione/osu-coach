"""Background jobs: the fields every job has. Each feature declares the job model of its own kind
(``kind`` + a typed ``result``); the union of all kinds is assembled in ``routes/jobs.py``."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["running", "succeeded", "failed"]


class JobBase(BaseModel):
    id: str
    status: JobStatus
    progress: float | None = Field(description="0–1 when known.")
    message: str
    error: str | None
    created_at: dt.datetime
    finished_at: dt.datetime | None


def job_view(model: type[JobBase], job) -> JobBase:
    """The response model ``model`` for a running or finished job of :mod:`osu_coach.jobs.manager`."""
    return model(id=job.id, kind=job.kind, status=job.status, progress=job.progress, message=job.message,
                 error=job.error, created_at=job.created_at, finished_at=job.finished_at, result=job.result)
