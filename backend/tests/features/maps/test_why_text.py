"""The "Why this map" text: settings read as the table shows them, also at a rate other than 1."""

from osu_coach.common.texts import why
from osu_coach.domain.maps.suggestions import Targets


def test_od_and_ar_at_a_custom_rate_have_one_decimal():
    targets = Targets(comfort=6.0)
    assert why({"od": 9.55435, "circle_share": 1.0}, "accuracy", targets) == "OD 9.6, 100% circles"
    assert why({"od": 8.0, "circle_share": 0.84}, "accuracy", targets) == "OD 8, 84% circles"
    assert why({"ar": 10.13333, "density_p90": 7.2}, "reading", targets) == "AR 10.1, up to 7 notes on screen"
