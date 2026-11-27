"""How playlists pick their maps (Goals & Training → Playlist for a skill, and "Practise this")."""

import pytest

from osu_coach.domain.maps.focus import parse_focus
from osu_coach.domain.maps.skillset import OVER, rated_skills, recommend
from osu_coach.domain.maps.suggestions import SKILLS
from osu_coach.infra.map_pool import POOL_PATH, load_pool

pytestmark = [
    pytest.mark.usefixtures("_isolated"),
    pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built"),
]

LEVEL = 6.6
PLAYER = {"aim": 58.0, "flow_aim": 46.0, "speed": 50.0, "stamina": 47.0, "sliders": 81.0, "consistency": 81.0}


@pytest.fixture(scope="module")
def pool():
    return load_pool().to_dict("records")


def _playlist(pool, abilities=PLAYER, skill="aim", **kw):
    return recommend(pool, LEVEL, abilities, skill, rated_skills(skill, abilities), **kw)


def _maps(result):
    return [m for stage in result.goals.values() for m in stage.maps]


def test_a_playlist_has_a_warm_up_a_comfort_and_a_push_stage_each_harder_than_the_one_before(pool):
    result = _playlist(pool)
    assert list(result.goals) == ["Warm-up", "Comfort", "Push"]
    stars = [stage.target_stars for stage in result.goals.values()]
    assert stars == sorted(stars) and len(set(stars)) == 3
    assert all(stage.maps for stage in result.goals.values())


def test_a_map_you_already_played_is_never_suggested(pool):
    first = _playlist(pool)
    played = frozenset(m.md5 for m in _maps(first)[:10])
    again = _playlist(pool, played=played)
    assert not {m.md5 for m in _maps(again)} & played
    assert all(stage.excluded["Already played"] > 0 for stage in again.goals.values())


def test_no_map_asks_another_skill_for_more_than_half_a_star_beyond_your_rating(pool):
    # a weak spaced-streams rating: maps that ask much more of it are left out, and say so
    result = _playlist(pool, PLAYER | {"flow_aim": 25.0})
    assert any(stage.excluded.get("Over your Spaced streams rating", 0) for stage in result.goals.values())
    for m in _maps(result):
        assert all(b.overload <= OVER for b in m.breakdown.bottlenecks)


def test_the_target_skill_is_always_checked(pool):
    for skill in SKILLS:
        assert rated_skills(skill, dict.fromkeys(SKILLS, 50.0))[0] == skill


@pytest.mark.parametrize("skill", ["accuracy", "reading", "consistency"])
def test_accuracy_reading_and_consistency_never_leave_a_map_out(pool, skill):
    # #149: consistency is rated by how steadily combo and accuracy hold, accuracy can't be trained apart from the
    # rest, and the AR range takes reading's place: a low rating of one of them changes nothing
    high = _playlist(pool, PLAYER | {skill: 95.0})
    low = _playlist(pool, PLAYER | {skill: 5.0})
    assert [s.eligible for s in low.goals.values()] == [s.eligible for s in high.goals.values()]
    assert all(stage.maps for stage in low.goals.values())


def test_practise_this_keeps_to_the_weak_stream_speeds(pool):
    # #144: "streams wobble at 120–129 and 140–159 BPM" → only maps whose streams are at those speeds
    result = _playlist(pool, skill="speed", focus=parse_focus("bpm:120-130,140-160"))
    shown = _maps(result)
    assert shown
    for m in shown:
        bpm = m.map["stream_bpm"] + 0.5  # note times in whole ms: a 130 BPM stream measures 129.9
        assert 120 <= bpm < 130 or 140 <= bpm < 160


def test_practise_this_for_jumps_into_a_part_of_the_screen_keeps_to_maps_with_many_notes_there(pool):
    shown = _maps(_playlist(pool, focus=parse_focus("quadrant:top-left")))
    assert shown and all(m.map["q_top_left"] >= 0.27 for m in shown)


def test_a_playlist_keeps_to_the_approach_rates_chosen(pool):
    shown = _maps(_playlist(pool, ar_range=(9.2, 9.8)))
    assert shown and all(9.2 <= m.map["ar"] <= 9.8 for m in shown)


def test_the_playlist_api(client):
    base = {"skill": "aim", "comfort": 6.5, "ratings": '{"aim":50}', "assessed": "aim"}
    # by default the approach rates around your level: the typical AR of maps at it, 0.3 either way
    level = client.get("/api/playlists", params=base).json()
    low, high = level["level_ar"]
    assert level["ar_range"] == [low, high] and round(high - low, 1) == 0.6
    assert client.get("/api/playlists", params={**base, "ar": "any"}).json()["ar_range"] is None
    # "Practise this" says what it keeps to, also in the collection's name
    focused = client.get("/api/playlists", params={**base, "focus": "jump:long"}).json()
    assert focused["focus"] == "long jumps" and focused["collection_name"].endswith("long jumps")


def test_a_weak_spot_of_a_skill_without_a_rating_is_practised_at_your_level(client):
    base = {"skill": "speed", "comfort": 5.0, "ratings": '{"aim":50}', "assessed": "speed"}
    assert client.get("/api/playlists", params=base).json()["maps"] == 0  # nothing to rank against
    focused = client.get("/api/playlists", params={**base, "focus": "run:10-40"}).json()
    assert focused["maps"] > 0 and focused["abilities"]["speed"] == 50


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"focus": "bpm:190-170"}, "invalid_focus"),
        ({"ar": "9.8-9.2"}, "invalid_ar_range"),
        ({"skill": "x"}, "unknown_skill"),
    ],
)
def test_a_wrong_playlist_request_says_what_is_wrong(client, params, code):
    # API errors always carry a readable detail and a stable code
    r = client.get("/api/playlists", params={"comfort": 5.0, **params})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == code and body["detail"]
