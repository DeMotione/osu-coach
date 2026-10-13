"""The background job runner and the busy gate."""
import threading
import time

import pytest

from osu_coach_api.errors import ApiError, Busy, NotFound
from osu_coach_api.jobs import BusyGate, JobManager


def _finish(job, timeout=5):
    end = time.monotonic() + timeout
    while job.status == "running":
        assert time.monotonic() < end
        time.sleep(0.01)
    return job


def test_a_job_reports_progress_and_its_result():
    jobs = JobManager(BusyGate())
    seen = threading.Event()

    def work(report):
        report(1, 4, "a quarter")
        seen.wait(5)
        return {"ok": True}
    job = jobs.start("scan", "Scanning", work)
    for _ in range(500):
        if job.progress:
            break
        time.sleep(0.01)
    assert job.progress == 0.25 and job.message == "a quarter" and jobs.running() == [job]
    seen.set()
    _finish(job)
    assert job.status == "succeeded" and job.result == {"ok": True} and job.progress == 1.0 and job.finished_at
    assert jobs.get(job.id) is job and jobs.running() == []


def test_failures_keep_the_message():
    jobs = JobManager(BusyGate())

    def known(report):
        raise ApiError(409, "nothing", "Nothing to do.")

    def unknown(report):
        raise ValueError("boom")
    assert _finish(jobs.start("scan", "x", known)).error == "Nothing to do."
    assert _finish(jobs.start("scan", "x", unknown)).error == "ValueError: boom"


def test_exclusive_jobs_wait_for_each_other_and_release_the_gate():
    gate = BusyGate()
    jobs = JobManager(gate)
    go = threading.Event()
    first = jobs.start("scan", "Scanning", lambda r: go.wait(5))
    with pytest.raises(Busy, match="Scanning"):
        jobs.start("analysis", "Analysing", lambda r: None)
    other = jobs.start("osz_download", "Downloading", lambda r: 1, exclusive=False)    # not exclusive: runs
    _finish(other)
    go.set()
    _finish(first)
    assert gate.holder is None
    _finish(jobs.start("analysis", "Analysing", lambda r: 2))                     # free again
    with gate.hold("check"):
        assert gate.holder == "check"
    assert gate.holder is None


def test_unknown_job_and_old_jobs_are_forgotten():
    jobs = JobManager(BusyGate(), keep=3)
    with pytest.raises(NotFound):
        jobs.get("nope")
    done = [_finish(jobs.start("scan", "x", lambda r, i=i: i)) for i in range(5)]
    with pytest.raises(NotFound):
        jobs.get(done[0].id)
    assert jobs.get(done[-1].id).status == "succeeded"


def test_gate_waits_when_asked():
    gate = BusyGate()
    gate.acquire("first")
    threading.Timer(0.1, gate.release).start()
    with gate.hold("second", wait=5):
        assert gate.holder == "second"
