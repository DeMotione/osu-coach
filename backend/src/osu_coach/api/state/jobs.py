"""Background jobs for the slow work (scanning, analysing, downloading), polled by the client.

A job runs in its own thread and reports progress through a :class:`Reporter`. Jobs that change the replay
library hold the :class:`BusyGate` for their whole run, so two of them never touch the library at once; the
few synchronous endpoints that change it (the one-replay check) go through the same gate.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from osu_coach.api.errors import ApiError, Busy, NotFound

log = logging.getLogger("osu_coach.api.state.jobs")
KEEP_JOBS = 50


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class BusyGate:
    """One holder at a time; ``holder`` says who (shown in the "busy" error)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.holder: str | None = None

    def acquire(self, label: str, wait: float = 0.0) -> None:
        if not (self._lock.acquire(timeout=wait) if wait > 0 else self._lock.acquire(blocking=False)):
            raise Busy(self.holder or "a task")
        self.holder = label

    def release(self) -> None:
        self.holder = None
        self._lock.release()

    @contextmanager
    def hold(self, label: str, wait: float = 0.0) -> Iterator[None]:
        self.acquire(label, wait)
        try:
            yield
        finally:
            self.release()


@dataclass
class Job:
    kind: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = "running"            # running | succeeded | failed
    progress: float | None = None      # 0..1 when known
    message: str = ""
    result: Any = None
    error: str | None = None
    created_at: dt.datetime = field(default_factory=_now)
    finished_at: dt.datetime | None = None


class Reporter:
    """Progress of one job: ``(done, total, message)`` like the domain's progress callbacks, or a message."""

    def __init__(self, job: Job):
        self._job = job

    def __call__(self, done: float, total: float, message: str = "") -> None:
        self._job.progress = max(0.0, min(1.0, done / total)) if total else None
        if message:
            self._job.message = str(message)

    def note(self, message) -> None:
        self._job.message = str(message)


class JobManager:
    def __init__(self, gate: BusyGate, keep: int = KEEP_JOBS):
        self._gate = gate
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        self._keep = keep

    def start(self, kind: str, label: str, work: Callable[[Reporter], Any], exclusive: bool = True) -> Job:
        """Run ``work(reporter)`` in a thread; its return value becomes the job's result. ``exclusive``: hold the
        busy gate for the whole run (refused with 409 while another holder has it)."""
        if exclusive:
            self._gate.acquire(label)
        job = Job(kind=kind, message=f"{label}…")
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > self._keep:
                oldest = next(iter(self._jobs))
                if self._jobs[oldest].status == "running":
                    break
                self._jobs.pop(oldest)
        thread = threading.Thread(target=self._run, args=(job, work, exclusive), name=f"job-{kind}-{job.id}",
                                  daemon=True)
        try:
            thread.start()
        except RuntimeError:
            if exclusive:
                self._gate.release()
            raise
        return job

    def _run(self, job: Job, work: Callable[[Reporter], Any], exclusive: bool) -> None:
        try:
            job.result = work(Reporter(job))
            job.status, job.progress = "succeeded", 1.0
        except ApiError as exc:
            job.status, job.error = "failed", exc.message
        except Exception as exc:  # noqa: BLE001 - a job failure is reported to the client, not raised
            log.exception("job %s (%s) failed", job.id, job.kind)
            job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = _now()
            if exclusive:
                self._gate.release()

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise NotFound(f"No job {job_id}.", "job_not_found")
        return job

    def running(self) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs.values() if j.status == "running"]
