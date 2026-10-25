"""Setup Tips: a change only when it is big enough to feel and the misses show it costs you, with the exact values;
otherwise keep it."""

import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

from osu_coach.analysis.domain import along_cross
from osu_coach.library.repository import analyze_files
from osu_coach.profile.domain import aim_regression, build_profile
from osu_coach.settings.domain import Setup
from osu_coach.tips.domain import make_tips, mm_per_osu_px, setup_advice
from tests.conftest import replay_and_map

R = 36.5
AREA = dict(area_w_mm=100.0, area_h_mm=56.25, area_x_mm=76.0, area_y_mm=47.0)
SAYO = dict(
    keyboard="sayo",
    sayo_stroke_mm=4.0,
    sayo_trigger_mm=0.40,
    sayo_release_mm=0.35,
    sayo_rt=True,
    sayo_rt_trigger_mm=0.10,
    sayo_rt_release_mm=0.15,
    sayo_full_stroke=False,
    sayo_rt_upper_mm=0.10,
    sayo_rt_lower_mm=3.80,
)
CLEAN_KEYS = dict(press_count=50_000, chatter_per_1000=2.0, extra_presses_per_100=0.9, comfort_bpm=210)


@pytest.fixture(scope="module")
def base():
    names = ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr"]
    return build_profile([analyze_files(*replay_and_map(n)[:2]) for n in names])


def jumps(n=2000, scale=(1.0, 1.0), rotation=0.0, offset=(0.0, 0.0), noise=20.0, seed=1) -> pd.DataFrame:
    """Jumps in every direction, 2-6 circle widths long. The clicks land where the movement takes them: scaled per
    axis, turned ``rotation`` degrees clockwise, shifted by ``offset`` px, plus noise; beyond the circle = aim miss."""
    rng = np.random.default_rng(seed)
    ang = rng.uniform(0, 2 * np.pi, n)
    dist = rng.uniform(2, 6, n) * 2 * R
    mx, my = np.cos(ang) * dist, np.sin(ang) * dist
    sx, sy = 256 - mx / 2, 192 - my / 2
    th = math.radians(rotation)
    ax, ay = mx * scale[0], my * scale[1]
    rx, ry = ax * math.cos(th) - ay * math.sin(th), ax * math.sin(th) + ay * math.cos(th)
    ex = rx - mx + offset[0] + rng.normal(0, noise, n)
    ey = ry - my + offset[1] + rng.normal(0, noise, n)
    hit = np.hypot(ex, ey) <= R
    ac = [along_cross(a, b, c, d) for a, b, c, d in zip(ex, ey, mx, my)]
    return pd.DataFrame(
        {
            "played": True,
            "kind": "circle",
            "head_hit": hit,
            "miss_reason": np.where(hit, None, "aim"),
            "x": sx + mx,
            "y": sy + my,
            "start_x": sx,
            "start_y": sy,
            "err_dx": ex,
            "err_dy": ey,
            "radius": R,
            "dist_norm": dist / (2 * R),
            "along": [a / R for a, _ in ac],
            "cross": [c / R for _, c in ac],
            "w": 1.0,
        }
    )


def playing(base, O, **regression):
    """The base profile playing these jumps, with the aim calibration fitted on them (``regression`` overrides it)."""
    return dataclasses.replace(base, objects=O, regression={**aim_regression(O), **regression})


def advice(p, setup, key):
    return next(a for a in setup_advice(p, setup) if a.key == key)


def changes(a):
    return {c.setting: (c.now, c.to) for c in a.changes}


# ---------------------------------------------------------------- tablet area size / mouse sensitivity
def test_overaim_that_costs_misses_gives_the_exact_area(base):
    p = playing(base, jumps(scale=(1.06, 1.06)))
    a = advice(p, Setup(**AREA), "area_size")
    assert a.verdict == "change" and "overshoot" in a.why and "past the note" in a.why
    sx, sy = p.regression["scale_x"], p.regression["scale_y"]
    assert changes(a) == {
        "Area width": ("100 mm", f"{100 * sx:.1f} mm"),
        "Area height": ("56.25 mm", f"{56.25 * sy:.1f} mm"),
    }
    assert 105.0 < 100 * sx < 107.0


def test_one_axis_off_changes_only_that_side(base):
    p = playing(base, jumps(scale=(1.07, 1.0)))
    a = advice(p, Setup(**AREA), "area_size")
    assert a.verdict == "change" and list(changes(a)) == ["Area width"] and "sideways" in a.why


def test_a_movement_within_the_feel_is_kept(base):
    a = advice(playing(base, jumps(scale=(1.01, 0.99))), Setup(**AREA), "area_size")
    assert a.verdict == "keep" and a.why.startswith("You land on the notes") and not a.changes


