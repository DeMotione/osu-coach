"""Noticing the replays osu! saves while osu! coach runs (#71)."""

import os
import shutil
import time

from osu_coach.replays.detect import Install
from osu_coach.replays.watch import SLACK_S, ReplayWatcher
from tests.conftest import MOT1ONE, sample_paths

REPLAY, OSU = sample_paths(MOT1ONE[0])


def _polls(watcher, n=2):
    """Two polls: one sees the new file, the next sees it has stopped growing."""
    found = []
    for _ in range(n):
        found += watcher.poll()
    return found


def _touch_folder(folder):
    """Some file systems keep a folder's time coarse: make sure the change shows."""
    t = time.time() + 5
    os.utime(folder, (t, t))


def test_a_new_stable_replay_is_reported_once_when_written(tmp_path):
    data_r = tmp_path / "Data" / "r"
    data_r.mkdir(parents=True)
    old = data_r / "old.osr"
    shutil.copy(REPLAY, old)
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    time.sleep(SLACK_S + 0.5)  # it arrived before the watcher started, not just now
    watcher = ReplayWatcher([Install("stable", tmp_path, replay_dirs=[data_r])])
    assert watcher.poll() == []
    new = data_r / "new.osr"
    shutil.copy(REPLAY, new)
    (data_r / "notes.txt").write_text("not a replay")
    _touch_folder(data_r)
    assert watcher.poll() == []  # just seen: it may still be written
    assert watcher.poll() == [(new, "stable")]
    assert _polls(watcher) == []  # once only; the old replay never
    _touch_folder(data_r)
    assert _polls(watcher) == []


def test_a_replay_still_being_written_waits_until_it_stops_growing(tmp_path):
    data_r = tmp_path / "r"
    data_r.mkdir()
    watcher = ReplayWatcher([Install("stable", tmp_path, replay_dirs=[data_r])])
    data = REPLAY.read_bytes()
    new = data_r / "new.osr"
    new.write_bytes(data[:100])
    _touch_folder(data_r)
    assert _polls(watcher, 1) == []
    new.write_bytes(data)  # osu! is still writing
    assert _polls(watcher, 1) == []
    assert _polls(watcher, 1) == [(new, "stable")]


def test_lazer_store_replays_are_found_in_new_and_old_sub_folders(tmp_path):
    files = tmp_path / "files"
    (files / "a" / "ab").mkdir(parents=True)
    watcher = ReplayWatcher([Install("lazer", tmp_path, files_dir=files)])
    assert watcher.folders == 3  # files, files/a, files/a/ab
    in_old = files / "a" / "ab" / ("ab" + "1" * 62)
    shutil.copy(REPLAY, in_old)
    shutil.copy(OSU, files / "a" / "ab" / ("ab" + "2" * 62))  # a beatmap: not a replay
    _touch_folder(files / "a" / "ab")
    # a sub-folder lazer makes for the new file
    (files / "c" / "cd").mkdir(parents=True)
    in_new = files / "c" / "cd" / ("cd" + "3" * 62)
    shutil.copy(REPLAY, in_new)
    _touch_folder(files)
    found = _polls(watcher, 4)  # files -> c -> cd -> written
    assert sorted(found) == sorted([(in_old, "lazer"), (in_new, "lazer")])


def test_a_replay_copied_in_counts_although_it_keeps_its_old_file_time(tmp_path):
    data_r = tmp_path / "r"
    data_r.mkdir()
    watcher = ReplayWatcher([Install("stable", tmp_path, replay_dirs=[data_r])])
    new = data_r / "copied.osr"
    shutil.copy2(REPLAY, new)  # copy2: the modification time of the sample file, long ago
    assert new.stat().st_mtime < watcher.started - 60
    _touch_folder(data_r)
    assert _polls(watcher) == [(new, "stable")]
