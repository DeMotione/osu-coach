"""A replay's mods and speed: one reading of lazer's speed mods for the header, the replay and its configuration."""

from osu_coach.domain.replays.configuration import from_meta
from osu_coach.domain.replays.models import MOD_BITS, lazer_rate, mods_label


def test_mods_label_spells_out_custom_speeds():
    assert mods_label("DT", 1.5) == "DT" and mods_label("HDDT", 1.26) == "HDDT ×1.26"
    assert mods_label("", 1.0) == "NM" and mods_label("", 0.85) == "NM ×0.85"
    assert mods_label("HR", float("nan")) == "HR"


def test_lazer_speed_mods_set_their_own_speed_unless_changed():
    assert lazer_rate([{"acronym": "DT", "settings": {"speed_change": 1.2}}]) == 1.2
    assert lazer_rate([{"acronym": "HD"}, {"acronym": "NC"}]) == 1.5
    assert lazer_rate([{"acronym": "DC", "settings": {}}]) == 0.75
    assert lazer_rate([{"acronym": "HD"}]) is None and lazer_rate(None) is None and lazer_rate("DT") is None


def test_a_configuration_takes_the_speed_lazer_played_at():
    custom = from_meta({"mods": 0, "lazer_mods": [{"acronym": "DT", "settings": {"speed_change": 1.33}}]})
    assert custom.rate == 1.33 and custom.mods & MOD_BITS["DT"]
    assert from_meta({"mods": MOD_BITS["DT"]}).rate == 1.5
    assert from_meta({"mods": MOD_BITS["DT"], "rate": 1.25}).rate == 1.25  # a known rate wins
