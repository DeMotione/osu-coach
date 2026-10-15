"""Map suggestions and skill playlists (routes)."""

import pytest

from osu_coach.maps.domain import SKILLS
from osu_coach.maps.repository import POOL_PATH

pytestmark = [
    pytest.mark.usefixtures("_isolated"),
    pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built"),
]


def test_suggestions_expose_missing_player_data(client):
    s = client.get("/api/maps/suggestions").json()
    assert not s["has_profile"] and "assumption" in s["comfort_source"]
    assert not s["sections"] and s["unmeasured_skills"]


def test_suggestions_and_hiding_maps(analysed):
    s = analysed.get("/api/maps/suggestions").json()
    assert s["pool_size"] > 1000 and s["hidden"] == 0
    assert not s["sections"]  # the two-replay fixture cannot measure a weak skill
    assert s["collection_name"].startswith("osu-coach: Map Suggestion")
    md5 = "a" * 32
    assert analysed.post("/api/maps/hidden", json={"md5s": [md5]}).json() == 1
    again = analysed.get("/api/maps/suggestions").json()
    assert again["hidden"] == 1
    assert analysed.post("/api/maps/hidden", json={"md5s": ["not-an-md5"]}).status_code == 422
    assert analysed.delete("/api/maps/hidden").json() == 0
    assert analysed.get("/api/maps/suggestions").json()["hidden"] == 0


def test_playlist_without_replays_uses_the_level_given(client):
    pl = client.get(
        "/api/playlists", params={"skill": "speed", "comfort": 4.0, "ratings": '{"speed":70}', "assessed": "speed"}
    ).json()
    assert not pl["has_profile"] and pl["comfort"] == 4.0 and pl["skill"] == "speed"
    assert [st["stage"] for st in pl["stages"]] == ["Warm-up", "Comfort", "Push"]
    assert pl["maps"] == sum(len(st["maps"]) for st in pl["stages"])
    assert pl["maps"] > 5
    assert pl["collection_name"].startswith("osu-coach: Tapping speed")
    assert [s["key"] for s in pl["skills"]] == SKILLS  # no weak quadrant without replays
    assert client.get("/api/playlists").json()["skill"] == "aim"  # the default
    assert client.get("/api/playlists", params={"skill": "quadrant"}).json()["code"] == "unknown_skill"
    assert client.get("/api/playlists", params={"skill": "juggling"}).json()["code"] == "unknown_skill"
    assert client.get("/api/playlists", params={"kappa": -1}).status_code == 422


def test_playlist_follows_the_profile(analysed):
    pl = analysed.get("/api/playlists").json()
    assert pl["has_profile"] and pl["skill"] == pl["default_skill"]
    assert all(s["score"] is None for s in pl["skills"])  # only two maps: no invented replay ability
    supplied = analysed.get("/api/playlists", params={"skill": "aim", "ratings": '{"aim":70}'}).json()
    assert supplied["abilities"]["aim"] == 70