def test_a_misscale_the_misses_dont_show_is_kept(base):
    """The fit says 6% too far, but the misses land short as often as past: it doesn't cost anything, keep it."""
    p = playing(base, jumps(), scale_x=1.06, scale_y=1.06)
    a = advice(p, Setup(**AREA), "area_size")
    assert a.verdict == "keep" and "short as often as past" in a.why


def test_without_the_area_the_change_is_a_direction(base):
    a = advice(playing(base, jumps(scale=(0.93, 0.93))), Setup(), "area_size")
    assert a.verdict == "change" and "fall short" in a.why
    assert changes(a)["Area width"] == (None, "7% smaller") and "Enter your area" in a.where


def test_mouse_underaim_gives_the_sensitivity_and_dpi(base):
    p = playing(base, jumps(scale=(0.94, 0.94)))
    a = advice(p, Setup(device="mouse", mouse_dpi=800, ingame_sens=1.0), "sensitivity")
    scale = (p.regression["scale_x"] + p.regression["scale_y"]) / 2
    assert a.verdict == "change"
    assert changes(a) == {
        "osu! sensitivity": ("1.00", f"{1 / scale:.2f}"),
        "or mouse DPI": ("800", str(int(round(800 / scale / 50) * 50))),
    }
    # a mouse can't be moved or turned in a setting
    assert {x.key for x in setup_advice(p, Setup(device="mouse"))} == {"sensitivity", "offset", "keys"}


def test_too_few_jumps_says_so(base):
    out = setup_advice(playing(base, jumps(n=100)), Setup())
    a = next(x for x in out if x.key == "area_size")
    assert a.verdict == "unknown" and "Not enough jumps" in a.why


# ---------------------------------------------------------------- tablet area position and rotation
def test_a_click_offset_moves_the_area_by_exact_millimetres(base):
    p = playing(base, jumps(offset=(8.0, -4.0)))
    s = Setup(**AREA)
    a = advice(p, s, "area_position")
    mm_x, mm_y = mm_per_osu_px(s)
    ox, oy = p.regression["offset_x"], p.regression["offset_y"]
    assert a.verdict == "change" and "right" in a.why
    assert changes(a) == {
        "Area X": ("76 mm", f"{76 + ox * mm_x:.1f} mm"),  # clicks land right → the area moves right
        "Area Y": ("47 mm", f"{47 + oy * mm_y:.1f} mm"),
    }


def test_centred_clicks_keep_the_area_where_it_is(base):
    a = advice(playing(base, jumps(offset=(1.0, 0.5))), Setup(**AREA), "area_position")
    assert a.verdict == "keep" and a.why == "Your clicks are centred on the notes."


def test_a_turned_movement_turns_the_area(base):
    a = advice(playing(base, jumps(rotation=4.0)), Setup(**AREA), "area_rotation")
    assert a.verdict == "change" and changes(a) == {"Area rotation": (None, "turn it 4° clockwise")}
    a = advice(playing(base, jumps(rotation=-4.0)), Setup(**AREA), "area_rotation")
    assert changes(a) == {"Area rotation": (None, "turn it 4° counter-clockwise")}
    assert advice(playing(base, jumps(rotation=0.3)), Setup(**AREA), "area_rotation").verdict == "keep"


# ---------------------------------------------------------------- audio offset
def timing(base, errors, ur=150.0):
    plays = pd.DataFrame({"mean_error": errors, "n300": 300, "n100": 20, "n50": 0, "od": 8.0})
    return dataclasses.replace(base, replays=plays, tapping={**base.tapping, "ur_single": ur})


def test_the_same_bias_on_every_map_is_the_offset(base):
    p = timing(base, [8.0 + d for d in np.linspace(-2, 2, 20)])
    a = advice(p, Setup(client="lazer"), "offset")
    assert a.verdict == "change" and "8 ms late" in a.why and "more 300s" in a.why
    assert changes(a) == {"Audio offset": (None, "8 ms lower")}  # lazer: its offset minus your average error
    a = advice(timing(base, [-8.0] * 20), Setup(client="lazer"), "offset")
    assert changes(a) == {"Audio offset": (None, "8 ms higher")}
    a = advice(p, Setup(client="stable"), "offset")
    assert "Offset wizard" in a.where


def test_a_bias_that_changes_from_map_to_map_is_timing(base):
    a = advice(timing(base, [10.0] * 12 + [-4.0] * 8), Setup(), "offset")
    assert a.verdict == "keep" and "not on every map" in a.why
    # and the Tips page talks about it as timing
    t = next(
        t
        for t in make_tips(
            dataclasses.replace(
                timing(base, [10.0] * 12 + [-4.0] * 8), tapping={**base.tapping, "mean_error": 8.0, "ur_single": 150.0}
            ),
            Setup(),
        )
        if "on average" in t.title
    )
    assert "not the same on every map" in t.evidence


def test_centred_hits_keep_the_offset(base):
    a = advice(timing(base, [1.0, -1.0] * 10), Setup(), "offset")
    assert a.verdict == "keep" and a.why.startswith("Your hits are centred")
    assert advice(timing(base, [5.0] * 5), Setup(), "offset").verdict == "unknown"


