import dataclasses

import pytest

from osu_coach.domain.advice import Setup, make_tips, mm_per_osu_px, practice_plan, rt_baseline, suggest_tablet_area
from osu_coach.domain.analysis import analyze_files
from osu_coach.domain.profile import build_profile
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


AREA = dict(area_w_mm=100.0, area_h_mm=56.25, area_x_mm=76.0, area_y_mm=47.0)


def _aim_misses_in(base, pattern: str, spaced: bool = False, n: int = 200):
    """The base profile with its misses replaced by n aim misses on notes of one pattern (jumps at normal speed,
    or streams — where they count as speed-aim misses)."""
    from osu_coach.domain.profile import miss_causes
    O = base.objects.copy()
    O["head_hit"] = True
    O["miss_reason"] = None
    idx = O.index[O["played"].astype(bool) & (O["kind"] != "spinner")][:n]
    O.loc[idx, "head_hit"] = False
    O.loc[idx, "miss_reason"] = "aim"
    O.loc[idx, "pattern"] = pattern
    O.loc[idx, "spaced_stream"] = spaced
    O.loc[idx, "run_len"] = 12 if pattern in ("stream", "burst") else 1
    O.loc[idx, "dt_real"] = 60.0 if pattern in ("stream", "burst") else 300.0
    O["miss_cause"] = miss_causes(O)
    counts = O.loc[idx, "miss_cause"].value_counts().to_dict()
    return with_(base, objects=O, miss_breakdown={**counts, "lost": 5})


def test_aim_misses_in_streams_are_speed_aim(base):
    t = tip(make_tips(_aim_misses_in(base, "stream")), "Overview", "speed-aim misses")
    assert t is not None and "streams, bursts or very fast jumps" in t.evidence
    assert any("Flow aim (spaced streams)" in a for a in t.actions)
    assert tip(make_tips(_aim_misses_in(base, "stream")), "Overview", "Most misses are aim misses") is None


def test_aim_miss_tip_keeps_jump_advice_for_jumps(base):
    t = tip(make_tips(_aim_misses_in(base, "jump")), "Overview", "aim misses")
    assert t is not None and "jumps 100%" in t.actions[0]
    assert any("Jump aim" in a for a in t.actions)


def test_calibration_tip_is_always_in_the_setup_tips(base):
    t = tip(make_tips(with_(base, regression={**REG, "scale_x": 1.0, "scale_y": 1.01}), Setup(**AREA)),
            "Setup / aim calibration", "fits")
    assert t is not None and "keep your tablet area" in " ".join(t.actions)
    t = tip(make_tips(with_(base, regression={**REG, "scale_x": 1.08, "scale_y": 1.08}), Setup(**AREA)),
            "Setup / aim calibration", "larger tablet area")
    assert t is not None and t.actions[0] == "Now 100 × 56.25 mm → try 108.0 × 60.8 mm."
    t = tip(make_tips(with_(base, regression={**REG, "scale_x": 0.9, "scale_y": 0.9}),
                      Setup(device="mouse", mouse_dpi=800, ingame_sens=1.0)), "Setup / aim calibration", "higher")
    assert t is not None and "raise your sensitivity" in " ".join(t.actions)


# ---------------------------------------------------------------- tablet area position (X / Y)


def test_area_position_follows_a_sizeable_click_offset(base):
    p = with_(base, regression={**REG, "offset_x": 8.0, "offset_y": -4.0, "offset_se": 0.2})
    s = Setup(**AREA)
    a = suggest_tablet_area(p, s)
    mm_x, mm_y = mm_per_osu_px(s)
    # clicks land right/up of the centre -> move the area the same way
    assert a["x"] == pytest.approx(76.0 + 8.0 * mm_x, abs=0.05)
    assert a["y"] == pytest.approx(47.0 - 4.0 * mm_y, abs=0.05)
    assert a["changed"]
    t = tip(make_tips(p, s), "Tablet area", "off-centre")
    assert t.settings["area_x_mm"] == a["x"] and t.settings["area_y_mm"] == a["y"]


def test_centred_clicks_keep_the_area_position(base):
    p = with_(base, regression={**REG, "offset_x": -0.76, "offset_y": 0.49, "offset_se": 0.06})
    a = suggest_tablet_area(p, Setup(**AREA))
    assert (a["x"], a["y"], a["w"], a["h"]) == (76.0, 47.0, 100.0, 56.25)
    assert not a["changed"] and any("centred" in w for w in a["why"])


def test_area_suggestion_combines_size_and_position(base):
    p = with_(base, regression={**REG, "scale_x": 1.10, "scale_y": 1.10, "offset_x": 8.0, "offset_se": 0.2})
    a = suggest_tablet_area(p, Setup(**AREA))
    assert a["w"] > 100.0 and a["h"] > 56.25 and a["x"] > 76.0 and a["y"] == 47.0


def test_no_area_suggestion_without_an_area_or_with_a_mouse(base):
    p = with_(base, regression={**REG, "offset_x": 8.0, "offset_se": 0.2})
    assert suggest_tablet_area(p, Setup()) is None
    assert suggest_tablet_area(p, Setup(device="mouse", **AREA)) is None


