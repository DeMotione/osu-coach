"""Fixtures: an app on a temporary data folder, the sample replays of the core tests, and no network."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from osu_coach.infrastructure.http import sources
from osu_coach.main import create_app
from osu_coach.config import LOCAL_HOSTS, Settings

RES = Path(__file__).resolve().parents[1] / "resources"
INDEX = {i["replay"]: i for i in json.loads((RES / "index.json").read_text())}
MOT1ONE = ["mot1one__lazer_nm.osr", "mot1one__lazer_dthd_spinner.osr", "mot1one__lazer_failed.osr"]   # old -> new
OTHERS = ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr"]


def replay_and_map(name: str) -> tuple[Path, Path]:
    return RES / "replays" / name, RES / "maps" / f"{INDEX[name]['md5']}.osu"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """No osu! installs of this computer, no network, and a home folder of its own (lazer import folders)."""
    monkeypatch.setenv("OSU_COACH_NO_AUTODETECT", "1")
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path / "default-cache"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setattr(sources, "fetch_beatmap_by_md5", lambda md5: None)
    monkeypatch.setattr(sources, "download_osz", lambda set_id, dest, progress=None: None)


def make_client(cache: Path, web_dir: Path | None = None, api_docs: bool = True) -> TestClient:
    config = Settings(cache_dir=cache, web_dir=web_dir, allowed_hosts=LOCAL_HOSTS + ("testserver",),
                       reveal_folders=False, analysis_workers=1, api_docs=api_docs)
    return TestClient(create_app(config))


@pytest.fixture
def client(tmp_path) -> TestClient:
    with make_client(tmp_path / "cache") as c:
        yield c


def workspace(client: TestClient):
    return client.app.state.workspace


def wait(client: TestClient, job: dict, timeout: float = 180) -> dict:
    """Poll a job until it has finished."""
    end = time.monotonic() + timeout
    while True:
        r = client.get(f"/api/jobs/{job['id']}")
        assert r.status_code == 200, r.text
        job = r.json()
        if job["status"] != "running":
            return job
        assert time.monotonic() < end, f"job {job['kind']} still running"
        time.sleep(0.05)


def plays_folder(tmp_path: Path, names=MOT1ONE) -> Path:
    folder = tmp_path / "plays"
    folder.mkdir(exist_ok=True)
    for n in names:
        rp, mp = replay_and_map(n)
        shutil.copy(rp, folder / n)
        shutil.copy(mp, folder / f"{n}.osu")
    return folder


def scan(client: TestClient, folder: Path, latest: int = 500) -> dict:
    r = client.post("/api/library/scan", json={"mode": "library", "folders": [str(folder)], "latest": latest})
    assert r.status_code == 202, r.text
    job = wait(client, r.json())
    assert job["status"] == "succeeded", job
    return job


def analyse(client: TestClient, **body) -> dict:
    r = client.post("/api/analysis", json={"online": False, **body})
    assert r.status_code == 202, r.text
    job = wait(client, r.json())
    assert job["status"] == "succeeded", job
    return job


@pytest.fixture
def analysed(tmp_path, client) -> TestClient:
    """A client with the three sample plays of one player scanned and analysed."""
    scan(client, plays_folder(tmp_path))
    analyse(client, player="Mot1one")
    return client
