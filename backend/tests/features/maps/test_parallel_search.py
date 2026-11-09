"""Parallel exact-configuration calculation and its cache/job boundaries."""

from __future__ import annotations

import concurrent.futures as cf
import threading
import time

import pytest

from osu_coach.domain.maps.configuration import SearchOptions
from osu_coach.features.maps import service
from osu_coach.infra.jobs import Cancelled


def test_parallel_map_results_match_serial_and_reuse_cache(res, tmp_path):
    names = (
        "0619c930348063c2a967a3af4d69cd6b",
        "e0d805c891bf0e18ecb543435c6625f7",
    )
    records = [{"md5": name, "beatmap_id": 0} for name in (*names, names[0])]
    options = SearchOptions(allow_hr=True, adjustable_dt=True, min_rate=1.20, max_rate=1.20)

    def run(folder, workers):
        source = folder / "recommendations" / "maps"
        source.mkdir(parents=True)
        for name in names:
            (source / f"{name}.osu").write_bytes(res(f"maps/{name}.osu").read_bytes())
        progress = []
        result = list(
            service._search_map_results(folder, records, [], options, "stable", lambda *p: progress.append(p), workers)
        )
        assert progress[-1] == (len(records), len(records), "Ranking complete")
        return result

    serial = run(tmp_path / "serial", 1)
    parallel = run(tmp_path / "parallel", 2)
    assert serial == parallel
    assert [item[0] for item in parallel] == [0, 1, 2]
    assert all(item[1] and item[4] == 4 for item in parallel)
    assert parallel[0][2] == parallel[2][2]  # duplicate pool rows keep their accounting and output
    assert len(list((tmp_path / "parallel" / "recommendations" / "variants").glob("*.json.gz"))) == 2
    assert (
        list(service._search_map_results(tmp_path / "parallel", records, [], options, "stable", lambda *_: None, 2))
        == parallel
    )


def test_broken_pool_retries_unconsumed_maps_serially(monkeypatch, tmp_path):
    records = [{"md5": f"{i:032x}"} for i in range(5)]
    monkeypatch.setattr(service, "verified_bytes", lambda _cache, row, _libraries: row["md5"].encode())
    monkeypatch.setattr(
        service, "calculate_variants", lambda _cache, raw, configs: ([{"configuration_id": raw.decode()}], 0)
    )
    shutdown = []

    class BrokenPool:
        def __init__(self, **_kwargs):
            self.submits = 0

        def submit(self, *_args):
            self.submits += 1
            if self.submits == 5:
                raise cf.process.BrokenProcessPool("worker stopped")
            future = cf.Future()
            future.set_result(([{"configuration_id": records[self.submits - 1]["md5"]}], 0))
            return future

        def shutdown(self, **kwargs):
            shutdown.append(kwargs)

    monkeypatch.setattr(service.cf, "ProcessPoolExecutor", BrokenPool)
    result = list(
        service._search_map_results(tmp_path, records, [], SearchOptions(), "stable", lambda *_: None, workers=2)
    )
    assert [item[0] for item in result] == list(range(len(records)))
    assert [item[2][0]["configuration_id"] for item in result] == [row["md5"] for row in records]
    assert shutdown == [{"wait": True, "cancel_futures": True}]


def test_pool_start_failure_uses_serial_calculation(monkeypatch, tmp_path):
    records = [{"md5": "a" * 32}]
    monkeypatch.setattr(service, "verified_bytes", lambda *_: b"raw")
    monkeypatch.setattr(service, "calculate_variants", lambda *_: ([{"configuration_id": "serial"}], 0))

    def unavailable_pool(**_kwargs):
        raise OSError("workers unavailable")

    monkeypatch.setattr(service.cf, "ProcessPoolExecutor", unavailable_pool)
    result = list(
        service._search_map_results(tmp_path, records, [], SearchOptions(), "stable", lambda *_: None, workers=2)
    )
    assert result == [(0, True, [{"configuration_id": "serial"}], 0, 1)]


def test_cancellation_waits_for_running_map_before_returning(monkeypatch, tmp_path):
    started = threading.Event()
    finished = threading.Event()
    records = [{"md5": "a" * 32}]
    monkeypatch.setattr(service, "verified_bytes", lambda *_: b"raw")

    def calculate(_cache, _raw, _configs):
        started.set()
        time.sleep(0.35)
        finished.set()
        return [], 1

    monkeypatch.setattr(service, "calculate_variants", calculate)

    class ThreadPool(cf.ThreadPoolExecutor):
        def __init__(self, max_workers, mp_context):
            super().__init__(max_workers=max_workers)

    monkeypatch.setattr(service.cf, "ProcessPoolExecutor", ThreadPool)

    def report(*_args):
        if started.is_set():
            raise Cancelled

    with pytest.raises(Cancelled):
        list(service._search_map_results(tmp_path, records, [], SearchOptions(), "stable", report, workers=2))
    assert finished.is_set()  # the next job cannot race this map's cache write
