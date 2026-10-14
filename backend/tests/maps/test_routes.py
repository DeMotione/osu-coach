"""Map suggestions and skill playlists (routes)."""

import pytest

from osu_coach.maps.domain import SKILLS
from osu_coach.maps.repository import POOL_PATH

pytestmark = [pytest.mark.usefixtures("_isolated"), pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built")]


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
