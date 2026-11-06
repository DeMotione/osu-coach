"""The IRT engine: states, the tested-difficulty cap, the comfort stand-in and the 0–100 adapter."""

import dataclasses
import datetime as dt

import numpy as np
import pytest

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.player.engines.irt import constants as K
from osu_coach.domain.player.engines.irt.engine import IrtEngine, adapter, prior_centre, state_of
from osu_coach.domain.player.engines.irt.fit import SkillFit
from tests.domain.player.engines.irt.helpers import simulate


@dataclasses.dataclass
class Play:  # what the engine reads of a PlaySummary
    meta: ReplayMeta
    irt: object


def plays(groups_list, stars=6.0):
    day = dt.datetime(2026, 9, 1)
    return [
        Play(ReplayMeta(key=f"k{i}", beatmap_md5=f"m{i}", stars=stars, date=day - dt.timedelta(hours=i)), g)
        for i, g in enumerate(groups_list)
    ]


def test_adapter_is_twenty_points_a_star_and_never_100():
    assert adapter(6.0, 6.0) == 50
    assert adapter(6.25, 6.0) - adapter(5.75, 6.0) == pytest.approx(10, abs=0.2)  # 20 points a star around 50
    assert 90 < adapter(9.0, 6.0) < 93 and adapter(20.0, 6.0) == 99 and adapter(-8.0, 6.0) == 1
    assert adapter(7.0, 6.0) + adapter(5.0, 6.0) == pytest.approx(100)


def test_states():
    assert state_of(SkillFit(6.0, 0.2, 500, 7.0)) == "measured"
    assert state_of(SkillFit(6.0, 0.5, 500, 7.0)) == "provisional"
    assert state_of(SkillFit(6.0, 0.2, 500, 7.0, modes=(5.5, 6.0))) == "provisional"
    assert state_of(SkillFit(7.5, 0.2, 500, 7.0)) == "untested"
    assert state_of(SkillFit(6.0, 0.9, 500, 7.0)) == "not_enough_data"
    assert state_of(SkillFit(6.0, 0.2, 0, 7.0)) == "not_enough_data"


def test_the_engine_rates_every_skill_in_stars():
    rated = IrtEngine().rate(plays([simulate(seed=s) for s in range(4)]), [], comfort=6.0)
    assert rated.engine == "irt" and rated.reference == 6.0
    assert list(rated.skills) == [
        "aim",
        "flow_aim",
        "speed",
        "stamina",
        "accuracy",
        "sliders",
        "reading",
        "consistency",
    ]
    aim = rated.skills["aim"]
    assert aim.state in ("measured", "provisional") and aim.score == adapter(aim.measured, 6.0)
    assert aim.stars_low < aim.stars < aim.stars_high and aim.natural_unit == "d/s"


def test_farming_easy_maps_shows_at_least_what_was_held():
    groups = simulate()
    aim_rows = np.isfinite(groups.b_aim)
    easy = groups.take(~aim_rows | (groups.b_aim <= 5.0))  # aim notes far below the limit only, all held
    aim_rows = np.isfinite(easy.b_aim)
    easy = easy.replace(**{c: np.where(aim_rows, 0.0, getattr(easy, c)) for c in ("f_a", "f_b", "f_t")})
    aim = IrtEngine().rate(plays([easy] * 50), [], comfort=6.0).skills["aim"]
    # held everything, all of it easy: a low lower bound, never the fitted value above it
    assert aim.state in ("untested", "not_enough_data")
    if aim.state == "untested":  # a lower bound from what was held, never a high score from easy notes
        assert aim.score == aim.at_least <= 60


def test_without_a_comfort_level_the_prior_has_a_stand_in():
    metas = [ReplayMeta(key=f"k{i}", beatmap_md5="m", stars=s) for i, s in enumerate((4.0, 5.0, 6.0))]
    assert np.isfinite(prior_centre(metas, None))
    assert prior_centre([], None) == 4.0 and prior_centre(metas, 6.5) == 6.5
    rated = IrtEngine().rate(plays([simulate()]), [], comfort=None)
    assert rated.reference == 4.0 and any(r.score is not None for r in rated.skills.values())


