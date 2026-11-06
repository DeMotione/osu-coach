"""The session (scanned library, analysed replays, profile) survives a restart of the app."""

from __future__ import annotations

import time
from threading import Event

import pytest

from osu_coach.domain.analysis.models import ANALYSIS_VERSION
from osu_coach.features.library import service as library_service
from osu_coach.infra import summaries
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


def wait_restored(client, timeout: float = 30) -> None:
    """Wait until the analysed plays of the last session are back (the background scan may still run)."""
    ws = workspace(client)
    end = time.monotonic() + timeout
    while ws.restoring:
        assert time.monotonic() < end, "the analysed plays are still being restored"
        time.sleep(0.02)


def test_the_library_and_analyses_come_back_after_a_restart(tmp_path, monkeypatch):
    first_session(tmp_path)
    release_scan = Event()
    original_scan = library_service.run_scan

    def delayed_scan(ws, args, report):
        release_scan.wait(timeout=5)
        return original_scan(ws, args, report)

    monkeypatch.setattr(library_service, "run_scan", delayed_scan)
    with make_client(tmp_path / "cache") as c:
        try:
            # The profile must be ready while the background scan is still pending.
            wait_restored(c)
            status = c.get("/api/analysis").json()
            assert status["analysed"] == 3 and status["player_label"] == "Mot1one"
        finally:
            release_scan.set()
        settle(c)
        lib = c.get("/api/library").json()
        assert lib["scanned"] is True and lib["replays"] == 3
        status = c.get("/api/analysis").json()
        assert status["analysed"] == 3 and status["player_label"] == "Mot1one"
        assert c.get("/api/library/selection", params={"player": "Mot1one"}).json()["replays"] == 3
        analyse(c, player="Mot1one")  # the restored library can be analysed again


def test_pages_say_the_session_is_being_restored_until_it_is(tmp_path, monkeypatch):
    first_session(tmp_path)
    release = Event()
    original = summaries.summaries_of

    def delayed(*args, **kwargs):
        release.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(summaries, "summaries_of", delayed)
    with make_client(tmp_path / "cache") as c:
        try:
            assert workspace(c).restoring
            assert c.get("/api/analysis").json()["restoring"] is True
            r = c.get("/api/profile/overview")
            assert r.status_code == 409 and r.json()["code"] == "no_profile"
            assert r.json()["detail"].startswith("Restoring your last session")
        finally:
            release.set()
        wait_restored(c)
        assert c.get("/api/analysis").json()["restoring"] is False
        assert c.get("/api/profile/overview").status_code == 200
        settle(c)


def test_a_failed_restore_says_nothing_was_analysed(tmp_path, monkeypatch):
    first_session(tmp_path)

    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(summaries, "summaries_of", broken)
    with make_client(tmp_path / "cache") as c:
        wait_restored(c)
        settle(c)
        r = c.get("/api/profile/overview")
        assert r.status_code == 409 and not r.json()["detail"].startswith("Restoring")


def test_a_corrupt_summaries_store_is_set_aside_and_made_again(tmp_path):
    first_session(tmp_path)
    store = tmp_path / "cache" / "summaries.sqlite"
    store.write_bytes(b"this is not a database" * 100)
    with make_client(tmp_path / "cache") as c:
        settle(c)
        assert c.get("/api/analysis").json()["analysed"] == 3  # made again from the analysis cache
        assert (tmp_path / "cache" / "summaries.sqlite.corrupt").is_file()
        analyse(c, player="Mot1one")


def test_plays_come_back_from_their_summaries_without_the_analysis_cache(tmp_path):
    first_session(tmp_path)
    for f in (tmp_path / "cache" / "analyses").glob(f"*-v{ANALYSIS_VERSION}.pkl"):
        f.unlink()
    with make_client(tmp_path / "cache") as c:
        settle(c)
        assert c.get("/api/analysis").json()["analysed"] == 3


def test_analyses_are_not_restored_when_one_is_gone_everywhere(tmp_path):
    first_session(tmp_path)
    next((tmp_path / "cache" / "analyses").glob(f"*-v{ANALYSIS_VERSION}.pkl")).unlink()
    (tmp_path / "cache" / "summaries.sqlite").unlink()
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
        settle(c)  # the analysed plays come back in the background; the scan isn't repeated
        assert c.get("/api/library").json()["scanned"] is False
        assert c.get("/api/analysis").json()["analysed"] == 3


def test_a_broken_session_file_is_ignored(tmp_path):
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "session.json").write_text("{not json", encoding="utf-8")
    with make_client(tmp_path / "cache") as c:
        assert workspace(c).gate.holder is None
        assert c.get("/api/analysis").json()["analysed"] == 0