# ---------------------------------------------------------------- SayoDevice keypad
# Nikita's settings (SayoDevice web configurator screenshot)
SAYO = dict(keyboard="sayo", sayo_stroke_mm=4.0, sayo_trigger_mm=0.40, sayo_release_mm=0.35, sayo_rt=True,
            sayo_rt_trigger_mm=0.10, sayo_rt_release_mm=0.15, sayo_full_stroke=False, sayo_rt_upper_mm=0.10,
            sayo_rt_lower_mm=3.80)
CLEAN = dict(chatter_per_1000=2.0, extra_presses_per_100=0.9, overlap_in_streams=0.43, slope_ms_per_note=0.05,
             comfort_bpm=210)


def _clean(base, **kw):
    p = _tapping(base, **{**CLEAN, **kw})
    return with_(p, slider_breaks={"follow": 52, "released": 8, "key_swap": 2},
                 miss_breakdown={"aim": 2288, "lost": 709, "no_tap": 383, "early": 61})


def _sayo(p, **setup):
    return tip(make_tips(p, Setup(**{**SAYO, **setup})), "Keys / SayoDevice")


def test_sayo_settings_that_fit_the_tapping_are_kept(base):
    t = _sayo(_clean(base))
    assert {k: t.settings[k] for k in ("Trigger", "Release", "RT Trigger", "RT Release", "RT Upper Bound",
                                       "RT Lower Bound")} == {"Trigger": 0.40, "Release": 0.35, "RT Trigger": 0.10,
                                                              "RT Release": 0.15, "RT Upper Bound": 0.10,
                                                              "RT Lower Bound": 3.80}
    assert t.severity == 1 and "fit" in t.title.lower()


def test_sayo_double_presses_make_rapid_trigger_less_sensitive(base):
    t = _sayo(_clean(base, chatter_per_1000=9.0))
    assert t.settings["RT Trigger"] == 0.15 and t.settings["RT Release"] == 0.20
    assert t.settings["RT Upper Bound"] == 0.40      # rapid trigger no longer fires above the trigger point
    assert t.severity == 2


def test_sayo_early_releases_in_sliders_raise_rt_release(base):
    p = with_(_clean(base), slider_breaks={"released": 12, "follow": 8})
    t = _sayo(p)
    assert t.settings["RT Release"] == 0.20 and t.settings["RT Trigger"] == 0.10


def test_sayo_falling_behind_in_streams_makes_presses_register_sooner(base):
    t = _sayo(_clean(base, slope_ms_per_note=1.2), sayo_rt_trigger_mm=0.25)
    assert t.settings["RT Trigger"] == 0.20


def test_sayo_impossible_settings_are_fixed(base):
    t = _sayo(_clean(base), sayo_release_mm=0.45, sayo_rt_lower_mm=4.0)
    assert t.settings["Release"] == 0.35             # must be shallower than Trigger 0.40
    assert t.settings["RT Lower Bound"] == 3.95      # not at the very bottom of the stroke
    text = " ".join(t.actions)
    assert "Release" in text and "RT Lower Bound" in text


def test_sayo_rt_trigger_never_above_rt_release(base):
    # keys overlap -> RT Release lower; RT Trigger must follow it down
    t = _sayo(_clean(base, overlap_in_streams=0.7), sayo_rt_trigger_mm=0.20, sayo_rt_release_mm=0.20)
    assert t.settings["RT Release"] == 0.15 and t.settings["RT Trigger"] <= t.settings["RT Release"]
    # falling behind -> RT Trigger lower stays valid; an entered Trigger > Release is fixed and reported
    t = _sayo(_clean(base), sayo_rt_trigger_mm=0.30, sayo_rt_release_mm=0.20)
    assert t.settings["RT Trigger"] <= t.settings["RT Release"]
    assert "must not be larger than RT Release" in " ".join(t.actions)
    for kw in ({}, {"slope_ms_per_note": 1.2}, {"overlap_in_streams": 0.9}, {"chatter_per_1000": 9.0}):
        for trig, rel in ((0.1, 0.1), (0.3, 0.1), (0.1, 0.4), (0.25, 0.25)):
            t = _sayo(_clean(base, **kw), sayo_rt_trigger_mm=trig, sayo_rt_release_mm=rel)
            assert t.settings["RT Trigger"] <= t.settings["RT Release"], (kw, trig, rel)


def test_sayo_without_values_gives_a_starting_point(base):
    t = tip(make_tips(_clean(base), Setup(keyboard="sayo")), "Keys / SayoDevice")
    assert t.settings["RT Mode"] is True and 0.1 <= t.settings["RT Trigger"] <= 0.3
    assert t.settings["RT Upper Bound"] == t.settings["Trigger"]
    assert t.settings["RT Lower Bound"] == round(t.settings["Stroke"] - 0.05, 2)


def test_keyboard_users_get_no_sayo_tip(base):
    tips = make_tips(_clean(base, chatter_per_1000=9.0), Setup(keyboard="standard"))
    assert tip(tips, "Keys / SayoDevice") is None
