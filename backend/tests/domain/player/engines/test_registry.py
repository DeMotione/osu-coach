"""Rating engines: the comfort engine gives exactly the ratings of ratings.combine_ratings."""

import pytest

from osu_coach.domain.player import build_profile_from, summarize
from osu_coach.domain.player.engines import COMFORT, ENGINES, ComfortEngine, Rated, compare, engine_name, make_engine
from osu_coach.domain.player.engines.comfort.ratings import combine_ratings, strengths_and_weaknesses
from osu_coach.domain.player.engines.comfort.readiness import compare_at
from osu_coach.infra.library import analyze_files
from tests.conftest import MOT1ONE, OTHERS, replay_and_map


@pytest.fixture(scope="module")
def analysed_summaries():
    return [summarize(analyze_files(*replay_and_map(n)[:2])) for n in MOT1ONE + OTHERS]


def test_unknown_names_fall_back_to_classic():
    assert engine_name(None) == engine_name("magic") == COMFORT
    assert all(engine_name(n) == n for n in ENGINES)
    assert make_engine("magic").name == COMFORT
    assert make_engine("irt").name == "irt"


def test_classic_engine_is_the_combined_ratings(analysed_summaries):
    summaries = analysed_summaries
    replays = [s.meta for s in summaries]
    p = build_profile_from(summaries)
    comfort = p.levels.comfort_stars
    expected = combine_ratings([s.ratings for s in summaries], replays, comfort)
    assert p.skill_ratings == expected
    assert (p.strengths, p.weaknesses) == strengths_and_weaknesses(expected)
    assert p.engine == COMFORT and p.rated.skills == expected
    assert build_profile_from(summaries, engine=ComfortEngine()).skill_ratings == expected


def test_compare_uses_the_engine_of_the_ratings(analysed_summaries):
    p = build_profile_from(analysed_summaries, level=5.0)
    rated = Rated(engine=COMFORT, skills=p.skill_ratings)
    assert compare(rated, 5.0, 6.0) == compare_at(p.skill_ratings, 5.0, 6.0)
