"""Background jobs. A job's ``result`` is typed by its ``kind``."""
from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from osu_coach.api.schemas.exports import LazerPackResult, OszResult
from osu_coach.api.schemas.library import AnalysisResult, ScanResult

JobStatus = Literal["running", "succeeded", "failed"]


class JobBase(BaseModel):
    id: str
    status: JobStatus
    progress: float | None = Field(description="0–1 when known.")
    message: str
    error: str | None
    created_at: dt.datetime
    finished_at: dt.datetime | None


class ScanJob(JobBase):
    kind: Literal["scan"]
    result: ScanResult | None


class AnalysisJob(JobBase):
    kind: Literal["analysis"]
    result: AnalysisResult | None


class LazerPackJob(JobBase):
    kind: Literal["lazer_pack"]
    result: LazerPackResult | None


class OszJob(JobBase):
    kind: Literal["osz_download"]
    result: OszResult | None


Job = Annotated[ScanJob | AnalysisJob | LazerPackJob | OszJob, Field(discriminator="kind")]
JOB_MODELS = {"scan": ScanJob, "analysis": AnalysisJob, "lazer_pack": LazerPackJob, "osz_download": OszJob}
