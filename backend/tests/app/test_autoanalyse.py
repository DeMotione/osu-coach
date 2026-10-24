"""New plays are added and analysed by themselves (#71)."""

import os
import shutil
import time

import pytest

from osu_coach.app.autoanalyse import AutoAnalyser
from osu_coach.replays.detect import Install
from tests.conftest import MOT1ONE, OTHERS, analyse, plays_folder, sample_paths, scan, workspace

pytestmark = pytest.mark.usefixtures("_isolated")


@pytest.fixture
def osu(tmp_path, client):
    """Two of a player's three plays analysed; osu!'s Data/r watched by an analyser of the test's own."""
    scan(client, plays_folder(tmp_path, MOT1ONE[:2]))
    analyse(client, player="Mot1one")
    client.app.state.auto_analyser.stop()  # the app's own would race the test's
    ws = workspace(client)
    data_r = tmp_path / "osu" / "Data" / "r"
    data_r.mkdir(parents=True)
    ws.scan_args.installs = [Install("stable", tmp_path / "osu", replay_dirs=[data_r])]
    auto = AutoAnalyser(ws)
    assert auto.tick() is None  # starts watching
    return ws, auto, data_r


def _play(data_r, name):
    """osu! saves a replay; its beatmap is one osu! has."""
    replay, beatmap = sample_paths(name)
    target = data_r / f"{name}"
    shutil.copy(replay, target)
    t = time.time() + 5
    os.utime(data_r, (t, t))
    return target, beatmap


def _until_job(auto, polls=10):
    for _ in range(polls):
        job = auto.tick()
        if job is not None:
            return job
    return None


def _finish(job, timeout=120):
    end = time.monotonic() + timeout
    while job.status == "running":
        assert time.monotonic() < end
        time.sleep(0.05)
    return job


def test_a_new_play_is_analysed_with_the_saved_choices(osu):
    ws, auto, data_r = osu
    replay, beatmap = _play(data_r, MOT1ONE[2])
    ws.library.add_files([beatmap])
    job = _finish(_until_job(auto))
    assert job.status == "succeeded", job.error
    assert job.kind == "analysis" and job.result.analysed == 3
    [new] = job.result.new_plays
    assert new.path == str(replay) and new.map
    assert any(r["path"] == str(replay) and r["source"] == "stable" for r in ws.library.replays)
    assert _until_job(auto, 3) is None  # once only


def test_a_play_the_analysis_choices_leave_out_is_only_added(osu):
    ws, auto, data_r = osu
    replay, beatmap = _play(data_r, OTHERS[1])  # another player's
    ws.library.add_files([beatmap])
    assert _until_job(auto, 4) is None
    assert any(r["path"] == str(replay) for r in ws.library.replays)


def test_nothing_happens_when_switched_off(osu):
    ws, auto, data_r = osu
    ws.update_settings(auto_analyse=False)
    _play(data_r, MOT1ONE[2])
    assert _until_job(auto, 4) is None
    assert auto._watcher is None
