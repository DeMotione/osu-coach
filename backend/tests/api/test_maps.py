"""Map Suggestion, playlists and getting maps into osu!."""
import io
import zipfile
from pathlib import Path

import pytest
from tests.api.conftest import wait, workspace

from osu_coach.infrastructure.filesystem import lazer_import
from osu_coach.infrastructure.http import sources
from osu_coach.infrastructure.filesystem.collection_db import loads
from osu_coach.domain.map_recommendations import SKILLS
from osu_coach.infrastructure.filesystem.map_pool import POOL_PATH

pytestmark = pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built")


def test_suggestions_need_an_analysis(client):
    assert client.get("/api/maps/suggestions").json()["code"] == "no_profile"


def test_suggestions_and_hiding_maps(analysed):
    s = analysed.get("/api/maps/suggestions").json()
    assert s["sections"] and s["pool_size"] > 1000 and s["hidden"] == 0
    assert s["sections"][-1]["skill"] == "general" and s["sections"][-1]["title"] == "Level up"
    assert s["collection_name"].startswith("osu-coach: Map Suggestion (")
    first = s["sections"][0]["maps"][0]
    assert first["url"].startswith("https://osu.ppy.sh/") and first["why"] and first["stage"]
    assert analysed.post("/api/maps/hidden", json={"md5s": [first["md5"]]}).json() == 1
    again = analysed.get("/api/maps/suggestions").json()
    assert again["hidden"] == 1
    assert first["md5"] not in {m["md5"] for sec in again["sections"] for m in sec["maps"]}
    assert analysed.post("/api/maps/hidden", json={"md5s": ["not-an-md5"]}).status_code == 422
    assert analysed.delete("/api/maps/hidden").json() == 0
    assert analysed.get("/api/maps/suggestions").json()["hidden"] == 0


def test_playlist_without_replays_uses_the_level_given(client):
    pl = client.get("/api/playlists", params={"skill": "speed", "comfort": 4.0, "maps": 9}).json()
    assert not pl["has_profile"] and pl["comfort"] == 4.0 and pl["skill"] == "speed" and pl["maps"] == 9
    assert [st["stage"] for st in pl["stages"]] == ["Warm-up", "Core", "Push"]
    assert sum(len(st["maps"]) for st in pl["stages"]) == 9
    assert pl["collection_name"] == "osu-coach: Tapping speed (bursts/streams) (4.0★)"
    assert [s["key"] for s in pl["skills"]] == SKILLS                  # no weak quadrant without replays
    assert client.get("/api/playlists").json()["skill"] == "aim"       # the default
    assert client.get("/api/playlists", params={"skill": "quadrant"}).json()["code"] == "no_weak_quadrant"
    assert client.get("/api/playlists", params={"skill": "juggling"}).json()["code"] == "unknown_skill"
    assert client.get("/api/playlists", params={"maps": 50}).status_code == 422


def test_playlist_follows_the_profile(analysed):
    pl = analysed.get("/api/playlists").json()
    assert pl["has_profile"] and pl["skill"] == pl["default_skill"]
    assert any(s["score"] is not None for s in pl["skills"])


# ------------------------------------------------------------------ exports
@pytest.fixture
def export(client):
    pl = client.get("/api/playlists", params={"skill": "aim", "comfort": 4.0, "maps": 6}).json()
    maps = [m for st in pl["stages"] for m in st["maps"]]
    return {"name": pl["collection_name"], "maps": [{"md5": m["md5"], "beatmapset_id": m["beatmapset_id"]}
                                                    for m in maps]}


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
    disposition = r.headers["content-disposition"]                 # the name has a ★: ASCII fallback + UTF-8 name
    assert disposition.startswith('attachment; filename="osu-coach Jump aim (4,0_).zip"; filename*=UTF-8\'\'')
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
    from osu_coach.infrastructure.filesystem import locate
    root = tmp_path / "osu!"
    (root / "Songs").mkdir(parents=True)
    (root / "osu!.tester.cfg").write_text("")
    from osu_coach.infrastructure.filesystem.collection_db import read_collection_db, write_collection_db
    write_collection_db(root / "collection.db", {"mine": ["a" * 32]})
    ws = workspace(client)
    monkeypatch.setattr(ws, "installs", lambda refresh=False: locate.find_installs(stable_roots=[root], lazer_roots=[]))
    monkeypatch.setattr(locate, "is_osu_running", lambda: False)
    r = client.post("/api/exports/stable-collection", json=export)
    assert r.status_code == 200, r.text
    assert r.json()["backup"] and Path(r.json()["backup"]).is_file()
    names = [n for n, _ in read_collection_db(root / "collection.db")[1]]
    assert names == ["mine", export["name"]]
    monkeypatch.setattr(locate, "is_osu_running", lambda: True)
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
