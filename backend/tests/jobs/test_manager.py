"""The background job runner and the busy gate."""

import threading
import time

import pytest

from osu_coach.app.errors import ApiError, Busy, NotFound
from osu_coach.jobs.manager import BusyGate, JobManager


def _finish(job, timeout=5):
    end = time.monotonic() + timeout
    while job.status == "running":
        assert time.monotonic() < end
        time.sleep(0.01)
    return job


@pytest.mark.parametrize("fails", [False, True])
def test_the_gate_is_open_once_an_exclusive_job_shows_finished(fails):
    """A client that sees the job finished may start the next task right away (#38: Clear after a scan)."""
    gate = BusyGate()
    jobs = JobManager(gate)
    release, seen = gate.release, []

    def watched_release():
        seen.append(job.status)
        release()

    gate.release = watched_release

    go = threading.Event()

    def work(report):
        go.wait(5)  # until ``job`` below is set
        if fails:
            raise RuntimeError("broken")
        return 1

    job = jobs.start("scan", "Scanning", work, exclusive=True)
    go.set()
    _finish(job)
    assert seen == ["running"]
    assert job.status == ("failed" if fails else "succeeded") and job.finished_at
    with gate.hold("next"):
        pass


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
    other = jobs.start("osz_download", "Downloading", lambda r: 1, exclusive=False)  # not exclusive: runs
    _finish(other)
    go.set()
    _finish(first)
    assert gate.holder is None
    _finish(jobs.start("analysis", "Analysing", lambda r: 2))  # free again
    with gate.hold("check"):
        assert gate.holder == "check"
    assert gate.holder is None


def test_a_cancelled_job_stops_at_its_next_report_and_frees_the_gate():
    gate = BusyGate()
    jobs = JobManager(gate)
    started, go, steps = threading.Event(), threading.Event(), []

    def work(report):
        for i in range(100):
            report(i, 100, f"step {i}")
            steps.append(i)
            started.set()
            go.wait(5)
        return "all done"

    job = jobs.start("lazer_pack", "Downloading", work, cancellable=True)
    assert started.wait(5)
    assert jobs.cancel(job.id) is job and job.message == "Stopping…"
    go.set()
    _finish(job)
    assert job.status == "cancelled" and job.result is None and job.error is None and steps == [0]
    assert gate.holder is None and jobs.running() == []
    assert jobs.cancel(job.id).status == "cancelled"  # again: nothing changes
    _finish(jobs.start("scan", "Scanning", lambda r: 1))  # the gate is free


def test_only_cancellable_jobs_can_be_cancelled():
    jobs = JobManager(BusyGate())
    go = threading.Event()
    job = jobs.start("scan", "Scanning", lambda r: go.wait(5))
    with pytest.raises(ApiError) as exc:
        jobs.cancel(job.id)
    assert exc.value.code == "not_cancellable" and job.status == "running"
    go.set()
    assert _finish(job).status == "succeeded"
    done = _finish(jobs.start("osz_download", "x", lambda r: 7, exclusive=False, cancellable=True))
    assert jobs.cancel(done.id).status == "succeeded" and done.result == 7  # finished first: keeps its result


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


def test_running_jobs_and_the_ones_finished_since_a_time():
    jobs = JobManager(BusyGate())
    go = threading.Event()
    done = _finish(jobs.start("scan", "Scanning", lambda r: 1))
    between = done.finished_at
    later = _finish(jobs.start("analysis", "Analysing", lambda r: 2))
    running = jobs.start("osz_download", "Downloading", lambda r: go.wait(5), exclusive=False)
    assert jobs.running() == [running]
    assert jobs.running(between) == [later, running]  # the scan finished at that time, not after it
    go.set()
    _finish(running)
