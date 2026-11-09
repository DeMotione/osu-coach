"""Getting maps into osu!: collection.db, maps straight into lazer, stable collection, .osz downloads (routes)."""

import threading
import zipfile
from pathlib import Path

import pytest

from osu_coach.infra.beatmaps import sources
from osu_coach.infra.exports import lazer_import
from osu_coach.infra.exports.collection_db import loads
from osu_coach.infra.map_pool import POOL_PATH
from tests.conftest import wait, workspace

pytestmark = [
    pytest.mark.usefixtures("_isolated"),
    pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built"),
]


# ------------------------------------------------------------------ exports
@pytest.fixture
def export(client):
    pl = client.get(
        "/api/playlists", params={"skill": "aim", "comfort": 4.0, "ratings": '{"aim":70}', "assessed": "aim"}
    ).json()
    maps = [m for st in pl["stages"] for m in st["maps"]][:6]
    return {
        "name": pl["collection_name"],
        "maps": [{"md5": m["md5"], "beatmapset_id": m["beatmapset_id"]} for m in maps],
    }


@pytest.fixture
def lazer(monkeypatch, tmp_path):
    """A lazer on this computer that imports each .osz it is handed and deletes it, as the real one does; and map
    downloads that work."""
    exe = tmp_path / "osulazer" / "current" / "osu!.exe"
    handed = []

    def run(program, args):
        handed.append((program, list(args)))
        for a in args:
            if str(a).endswith(".osz"):
                Path(a).unlink()

    def fake_download(set_id, dest, progress=None, stop=None):
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        osz = dest / f"{set_id} Artist - Title.osz"
        with zipfile.ZipFile(osz, "w") as z:
            z.writestr("map.osu", "osu file format v14\n")
        return osz

    monkeypatch.setattr(lazer_import, "find_lazer", lambda candidates=None: exe)
    monkeypatch.setattr(lazer_import, "launch", run)
    monkeypatch.setattr(sources, "download_osz", fake_download)
    return exe, handed


def test_export_preview(client, export):
    p = client.post("/api/exports/preview", json=export).json()
    assert p["total_sets"] == len({m["beatmapset_id"] for m in export["maps"]}) == p["lazer_sets"]
    assert not p["stable_available"] and p["preferred_client"] == "stable"


def test_collection_db_download(client, export):
    r = client.post("/api/exports/collection-db", json=export)
    assert r.status_code == 200 and r.headers["content-disposition"] == 'attachment; filename="collection.db"'
    _, collections = loads(r.content)
    assert collections == [(export["name"], [m["md5"] for m in export["maps"]])]


def test_download_names_with_a_star_get_an_ascii_fallback():
    from osu_coach.features.exports.routes import content_disposition

    disposition = content_disposition("osu-coach Jumps (4,0★).zip")
    assert disposition.startswith("attachment; filename=\"osu-coach Jumps (4,0_).zip\"; filename*=UTF-8''")
    assert "%E2%98%85" in disposition


def test_without_lazer_nothing_is_sent_or_opened(client, export):
    # tests never find the computer's own lazer
    assert client.get("/api/meta").json()["lazer_found"] is False
    r = client.post("/api/exports/lazer-send", json=export)
    assert r.status_code == 404 and r.json()["code"] == "no_lazer"
    r = client.post("/api/exports/lazer-open", json={"beatmap_id": 2768184})
    assert r.status_code == 404 and r.json()["code"] == "no_lazer"


def test_sending_to_lazer_can_be_cancelled(client, export, monkeypatch, lazer):
    first, go = threading.Event(), threading.Event()

    def slow_download(set_id, dest, progress=None, stop=None):
        first.set()
        go.wait(5)
        return None

    monkeypatch.setattr(sources, "download_osz", slow_download)
    job = client.post("/api/exports/lazer-send", json=export).json()
    assert job["cancellable"] is True
    assert first.wait(5)
    r = client.post(f"/api/jobs/{job['id']}/cancel")
    assert r.status_code == 200 and r.json()["message"] == "Stopping…"
    go.set()
    job = wait(client, job)
    assert job["status"] == "cancelled" and job["result"] is None
    assert lazer[1] == []  # lazer got nothing
    assert client.post("/api/exports/lazer-send", json=export).status_code == 202  # not busy any more


def test_the_maps_go_straight_into_lazer(client, export, lazer, tmp_path):
    exe, handed = lazer
    assert client.get("/api/meta").json()["lazer_found"] is True
    job = wait(client, client.post("/api/exports/lazer-send", json=export).json())
    assert job["status"] == "succeeded", job
    res = job["result"]
    sets = sorted({m["beatmapset_id"] for m in export["maps"]})
    assert sorted(res["maps"]) == sorted(res["imported"]) == sets and res["not_imported"] == res["failed"] == []
    assert len(handed) == 1 and handed[0][0] == exe and len(handed[0][1]) == len(sets)
    cache = workspace(client).cache_dir
    assert all(Path(f).parent == cache / "lazer-maps" for f in handed[0][1])
    assert not list((cache / "lazer-maps").glob("*.osz"))  # lazer took them all
    assert not (cache / "lazer-import").exists() and not (tmp_path / "home" / "Downloads").exists()