def test_comparing_with_harder_maps_lowers_every_score():
    rated = IrtEngine().rate(plays([simulate(seed=s) for s in range(3)]), [], comfort=6.0)
    at = IrtEngine().compare_at(rated, 6.0, 7.0)
    for k, v in at.skills.items():
        if v is not None:
            assert v.score == adapter(rated.skills[k].measured, 7.0), k
            assert v.score < rated.skills[k].score, k


def test_a_skill_never_held_gets_no_number():
    # every head note failed (all aim misses): tapping has no tested difficulty, so it must not show a high value
    groups = simulate()
    heads = groups.kind == K.HEAD
    failed = groups.replace(
        f_a=np.where(heads, groups.n, groups.f_a),
        f_b=np.where(heads, 0.0, groups.f_b),
        f_t=np.where(heads, 0.0, groups.f_t),
    )
    rated = IrtEngine().rate(plays([failed]), [], comfort=6.0)
    for key in ("aim", "speed", "stamina", "flow_aim", "reading"):
        row = rated.skills[key]
        assert row.score is None and row.state in ("not_enough_data", "failed"), (key, row.state, row.stars)
        assert row.at_least is None  # nothing held: no bound either


def test_many_easy_notes_dont_lower_the_tested_difficulty():
    # the spec's §7 player: lots of easy jumps and fewer hard ones, all fitted near 6.6★ aim; held hard notes count
    groups = simulate()
    aim = np.isfinite(groups.b_aim)
    bulk = groups.replace(
        n=np.where(aim & (groups.b_aim < 6.0), groups.n * 20, groups.n),
        f_a=np.where(aim & (groups.b_aim < 6.0), groups.f_a * 20, groups.f_a),
        f_b=np.where(aim & (groups.b_aim < 6.0), groups.f_b * 20, groups.f_b),
        f_t=np.where(aim & (groups.b_aim < 6.0), groups.f_t * 20, groups.f_t),
    )
    row = IrtEngine().rate(plays([bulk]), [], comfort=6.0).skills["aim"]
    assert row.state in ("measured", "provisional"), (row.state, row.stars, row.tested_demand)


def test_an_untested_skill_keeps_its_lower_bound_at_every_star_rating():
    groups = simulate()
    aim_rows = np.isfinite(groups.b_aim)
    easy = groups.take(~aim_rows | (groups.b_aim <= 5.0))
    aim_rows = np.isfinite(easy.b_aim)
    easy = easy.replace(**{c: np.where(aim_rows, 0.0, getattr(easy, c)) for c in ("f_a", "f_b", "f_t")})
    engine = IrtEngine()
    rated = engine.rate(plays([easy] * 50), [], comfort=6.0)
    if rated.skills["aim"].state != "untested":
        pytest.skip("aim isn't untested on this simulation")
    held = rated.skills["aim"].stars
    for target in (5.0, 6.0, 7.0):
        at = engine.compare_at(rated, 6.0, target).skills["aim"]
        assert at.score == at.at_least == adapter(held, target)


def test_calibration_puts_each_skills_50_where_it_fails_its_anchor_share():
    from osu_coach.domain.player.engines.irt.engine import _fail_share, calibration
    from osu_coach.domain.player.engines.irt.merge import merge

    groups = simulate()
    merged = merge([(p.meta, p.irt) for p in plays([groups, simulate(seed=2)], stars=6.0)])
    refs = calibration(merged, 6.0)
    for i, k in enumerate(K.SKILLS):
        rows = groups.take(groups.kind != K.TIMING)
        b = getattr(rows, f"b_{k}")
        ok = np.isfinite(b)
        share = _fail_share(refs[k], b[ok], rows.n[ok], float(K.A[i]), K.C)
        assert share == pytest.approx(1 - K.PI, abs=1e-4), k
        assert adapter(refs[k], refs[k]) == 50
    # the maps' content alone sets it: the same maps played better or worse give the same references
    better = groups.replace(f_a=groups.f_a * 0, f_b=groups.f_b * 0, f_t=groups.f_t * 0)
    assert calibration(merge([(p.meta, p.irt) for p in plays([better, simulate(seed=2)])]), 6.0) == pytest.approx(refs)
