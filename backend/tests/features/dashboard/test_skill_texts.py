"""How the Overview words a skill rating: IRT as the map star rating it holds up on, never as "typical"."""

from __future__ import annotations

from osu_coach.domain.player.messages import Message
from osu_coach.domain.player.records import SkillRating
from osu_coach.features.dashboard.service import COMFORT_50, irt_facts, irt_level_text, irt_stars, natural_text


def irt(state: str, **kw) -> SkillRating:
    base = dict(score=62.0, maps=40, reason=Message(f"irt_{state}"), state=state, expected=6.0)
    return SkillRating(**{**base, **kw})


def test_measured_skill_reads_as_map_stars_with_range_and_units():
    row = irt("measured", stars=6.62, stars_low=6.31, stars_high=6.93, natural=221.4, natural_unit="BPM")
    assert irt_level_text(row) == "holds up on 6.6★ maps (likely 6.3–6.9★) · ≈ 221 BPM"


def test_accuracy_says_what_its_od_means():
    row = irt("provisional", stars=5.4, stars_low=5.0, stars_high=5.8, natural=8.04, natural_unit="OD")
    assert natural_text(row) == "≈ 90% 300s at OD 8.0"
    text = irt_level_text(row)
    assert text is not None and text.startswith("holds up on 5.4★ maps (likely 5.0–5.8★)")


def test_untested_skill_is_a_lower_bound_in_stars():
    row = irt("untested", stars=7.1, stars_low=7.1, reason=Message("irt_untested", {"skill": "sliders", "maps": 9.0}))
    text = irt_level_text(row)
    assert (
        text is not None
        and text.startswith("holds up on at least 7.1★ maps · ")
        and text.endswith("harder maps could show more")
    )


def test_a_lower_bound_never_goes_above_the_maps_played():
    held = Message("irt_untested", {"skill": "sliders", "maps": 7.2})
    row = irt("untested", stars=9.1, stars_low=9.1, reason=held)
    assert irt_stars(row) == (7.2, 7.2, None)
    text = irt_level_text(row)
    assert text is not None and text.startswith("holds up on at least 7.2★ maps")
    assert irt_stars(irt("measured", stars=9.1, stars_low=8.8, stars_high=9.4)) == (9.1, 8.8, 9.4)  # as fitted


def test_no_star_text_without_a_rating():
    assert irt_level_text(irt("not_enough_data", score=None)) is None
    assert irt_level_text(irt("measured", stars=None)) is None


def test_the_0_100_score_is_against_maps_of_the_level_not_players():
    facts = irt_facts(irt("measured", stars=6.6, stars_low=6.3, stars_high=6.9))
    assert facts[0] == "62 of 100 against maps of your level (6.0★), for charts and goals"
    assert not any("typical" in f for f in facts)
    assert "typical" not in COMFORT_50 and "assumed" in COMFORT_50
