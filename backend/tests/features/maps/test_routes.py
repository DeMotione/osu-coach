"""Map suggestions and skill playlists (routes)."""

import re

import pytest

from osu_coach.domain.maps.skillset import recommend
from osu_coach.domain.maps.suggestions import SKILLS
from osu_coach.infra.map_pool import POOL_PATH, load_pool

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
    assert s["collection_name"].startswith("osu-coach: Skill Development")
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


def test_lower_level_accuracy_playlist_requires_timing_od(client):
    pl = client.get(
        "/api/playlists",
        params={"skill": "accuracy", "comfort": 4.5, "ratings": '{"accuracy":13}', "assessed": "accuracy"},
    ).json()
    assert pl["maps"] > 0
    assert all(row["od"] >= 7.5 for stage in pl["stages"] for row in stage["maps"])
    assert all(row["breakdown"]["star_window"] <= 1.0 for stage in pl["stages"] for row in stage["maps"])


def test_sparse_lower_level_accuracy_stage_stays_empty(client):
    pl = client.get(
        "/api/playlists",
        params={"skill": "accuracy", "comfort": 2.5, "ratings": '{"accuracy":13}', "assessed": "accuracy"},
    ).json()
    warmup = next(stage for stage in pl["stages"] if stage["stage"] == "Warm-up")
    assert warmup["maps"] == []
    assert warmup["eligible"] == 0
    assert warmup["excluded"]["Outside star window"] > 0


def test_lower_level_accuracy_reports_when_no_od_qualified_maps():
    pool = load_pool()
    low_od_only = pool.nsmallest(1, "od")
    result = recommend(low_od_only.to_dict("records"), 4.5, {"accuracy": 13}, "accuracy", ("accuracy",))
    for stage in result.goals.values():
        assert stage.maps == ()
        assert stage.excluded["No qualified timing map in the configured star window"] == 1


def test_a_playlist_opens_on_a_weakness_with_a_rating():
    """A weakness without a rating (consistency before 8 maps around the comfort level) has no maps to offer."""
    from types import SimpleNamespace

    from osu_coach.features.maps.service import default_skill

    p = SimpleNamespace(weaknesses=["consistency", "speed", "aim"])
    assert default_skill(p, {"speed": 30.0, "aim": 40.0}) == "speed"
    assert default_skill(p, {}) == "aim" and default_skill(None, {}) == "aim"


def test_modified_playlist_starts_cancellable_job_and_validates_rate_range(client, monkeypatch):
    from osu_coach.features.maps import service

    monkeypatch.setattr(service, "search", lambda ws, request, report: None)
    body = {
        "skill": "aim",
        "comfort": 4,
        "ratings": '{"aim":50}',
        "allow_hr": True,
        "adjustable_dt": True,
        "min_rate": 1.2,
        "max_rate": 1.5,
    }
    started = client.post("/api/playlists/search", json=body)
    assert started.status_code == 202
    job = started.json()
    assert job["kind"] == "playlist" and job["cancellable"]
    invalid = client.post("/api/playlists/search", json={**body, "min_rate": 1.8})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_recommendation_settings"


def test_completed_maps(analysed):
    """The sample plays include pool maps: they are listed as finished, and playlists leave them out."""
    maps = analysed.get("/api/maps/completed").json()
    assert maps
    assert all(m["played_at"] for m in maps) and [m["played_at"] for m in maps] == sorted(
        (m["played_at"] for m in maps), reverse=True
    )
    done = {m["md5"] for m in maps}
    playlist = analysed.get("/api/playlists").json()
    assert done.isdisjoint(m["md5"] for st in playlist["stages"] for m in st["maps"])


def test_a_playlist_keeps_to_a_weak_spot(client):
    """ "Practise this" on an analysis page: only the maps on the weak spot, said in the heading and the collection."""
    base = {"skill": "speed", "comfort": 5.0, "ratings": '{"speed":50}', "assessed": "speed"}
    whole = client.get("/api/playlists", params=base).json()
    pl = client.get("/api/playlists", params={**base, "focus": "bpm:170-190"}).json()
    assert whole["focus"] is None
    assert pl["focus"] == "streams at 170–189 BPM" and pl["collection_name"].endswith("– streams at 170–189 BPM")
    assert 0 < pl["maps"] < whole["maps"]
    assert all(st["excluded"]["Not on the weak spot practised"] > 0 for st in pl["stages"])
    # each map says the stream speed it was picked by
    said = [float(re.match(r"streams at ~(\d+) BPM", m["why"])[1]) for st in pl["stages"] for m in st["maps"]]
    assert said and all(169 <= bpm <= 190 for bpm in said)
    bad = client.get("/api/playlists", params={**base, "focus": "bpm:190-170"})
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_focus"


def test_a_weak_spot_of_a_skill_without_a_rating_is_practised_at_your_level(client):
    """Without a rating the skill's playlist is empty; its weak spot is practised as if it were at the level (50)."""
    base = {"skill": "speed", "comfort": 5.0, "ratings": '{"aim":50}', "assessed": "speed"}
    assert client.get("/api/playlists", params=base).json()["maps"] == 0
    pl = client.get("/api/playlists", params={**base, "focus": "run:10-40"}).json()
    assert pl["maps"] > 0 and pl["abilities"]["speed"] == 50


def test_a_playlist_keeps_to_the_approach_rates_around_the_level(client):
    """Fine-tune → Approach rate: around the level by default, any, or a range chosen."""
    base = {"skill": "aim", "comfort": 6.5, "ratings": '{"aim":50}', "assessed": "aim"}
    level = client.get("/api/playlists", params=base).json()
    lo, hi = level["level_ar"]
    assert level["ar_range"] == [lo, hi] and round(hi - lo, 1) == 0.6
    assert all(lo <= m["ar"] <= hi for st in level["stages"] for m in st["maps"]) and level["maps"] > 0
    anything = client.get("/api/playlists", params={**base, "ar": "any"}).json()
    assert anything["ar_range"] is None and anything["maps"] > level["maps"]
    chosen = client.get("/api/playlists", params={**base, "ar": "9.2-9.8"}).json()
    assert chosen["ar_range"] == [9.2, 9.8]
    assert all(9.2 <= m["ar"] <= 9.8 for st in chosen["stages"] for m in st["maps"])
    bad = client.get("/api/playlists", params={**base, "ar": "9.8-9.2"})
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_ar_range"
    # a weak spot of AR ("Practise this" on Sliders & Reading) picks the AR itself
    reading = {**base, "skill": "reading", "ratings": '{"reading":50}', "assessed": "reading"}
    focused = client.get("/api/playlists", params={**reading, "focus": "ar:8-8.5"}).json()
    assert focused["ar_range"] is None
