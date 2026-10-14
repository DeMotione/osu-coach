"""Fixtures and helpers shared by the tests of every feature.

* the sample replays and maps in ``tests/resources`` (``replay_and_map``, ``sample_paths``, ``plays_folder``);
* for the route tests, an app on a temporary data folder without network or osu! installs: those test modules
  set ``pytestmark = pytest.mark.usefixtures("_isolated")``, then use ``client`` / ``analysed``.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from osu_coach.beatmaps import sources
from osu_coach.config import LOCAL_HOSTS, Settings
from osu_coach.main import create_app

RES = pathlib.Path(__file__).parent / "resources"
DEV = pathlib.Path(__file__).parent.parent / "dev_data"
INDEX = {i["replay"]: i for i in json.loads((RES / "index.json").read_text())}
MOT1ONE = ["mot1one__lazer_nm.osr", "mot1one__lazer_dthd_spinner.osr", "mot1one__lazer_failed.osr"]   # old -> new
OTHERS = ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr"]


@pytest.fixture(autouse=True)
def _no_real_osu(monkeypatch):
    """Never pick up the osu! installs of the computer running the tests."""
    monkeypatch.setenv("OSU_COACH_NO_AUTODETECT", "1")


@pytest.fixture
def res():
    def _res(rel: str) -> pathlib.Path:
        p = RES / rel
        assert p.exists(), p
        return p

    return _res


@pytest.fixture
def index():
    """Header facts for the bundled sample replays (collected with osrparse)."""
    return dict(INDEX)


def replay_and_map(name: str):
    entry = INDEX[name]
    return RES / "replays" / name, RES / "maps" / f"{entry['md5']}.osu", entry


def sample_paths(name: str) -> tuple[Path, Path]:
    return RES / "replays" / name, RES / "maps" / f"{INDEX[name]['md5']}.osu"


@pytest.fixture
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
        rp, mp = sample_paths(n)
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
