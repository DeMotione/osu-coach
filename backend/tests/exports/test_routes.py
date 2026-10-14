"""Getting maps into osu!: collection.db, lazer import folder, stable collection, .osz downloads (routes)."""

import io
import zipfile
from pathlib import Path

import pytest

from osu_coach.beatmaps import sources
from osu_coach.exports import lazer_import
from osu_coach.exports.collection_db import loads
from osu_coach.maps.repository import POOL_PATH
from tests.conftest import wait, workspace

pytestmark = [
    pytest.mark.usefixtures("_isolated"),
    pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built"),
]


# ------------------------------------------------------------------ exports
@pytest.fixture
def export(client):
    pl = client.get("/api/playlists", params={"skill": "aim", "comfort": 4.0, "maps": 6}).json()
    maps = [m for st in pl["stages"] for m in st["maps"]]
    return {
        "name": pl["collection_name"],
        "maps": [{"md5": m["md5"], "beatmapset_id": m["beatmapset_id"]} for m in maps],
    }


def test_export_preview(client, export):
    p = client.post("/api/exports/preview", json=export).json()
    assert p["total_sets"] == len({m["beatmapset_id"] for m in export["maps"]}) == p["lazer_sets"]
    assert not p["stable_available"] and p["preferred_client"] == "stable"
    assert p["lazer_folder"].endswith(lazer_import.safe_name(export["name"]))


def test_collection_db_download(client, export):
    r = client.post("/api/exports/collection-db", json=export)
    assert r.status_code == 200 and r.headers["content-disposition"] == 'attachment; filename="collection.db"'
    _, collections = loads(r.content)
    assert collections == [(export["name"], [m["md5"] for m in export["maps"]])]


def test_lazer_zip_download(client, export):
    r = client.post("/api/exports/lazer-zip", json=export)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    disposition = r.headers["content-disposition"]  # the name has a ★: ASCII fallback + UTF-8 name
    assert disposition.startswith("attachment; filename=\"osu-coach Jump aim (4,0_).zip\"; filename*=UTF-8''")
    assert "%E2%98%85" in disposition
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    folder = lazer_import.safe_name(export["name"])
    assert sorted(names) == sorted([f"{folder}/osu!.user.cfg", f"{folder}/collection.db"])


def test_lazer_import_folder(client, export, monkeypatch):
    def fake_download(set_id, dest, progress=None):
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        osz = dest / f"{set_id}.osz"
        with zipfile.ZipFile(osz, "w") as z:
            z.writestr("map.osu", "osu file format v14\n")
        return osz

    monkeypatch.setattr(sources, "download_osz", fake_download)
    r = client.post("/api/exports/lazer-pack", json=export)
    assert r.status_code == 202
    job = wait(client, r.json())
    assert job["status"] == "succeeded", job
    res = job["result"]
    folder = Path(res["path"])
    assert (folder / "collection.db").is_file() and (folder / "osu!.user.cfg").is_file()
    assert sorted(res["maps"]) == sorted({m["beatmapset_id"] for m in export["maps"]}) and res["failed"] == []


def test_stable_collection_needs_a_stable_install(client, export):
    r = client.post("/api/exports/stable-collection", json=export)
    assert r.status_code == 404 and r.json()["code"] == "no_stable_install"


def test_stable_collection_is_merged_with_a_backup(client, export, tmp_path, monkeypatch):
    from osu_coach.replays import detect

    root = tmp_path / "osu!"
    (root / "Songs").mkdir(parents=True)
    (root / "osu!.tester.cfg").write_text("")
    from osu_coach.exports.collection_db import read_collection_db, write_collection_db

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


def test_export_requests_are_validated(client):
    assert client.post("/api/exports/preview", json={"name": "x", "maps": []}).status_code == 422
    bad = {"name": "x", "maps": [{"md5": "zz", "beatmapset_id": 1}]}
    assert client.post("/api/exports/collection-db", json=bad).status_code == 422