def test_a_map_is_opened_in_lazer(client, lazer):
    exe, handed = lazer
    r = client.post("/api/exports/lazer-open", json={"beatmap_id": 2768184})
    assert r.status_code == 200 and r.json() == {"link": "osu://b/2768184"}
    assert handed == [(exe, ["osu://b/2768184"])]
    for bad in (0, -1, "1; calc", 2**31):
        assert client.post("/api/exports/lazer-open", json={"beatmap_id": bad}).status_code == 422
    assert len(handed) == 1


def test_cancelling_an_unknown_job(client):
    r = client.post("/api/jobs/nope/cancel")
    assert r.status_code == 404 and r.json()["code"] == "job_not_found"


def test_stable_collection_needs_a_stable_install(client, export):
    r = client.post("/api/exports/stable-collection", json=export)
    assert r.status_code == 404 and r.json()["code"] == "no_stable_install"


def test_stable_collection_is_merged_with_a_backup(client, export, tmp_path, monkeypatch):
    from osu_coach.infra.replays import detect

    root = tmp_path / "osu!"
    (root / "Songs").mkdir(parents=True)
    (root / "osu!.tester.cfg").write_text("")
    from osu_coach.infra.exports.collection_db import read_collection_db, write_collection_db

    write_collection_db(root / "collection.db", {"mine": ["a" * 32]})
    ws = workspace(client)
    monkeypatch.setattr(ws, "installs", lambda refresh=False: detect.find_installs(stable_roots=[root], lazer_roots=[]))
    monkeypatch.setattr(detect, "is_osu_running", lambda: False)
    r = client.post("/api/exports/stable-collection", json=export)
    assert r.status_code == 200, r.text
    assert r.json()["backup"] and Path(r.json()["backup"]).is_file()
    names = [n for n, _ in read_collection_db(root / "collection.db")[1]]
    assert names == ["mine", export["name"]]
    monkeypatch.setattr(detect, "is_osu_running", lambda: True)
    r = client.post("/api/exports/stable-collection", json=export)
    assert r.status_code == 409 and r.json()["code"] == "osu_running"


def test_osz_downloads_report_what_failed(client, tmp_path):
    r = client.post("/api/exports/osz", json={"folder": str(tmp_path / "maps"), "set_ids": [1, 2, 2]})
    job = wait(client, r.json())
    assert job["status"] == "succeeded" and job["result"]["downloaded"] == 0 and job["result"]["failed"] == [1, 2]


def _without_set(export):
    # the second map with no known set, as an old .osu file reads
    maps = [dict(m) for m in export["maps"]]
    maps[1]["beatmapset_id"] = 0
    return {**export, "maps": maps}, maps[1]["md5"]


def test_a_map_without_a_known_set_doesnt_break_the_export(client, export):
    body, _ = _without_set(export)
    p = client.post("/api/exports/preview", json=body)
    assert p.status_code == 200, p.text
    p = p.json()
    assert p["total_sets"] == len({m["beatmapset_id"] for m in body["maps"] if m["beatmapset_id"] > 0}) + 1
    assert p["lazer_sets"] == p["total_sets"] and p["lazer_approximate"]
    r = client.post("/api/exports/collection-db", json=body)
    assert r.status_code == 200 and loads(r.content)[1][0][1] == [m["md5"] for m in body["maps"]]


def test_sending_to_lazer_looks_up_a_maps_unknown_set(client, export, monkeypatch, lazer):
    body, md5 = _without_set(export)
    looked_up = []

    def lookup(m):
        looked_up.append(m)
        return {"id": 999, "beatmapset_id": 4242}

    monkeypatch.setattr(sources, "lookup_md5", lookup)
    job = wait(client, client.post("/api/exports/lazer-send", json=body).json())
    assert job["status"] == "succeeded", job
    assert looked_up == [md5]
    assert 4242 in job["result"]["maps"] and 0 not in job["result"]["maps"] and job["result"]["not_found"] == 0

    monkeypatch.setattr(sources, "lookup_md5", lambda m: None)
    job = wait(client, client.post("/api/exports/lazer-send", json=body).json())
    assert job["status"] == "succeeded" and job["result"]["not_found"] == 1 and 0 not in job["result"]["maps"]


def test_osz_downloads_skip_unknown_sets(client, tmp_path):
    r = client.post("/api/exports/osz", json={"folder": str(tmp_path / "maps"), "set_ids": [0, -1]})
    assert r.status_code == 422 and r.json()["code"] == "no_sets"
    assert not (tmp_path / "maps").exists()


def test_export_requests_are_validated(client):
    assert client.post("/api/exports/preview", json={"name": "x", "maps": []}).status_code == 422
    bad = {"name": "x", "maps": [{"md5": "zz", "beatmapset_id": 1}]}
    assert client.post("/api/exports/collection-db", json=bad).status_code == 422
