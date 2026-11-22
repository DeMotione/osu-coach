import dataclasses
from dataclasses import asdict, fields

import pytest

from osu_coach.domain.player.setup import CHECKED_BY, Setup, changed_groups


def test_defaults_describe_a_right_handed_tablet_player_on_stable():
    s = Setup()
    assert (s.device, s.handedness, s.keyboard, s.client) == ("tablet", "right", "standard", "stable")
    assert (s.screen_w_px, s.screen_h_px) == (1920, 1080)


def test_everything_the_player_has_to_enter_is_unset_by_default():
    entered = {"device", "handedness", "keyboard", "client", "screen_w_px", "screen_h_px"}
    unset = [f.name for f in fields(Setup) if f.name not in entered and getattr(Setup(), f.name) is not None]
    assert unset == []


def test_fields_given_by_name_override_the_defaults_and_the_rest_stay():
    s = Setup(device="mouse", mouse_dpi=800, ingame_sens=1.2, sayo_rt=True)
    assert (s.device, s.mouse_dpi, s.ingame_sens, s.sayo_rt) == ("mouse", 800, 1.2, True)
    assert s.handedness == "right" and s.area_w_mm is None


def test_a_value_replaced_by_another_changes_its_group_of_checks():
    """#131: the checks of a changed group wait for plays made with the new value."""
    old = Setup(keyboard="sayo", sayo_rt_trigger_mm=0.15, area_w_mm=100.0)
    assert changed_groups(old, dataclasses.replace(old, sayo_rt_trigger_mm=0.2)) == {"keys"}
    assert changed_groups(old, dataclasses.replace(old, area_w_mm=90.0, keyboard="standard")) == {"aim", "keys"}
    # a value entered where there was none, or cleared: the setup described, not changed
    assert changed_groups(old, dataclasses.replace(old, sayo_rt_release_mm=0.2, area_w_mm=None)) == set()
    assert changed_groups(old, dataclasses.replace(old, client="lazer", handedness="left")) == set()


def test_every_setting_is_read_by_a_group_of_checks_or_by_none():
    grouped = [n for names in CHECKED_BY.values() for n in names]
    assert len(grouped) == len(set(grouped))
    assert set(grouped) | {"handedness", "client"} == {f.name for f in fields(Setup)}


def test_instances_do_not_share_state():
    a, b = Setup(), Setup()
    a.device = "mouse"
    assert b.device == "tablet"


def test_unknown_fields_are_rejected_so_callers_filter_saved_settings_first():
    with pytest.raises(TypeError):
        Setup(goals=[])  # type: ignore[call-arg]


def test_the_way_callers_build_a_setup_from_saved_settings_ignores_other_keys():
    saved = {"goals": [{"id": "x"}], "latest": 500, "device": "mouse", "area_w_mm": 100.0}
    s = Setup(**{k: v for k, v in saved.items() if k in Setup.__dataclass_fields__})
    assert s.device == "mouse" and s.area_w_mm == 100.0


def test_asdict_round_trips():
    s = Setup(device="mouse", keyboard="sayo", sayo_stroke_mm=3.4, sayo_full_stroke=False, client="lazer")
    assert Setup(**asdict(s)) == s


def test_values_are_not_validated_or_coerced():
    s = Setup(device="gamepad", screen_w_px="wide")  # type: ignore[arg-type]
    assert s.device == "gamepad" and s.screen_w_px == "wide"  # validation belongs to the API schema
