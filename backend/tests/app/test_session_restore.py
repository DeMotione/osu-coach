"""The session (scanned library, analysed replays, profile) survives a restart of the app."""

from __future__ import annotations

import time

import pytest

from osu_coach.analysis.domain import ANALYSIS_VERSION
from tests.conftest import analyse, make_client, plays_folder, scan, workspace

pytestmark = pytest.mark.usefixtures("_isolated")


def settle(client, timeout: float = 120) -> None:
    """Wait for the restore the start of the app began (it holds the busy gate while it runs)."""
    ws = workspace(client)
    end = time.monotonic() + timeout
    while ws.gate.holder is not None:
        assert time.monotonic() < end, "the restore is still running"
        time.sleep(0.05)


def first_session(tmp_path) -> None:
    with make_client(tmp_path / "cache") as c:
        scan(c, plays_folder(tmp_path))
        analyse(c, player="Mot1one")


def test_a_fresh_start_restores_nothing(tmp_path):
    with make_client(tmp_path / "cache") as c:
        assert workspace(c).gate.holder is None
        assert c.get("/api/library").json()["scanned"] is False
        assert c.get("/api/analysis").json()["analysed"] == 0


def test_the_library_and_analyses_come_back_after_a_restart(tmp_path):
    first_session(tmp_path)
    with make_client(tmp_path / "cache") as c:
        settle(c)
        lib = c.get("/api/library").json()
        assert lib["scanned"] is True and lib["replays"] == 3
        status = c.get("/api/analysis").json()
        assert status["analysed"] == 3 and status["player_label"] == "Mot1one"
        assert c.get("/api/library/selection", params={"player": "Mot1one"}).json()["replays"] == 3
        analyse(c, player="Mot1one")  # the restored library can be analysed again


def test_analyses_are_not_restored_when_the_cache_lost_one(tmp_path):
    first_session(tmp_path)
    next((tmp_path / "cache" / "analyses").glob(f"*-v{ANALYSIS_VERSION}.pkl")).unlink()
    with make_client(tmp_path / "cache") as c:
        settle(c)
        assert c.get("/api/analysis").json()["analysed"] == 0
        assert c.get("/api/library").json()["scanned"] is True


def test_a_scan_of_a_folder_that_is_gone_is_not_repeated(tmp_path):
    first_session(tmp_path)
    for p in (tmp_path / "plays").iterdir():
        p.unlink()
    (tmp_path / "plays").rmdir()
    with make_client(tmp_path / "cache") as c:
        assert workspace(c).gate.holder is None
        assert c.get("/api/library").json()["scanned"] is False
        assert c.get("/api/analysis").json()["analysed"] == 3


def test_a_broken_session_file_is_ignored(tmp_path):
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "session.json").write_text("{not json", encoding="utf-8")
    with make_client(tmp_path / "cache") as c:
        assert workspace(c).gate.holder is None
        assert c.get("/api/analysis").json()["analysed"] == 0