# ---------------------------------------------------------------- keys
def keys(base, **tapping):
    return dataclasses.replace(
        base,
        tapping={**base.tapping, **CLEAN_KEYS, **tapping},
        sliders={**base.sliders, "sliders": 20_000},
        slider_breaks={"follow": 52, "released": 8, "key_swap": 2},
    )


def test_keys_that_fit_are_kept(base):
    """The old rule changed RT Lower Bound 4.00 → 3.95 mm on any setup: no more changes the replays don't ask for."""
    a = advice(keys(base), Setup(**{**SAYO, "sayo_rt_lower_mm": 4.0}), "keys")
    assert a.verdict == "keep" and not a.changes


def test_double_presses_make_rapid_trigger_less_sensitive(base):
    a = advice(keys(base, chatter_per_1000=9.0), Setup(**SAYO), "keys")
    assert a.verdict == "change" and "fire twice" in a.why
    assert changes(a) == {
        "RT Trigger": ("0.10 mm", "0.15 mm"),
        "RT Release": ("0.15 mm", "0.20 mm"),
        "RT Upper Bound": ("0.10 mm", "0.40 mm"),  # rapid trigger no longer fires above the trigger point
    }


def test_keys_letting_go_mid_slider_raise_rt_release(base):
    p = dataclasses.replace(keys(base), slider_breaks={"released": 40, "follow": 20})
    a = advice(p, Setup(**SAYO), "keys")
    assert changes(a) == {"RT Release": ("0.15 mm", "0.20 mm")} and "let go mid-slider" in a.why
    # a few such breaks in many sliders are nothing to change
    p = dataclasses.replace(keys(base), slider_breaks={"released": 11, "follow": 67}, sliders={"sliders": 55_000})
    assert advice(p, Setup(**SAYO), "keys").verdict == "keep"


def test_values_the_device_cant_work_with_are_fixed(base):
    a = advice(keys(base), Setup(**{**SAYO, "sayo_rt_trigger_mm": 0.30, "sayo_rt_release_mm": 0.20}), "keys")
    assert changes(a)["RT Trigger"] == ("0.30 mm", "0.20 mm") and "can't be larger" in a.why
    a = advice(keys(base), Setup(**{**SAYO, "sayo_release_mm": 0.45}), "keys")
    assert changes(a)["Release"] == ("0.45 mm", "0.35 mm")


def test_rt_trigger_never_ends_above_rt_release(base):
    for trig, rel in ((0.1, 0.1), (0.1, 0.05), (0.25, 0.25), (0.1, 0.4)):
        a = advice(
            keys(base, chatter_per_1000=9.0),
            Setup(**{**SAYO, "sayo_rt_trigger_mm": trig, "sayo_rt_release_mm": rel}),
            "keys",
        )
        new = changes(a)
        t, r = float(new["RT Trigger"][1].split()[0]), float(new["RT Release"][1].split()[0])
        assert t <= r, (trig, rel, new)


def test_unknown_values_get_a_direction(base):
    a = advice(keys(base, chatter_per_1000=9.0), Setup(keyboard="sayo"), "keys")
    assert changes(a)["RT Trigger"] == (None, "0.05 mm higher") and "Enter your current values" in a.where


def test_rapid_trigger_and_plain_keyboards(base):
    a = advice(
        keys(base, chatter_per_1000=9.0),
        Setup(keyboard="rapid_trigger", actuation_mm=0.4, rt_press_mm=0.1, rt_release_mm=0.1),
        "keys",
    )
    assert changes(a) == {"Rapid-trigger sensitivity": ("0.10 mm", "0.20 mm"), "Actuation point": ("0.4 mm", "0.6 mm")}
    assert advice(keys(base, chatter_per_1000=6.0), Setup(), "keys").verdict == "keep"  # a plain switch: from 8
    a = advice(keys(base, chatter_per_1000=9.0), Setup(), "keys")
    assert a.verdict == "change" and changes(a) == {"Switch": (None, "clean it, or try other keys")}


# ---------------------------------------------------------------- the page
def test_changes_come_first_and_the_tips_have_no_setup_left(base):
    p = keys(playing(base, jumps(offset=(8.0, -4.0))), chatter_per_1000=9.0)
    out = setup_advice(p, Setup(**AREA, **{k: v for k, v in SAYO.items()}))
    verdicts = [a.verdict for a in out]
    assert verdicts == sorted(verdicts, key=["change", "unknown", "keep"].index)
    assert {a.key for a in out if a.verdict == "change"} == {"area_position", "keys"}
    categories = {t.category for t in make_tips(p, Setup(**AREA, **SAYO))}
    assert not categories & {
        "Setup / aim calibration",
        "Tablet area",
        "Mouse sensitivity",
        "Keys / SayoDevice",
        "Keyboard / Rapid trigger",
    }
