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
