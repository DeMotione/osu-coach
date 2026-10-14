"""Analysing the scanned replays: the result, the status, and what happens with Best replays."""

import shutil

import pytest

from tests.conftest import analyse, plays_folder, scan

pytestmark = pytest.mark.usefixtures("_isolated")


def test_failed_plays_and_best_replays(tmp_path, client):
    folder = plays_folder(tmp_path, ["mot1one__lazer_failed.osr"])
    shutil.copy(folder / "mot1one__lazer_failed.osr", folder / "copy.osr")
    scan(client, folder)
    client.patch("/api/settings", json={"replay_set": "best"})
    job = analyse(client)
    assert job["result"]["profile_ready"] is False and "Best replays is empty" in job["result"]["warnings"][0]
    status = client.get("/api/analysis").json()
    assert status["best_empty"] and status["profile_replays"] is None
    r = client.get("/api/profile/overview")
    assert r.status_code == 409 and "Best replays" in r.json()["detail"]
    client.patch("/api/settings", json={"replay_set": "all"})
    assert client.get("/api/profile/summary").json()["replays"] == 1  # the copy is the same play
