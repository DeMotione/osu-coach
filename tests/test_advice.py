import dataclasses

import pytest

from osu_coach.advice import Setup, make_tips, practice_plan, rt_baseline
from osu_coach.analysis import analyze_files
from osu_coach.profile import build_profile
from tests.conftest import replay_and_map

REG = {"n": 500, "scale_x": 1.0, "scale_y": 1.0, "rotation_deg": 0.0, "offset_x": 0.0, "offset_y": 0.0,
       "offset_se": 0.3, "residual_px": 15.0, "radius": 36.5}


@pytest.fixture(scope="module")
def base():
    names = ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr"]
    return build_profile([analyze_files(*replay_and_map(n)[:2]) for n in names])


def with_(p, **kw):
    return dataclasses.replace(p, **kw)


def tip(tips, category, word=""):
    found = [t for t in tips if t.category == category and word.lower() in t.title.lower()]
    return found[0] if found else None


def test_overaim_on_tablet_suggests_larger_area_in_mm(base):
    p = with_(base, regression={**REG, "scale_x": 1.10, "scale_y": 1.10})
    t = tip(make_tips(p, Setup(device="tablet", area_w_mm=100, area_h_mm=56.25)), "Tablet area", "overaim")
    assert t is not None and t.severity == 3
    assert t.settings["area_mm"] == [110.0, 61.9]


def test_underaim_with_mouse_suggests_higher_dpi(base):
    p = with_(base, regression={**REG, "scale_x": 0.90, "scale_y": 0.90})
    t = tip(make_tips(p, Setup(device="mouse", mouse_dpi=800)), "Mouse sensitivity")
    assert t is not None
    assert t.settings["mouse_dpi"] == 900


def test_accurate_scale_gives_no_area_tip(base):
    p = with_(base, regression={**REG, "scale_x": 1.02, "scale_y": 0.99})
    tips = make_tips(p, Setup(device="tablet", area_w_mm=100, area_h_mm=56.25))
    assert tip(tips, "Tablet area", "overaim") is None
    assert tip(tips, "Tablet area", "underaim") is None


def test_rotation_tip_reports_direction(base):
    p = with_(base, regression={**REG, "rotation_deg": 5.0})
    t = tip(make_tips(p, Setup()), "Tablet area", "rotated")
    assert t is not None and "clockwise" in t.title and "counter" not in t.title
    assert t.settings["rotation_deg"] == 5.0


def test_tiny_offset_is_not_reported(base):
    p = with_(base, regression={**REG, "offset_x": -3.0, "offset_y": 0.0, "offset_se": 0.2})
    assert tip(make_tips(p, Setup()), "Tablet area", "off-centre") is None


def test_large_offset_gives_shift_in_mm(base):
    p = with_(base, regression={**REG, "offset_x": -8.0, "offset_y": 0.0, "offset_se": 0.2})
    t = tip(make_tips(p, Setup(area_w_mm=100, area_h_mm=56.25)), "Tablet area", "off-centre")
    assert t is not None
    dx_mm, dy_mm = t.settings["area_shift_mm"]
    # 1920x1080 screen, playfield 864 px high -> 2.25 screen px per osu!px; 100 mm / 1920 px
    assert dx_mm == pytest.approx(-8 * 2.25 * 100 / 1920, abs=0.05)
    assert dy_mm == pytest.approx(0.0, abs=0.05)


def _quadrant(significant):
    return {"quadrant": "bottom-right", "miss_rate": 0.1, "rest_miss_rate": 0.04, "relative_risk": 2.5, "z": 5.0,
            "objects": 900, "misses": 90, "mean_dx": -6.0, "mean_dy": -5.0, "along": -0.2, "aim_miss_rate": 0.08,
            "significant": significant}


def test_significant_weak_quadrant_is_top_priority(base):
    tips = make_tips(with_(base, worst_quadrant=_quadrant(True)), Setup(device="tablet", handedness="right"))
    t = tip(tips, "Quadrant")
    assert t.severity == 3 and "BOTTOM-RIGHT" in t.title
    text = " ".join(t.actions)
    assert "short" in text            # clicks land towards the middle -> not reaching the corner
    assert "nearest your hand" in text


def test_noisy_weak_quadrant_is_low_priority(base):
    t = tip(make_tips(with_(base, worst_quadrant=_quadrant(False)), Setup()), "Quadrant")
    assert t.severity == 1


def _tapping(base, **kw):
    return with_(base, tapping={**base.tapping, **kw})


def test_rapid_trigger_chatter_makes_settings_less_sensitive(base):
    p = _tapping(base, chatter_per_1000=12.0, comfort_bpm=200, extra_presses_per_100=1.0)
    s = Setup(keyboard="rapid_trigger", actuation_mm=0.4, rt_press_mm=0.1, rt_release_mm=0.1)
    t = tip(make_tips(p, s), "Keyboard / Rapid trigger")
    assert t.settings["rt_sensitivity_mm"] > 0.1
    assert t.settings["actuation_mm"] > 0.4


def test_rapid_trigger_falling_behind_lowers_actuation(base):
    p = _tapping(base, chatter_per_1000=0.0, extra_presses_per_100=0.5, slope_ms_per_note=1.2, n=500,
                 comfort_bpm=180)
    s = Setup(keyboard="rapid_trigger", actuation_mm=1.2, rt_press_mm=0.3, rt_release_mm=0.3)
    t = tip(make_tips(p, s), "Keyboard / Rapid trigger")
    assert t.settings["actuation_mm"] < 1.2


def test_rt_baseline_gets_more_sensitive_with_speed():
    slow, fast = rt_baseline(150), rt_baseline(240)
    assert fast["actuation_mm"][1] < slow["actuation_mm"][0]
    assert fast["rt_mm"][1] < slow["rt_mm"][0]


def test_mouse_buttons_tip_points_to_the_right_client_setting(base):
    p = _tapping(base, mouse_button_share=0.6)
    t = tip(make_tips(p, Setup(client="lazer")), "Tapping", "mouse")
    assert t is not None and "lazer" in " ".join(t.actions)


def test_tips_are_sorted_and_have_evidence(base):
    tips = make_tips(base, Setup())
    assert tips, "a real profile should always produce some advice"
    assert [t.severity for t in tips] == sorted([t.severity for t in tips], reverse=True)
    for t in tips:
        assert t.evidence and t.category != "Internal", t


def test_practice_plan_names_weakest_skill(base):
    plan = practice_plan(base)
    label = base.skills[base.weaknesses[0]]["label"] if base.weaknesses else "your weakest skill"
    assert any(label in step for step in plan)
