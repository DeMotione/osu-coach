import pytest

from osu_coach.profile.domain.ratings import (
    _accuracy_expected,
    _accuracy_score,
    _score,
    at_level,
)


def test_accuracy_score_decreases_as_non_300_rate_increases():
    reference = 0.0976

    assert _score("accuracy", reference, reference, inverse=True) == 50
    assert _score("accuracy", 0.114, reference, inverse=True) == pytest.approx(44.4)
    assert _score("accuracy", 0.08, reference, inverse=True) > 50


def test_lower_comfort_accuracy_anchors_and_top_reference():
    windows = [(79.5 - 6 * 8, 1.0)]
    reference = _accuracy_expected(windows, 4.5)
    assert reference == pytest.approx(0.1, abs=1e-9)
    assert _accuracy_score(0.2, reference, 4.5) == 20
    assert _accuracy_score(0.1, reference, 4.5) == 50
    assert _accuracy_score(0, reference, 4.5) == 100
    assert _accuracy_score(0.234, reference, 4.5) == pytest.approx(13.2)

    row = {"score": _accuracy_score(0.234, reference, 4.5), "measured": 0.234, "od_windows": windows}
    assert at_level({"accuracy": row}, 10.0)["accuracy"] == 0


def test_higher_comfort_accuracy_keeps_previous_model():
    windows = [(79.5 - 6 * 8, 1.0)]
    for level in (5.5, 6.3, 10.0):
        reference = _accuracy_expected(windows, level)
        assert reference == pytest.approx(_accuracy_expected(windows, 5.5))
        assert _accuracy_score(0.114, reference, level) == _score("accuracy", 0.114, reference, inverse=True)


def test_reference_and_score_transition_smoothly_into_5_5_stars():
    windows = [(79.5 - 6 * 8, 1.0)]
    low = _accuracy_expected(windows, 4.5)
    middle = _accuracy_expected(windows, 5.0)
    high = _accuracy_expected(windows, 5.5)
    assert low > middle > high
    assert (
        abs(_accuracy_score(0.11, _accuracy_expected(windows, 5.4999), 5.4999) - _accuracy_score(0.11, high, 5.5))
        <= 0.1
    )


def test_slider_expectation_is_what_typical_maps_ask():
    """#54: the reference was 40 × 2^((★−6)/3), twice what a typical 6★ map's hardest sliders score, so players who
    don't break sliders were "not tested" whatever they played. Now 19 at 6★, growing like real slider speed."""
    from osu_coach.profile.domain.ratings import SLIDERS_AT_6, _expected

    assert _expected("sliders", 6.0) == pytest.approx(SLIDERS_AT_6) == pytest.approx(19.0)
    assert 1.05 < _expected("sliders", 7.0) / _expected("sliders", 6.0) < 1.3  # ~15% per ★, not 26%
    assert _expected("sliders", 8.0) < 30 < 40  # the old curve asked 63.5 at 8★
    assert _expected("sliders", 4.0) < _expected("sliders", 6.0) < _expected("sliders", 9.0)


def test_slider_control_scores_a_tenth_lower():
    """Slider control read about 10% too high for everyone: every slider score is 0.9× what its curve gives."""
    import math

    from osu_coach.profile.domain.ratings import _expected

    expected = _expected("sliders", 6.0)
    for value in (expected / 2, expected, expected * 1.6, expected * 20):
        raw = 50 + 25 * math.log2(value / expected)
        assert _score("sliders", value, expected) == pytest.approx(round(min(max(raw, 0), 100) * 0.9, 1))
    assert _score("aim", 17.5, 17.5) == 50  # the other skills are unchanged


def test_stamina_the_maps_never_tested_gets_a_lower_bound_and_what_to_play():
    """A player who held every note but never played a stretch as dense as their level expects has no stamina score
    (their limit is unknown), but at least the score the densest stretches show, and what to play to find it."""
    from osu_coach.library.repository import analyze_files
    from osu_coach.profile.domain import build_profile
    from osu_coach.profile.domain.ratings import ratings
    from tests.conftest import replay_and_map

    names = ["osrparse__resources__replay.osr", "mot1one__lazer_nm.osr"]  # no stretch as dense as 12★ expects
    p = build_profile([analyze_files(*replay_and_map(n)[:2]) for n in names], with_ratings=False)
    # every note held, at half the density: no stretch is as dense as a 12★ level expects
    O = p.objects.assign(head_hit=True, miss_reason=None, time=p.objects["time"] * 2)
    stamina = ratings(O, p.replays, 12.0)["stamina"]
    assert stamina["score"] is None
    assert 0 <= stamina["at_least"] < 50
    assert "below what your comfort level expects" in stamina["needs"]
