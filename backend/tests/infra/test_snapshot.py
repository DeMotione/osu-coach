"""The snapshot of the Analysis pages (#97): kept per version of the code, never a half-written file."""

from osu_coach.infra import snapshot
from osu_coach.infra.snapshot import Snapshot


def test_a_snapshot_comes_back_only_for_its_version(tmp_path):
    kept = Snapshot({"keys": ["a", "b"], "replay_set": "all"}, "2026-11-17T18:00:00+00:00", {"/api/x": {"n": 1.5}})
    snapshot.save(tmp_path, "v1", kept)
    assert snapshot.load(tmp_path, "v1") == kept
    assert snapshot.load(tmp_path, "v2") is None
    assert not (tmp_path / f"{snapshot.FILE}.tmp").exists()


def test_a_missing_or_broken_snapshot_is_none(tmp_path):
    assert snapshot.load(tmp_path, "v1") is None
    (tmp_path / snapshot.FILE).write_bytes(b"not gzip")
    assert snapshot.load(tmp_path, "v1") is None
