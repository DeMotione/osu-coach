import math
from types import SimpleNamespace

import pytest

from osu_coach.beatmaps import difficulty

MAP = "maps/0619c930348063c2a967a3af4d69cd6b.osu"  # standard map, 363 circles / 165 sliders / 1 spinner
HR, DT, HT, NC = 16, 64, 256, 512

needs_rosu = pytest.mark.skipif(not difficulty.available(), reason="rosu-pp-py not installed")


@pytest.fixture
def osu_bytes(res):
    return res(MAP).read_bytes()


class FakeRosu:
    """Stands in for rosu_pp_py: records the Difficulty kwargs; behaviour is steered by class attributes."""

    created: list = []
    suspicious = False
    reject_lazer_mods = False
    attrs = SimpleNamespace(stars=5.5, aim=2, speed=float("nan"), max_combo=100, ar="9", flashlight=None)
    strain_data = SimpleNamespace(section_length=400, aim=[1, 2], speed=None)

    class Beatmap:
        def __init__(self, bytes):
            if bytes == b"broken":
                raise ValueError("cannot parse")

        def is_suspicious(self):
            return FakeRosu.suspicious

    class Difficulty:
        def __init__(self, **kw):
            if FakeRosu.reject_lazer_mods and isinstance(kw.get("mods"), list):
                raise TypeError("unknown mod")
            FakeRosu.created.append(kw)

        def calculate(self, m):
            return FakeRosu.attrs

        def strains(self, m):
            return FakeRosu.strain_data


@pytest.fixture
def fake(monkeypatch):
    FakeRosu.created = []
    FakeRosu.suspicious = False
    FakeRosu.reject_lazer_mods = False
    FakeRosu.attrs = SimpleNamespace(stars=5.5, aim=2, speed=float("nan"), max_combo=100, ar="9", flashlight=None)
    FakeRosu.strain_data = SimpleNamespace(section_length=400, aim=[1, 2], speed=None)
    monkeypatch.setattr(difficulty, "rosu", FakeRosu)
    return FakeRosu


# --- availability ---------------------------------------------------------------------------------------------


def test_available_reflects_whether_rosu_imported(monkeypatch):
    monkeypatch.setattr(difficulty, "rosu", None)
    assert not difficulty.available()
    monkeypatch.setattr(difficulty, "rosu", object())
    assert difficulty.available()


def test_everything_fails_soft_without_rosu(monkeypatch, osu_bytes):
    monkeypatch.setattr(difficulty, "rosu", None)
    assert difficulty.attributes(osu_bytes) == {}
    assert difficulty.strains(osu_bytes) is None


# --- _legacy_rate / _kwargs -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mods", "rate"),
    [(0, 1.0), (HR, 1.0), (DT, 1.5), (NC, 1.5), (DT | NC, 1.5), (HT, 0.75), (HT | HR, 0.75), (DT | HR, 1.5)],
)
def test_legacy_rate(mods, rate):
    assert difficulty._legacy_rate(mods) == rate


def test_kwargs_for_plain_legacy_mods():
    assert difficulty._kwargs(HR, None, None, False) == {"mods": HR, "lazer": False}
    assert difficulty._kwargs(0, None, None, True) == {"mods": 0, "lazer": True}


def test_kwargs_omit_clock_rate_when_it_matches_the_mods():
    assert difficulty._kwargs(DT, 1.5, None, False) == {"mods": DT, "lazer": False}
    assert difficulty._kwargs(HT, 0.75, None, False) == {"mods": HT, "lazer": False}
    assert difficulty._kwargs(0, 1.0, None, False) == {"mods": 0, "lazer": False}
    assert difficulty._kwargs(DT, 1.5 + 1e-9, None, False) == {"mods": DT, "lazer": False}


def test_kwargs_pass_a_custom_clock_rate():
    assert difficulty._kwargs(DT, 1.3, None, False) == {"mods": DT, "lazer": False, "clock_rate": 1.3}
    assert difficulty._kwargs(0, 1.2, None, True) == {"mods": 0, "lazer": True, "clock_rate": 1.2}


def test_kwargs_ignore_a_zero_or_missing_rate():
    assert "clock_rate" not in difficulty._kwargs(DT, 0, None, False)
    assert "clock_rate" not in difficulty._kwargs(DT, None, None, False)


def test_kwargs_use_lazer_mod_list_and_ignore_legacy_bits_and_rate():
    mods = [{"acronym": "DT", "settings": {"speed_change": 1.3}}, {"acronym": "HD"}]
    kw = difficulty._kwargs(HR, 2.0, mods, False)
    assert kw == {
        "mods": [{"acronym": "DT", "settings": {"speed_change": 1.3}}, {"acronym": "HD", "settings": {}}],
        "lazer": True,
    }


def test_kwargs_lazer_mods_skip_entries_without_acronym_and_tolerate_null_settings():
    kw = difficulty._kwargs(
        0, None, [{"settings": {"a": 1}}, {"acronym": "", "settings": {}}, {"acronym": "EZ", "settings": None}], False
    )
    assert kw["mods"] == [{"acronym": "EZ", "settings": {}}]


def test_kwargs_lazer_mods_are_copied():
    settings = {"speed_change": 1.2}
    kw = difficulty._kwargs(0, None, [{"acronym": "DT", "settings": settings}], False)
    kw["mods"][0]["settings"]["speed_change"] = 9
    assert settings == {"speed_change": 1.2}


def test_kwargs_empty_lazer_mod_list_means_legacy_path():
    assert difficulty._kwargs(HR, None, [], True) == {"mods": HR, "lazer": True}


# --- _difficulty fallback -------------------------------------------------------------------------------------


def test_difficulty_falls_back_to_legacy_bits_when_lazer_mods_are_unknown(fake):
    fake.reject_lazer_mods = True
    difficulty._difficulty(DT, 1.3, [{"acronym": "XX"}], True)
    assert fake.created == [{"mods": DT, "lazer": True, "clock_rate": 1.3}]


def test_difficulty_reraises_when_legacy_arguments_are_rejected(monkeypatch):
    class Rejecting:
        class Difficulty:
            def __init__(self, **kw):
                raise TypeError("nope")

    monkeypatch.setattr(difficulty, "rosu", Rejecting)
    with pytest.raises(TypeError):
        difficulty._difficulty(0, None, None, False)


# --- attributes (stubbed rosu) --------------------------------------------------------------------------------


def test_attributes_keeps_only_known_finite_numeric_values_as_floats(fake):
    out = difficulty.attributes(b"data")
    # NaN (speed), None (flashlight), a string (ar) and attributes the stub lacks are all dropped
    assert out == {"stars": 5.5, "aim": 2.0, "max_combo": 100.0}
    assert all(type(v) is float for v in out.values())


def test_attributes_passes_mods_rate_and_lazer_flag_on(fake):
    difficulty.attributes(b"data", mods=HR, rate=1.2, lazer=True)
    assert fake.created == [{"mods": HR, "lazer": True, "clock_rate": 1.2}]


def test_attributes_uses_lazer_mods_when_given(fake):
    difficulty.attributes(b"data", lazer_mods=[{"acronym": "DT", "settings": {"speed_change": 1.4}}])
    assert fake.created == [{"mods": [{"acronym": "DT", "settings": {"speed_change": 1.4}}], "lazer": True}]


def test_attributes_empty_for_suspicious_maps(fake):
    fake.suspicious = True
    assert difficulty.attributes(b"data") == {}
    assert fake.created == []


def test_attributes_empty_when_the_map_cannot_be_parsed(fake):
    assert difficulty.attributes(b"broken") == {}


def test_attributes_empty_when_calculation_raises(fake, monkeypatch):
    def boom(self, m):
        raise RuntimeError("calc failed")

    monkeypatch.setattr(fake.Difficulty, "calculate", boom)
    assert difficulty.attributes(b"data") == {}


def test_attributes_empty_when_even_the_fallback_fails(fake, monkeypatch):
    class Never:
        def __init__(self, **kw):
            raise TypeError("nope")

    monkeypatch.setattr(fake, "Difficulty", Never)
    assert difficulty.attributes(b"data", lazer_mods=[{"acronym": "XX"}]) == {}


def test_attributes_only_report_names_in_attr_names(fake):
    fake.attrs = SimpleNamespace(stars=1.0, something_else=3.0)
    assert difficulty.attributes(b"data") == {"stars": 1.0}


# --- strains (stubbed rosu) -----------------------------------------------------------------------------------


def test_strains_shape_and_missing_series_become_empty_lists(fake):
    s = difficulty.strains(b"data")
    assert s == {"section_length": 400.0, "aim": [1, 2], "speed": [], "reading": []}
    assert isinstance(s["section_length"], float)


def test_strains_include_reading_when_rosu_has_it(fake):
    fake.strain_data = SimpleNamespace(section_length=400, aim=[1], speed=[2], reading=[3, 4])
    assert difficulty.strains(b"data")["reading"] == [3, 4]


def test_strains_pass_mods_on(fake):
    difficulty.strains(b"data", mods=DT, rate=1.5, lazer=True)
    assert fake.created == [{"mods": DT, "lazer": True}]


def test_strains_none_when_map_cannot_be_parsed(fake):
    assert difficulty.strains(b"broken") is None


def test_strains_none_when_rosu_raises(fake, monkeypatch):
    def boom(self, m):
        raise RuntimeError("no strains")

    monkeypatch.setattr(fake.Difficulty, "strains", boom)
    assert difficulty.strains(b"data") is None


def test_strains_do_not_skip_suspicious_maps(fake):
    # attributes() refuses suspicious maps, strains() has no such check
    fake.suspicious = True
    assert difficulty.strains(b"data") is not None


# --- with the real rosu-pp ------------------------------------------------------------------------------------


@needs_rosu
def test_real_attributes_of_a_sample_map(osu_bytes):
    a = difficulty.attributes(osu_bytes)
    assert 7.0 < a["stars"] < 8.5
    assert a["aim"] > 0
    assert a["speed"] > 0
    assert a["n_circles"] == 363
    assert a["n_sliders"] == 165
    assert a["n_spinners"] == 1
    assert a["max_combo"] == 734
    assert a["ar"] == pytest.approx(9.7, abs=1e-3)
    assert set(a) <= set(difficulty.ATTR_NAMES)
    assert all(isinstance(v, float) and math.isfinite(v) for v in a.values())


@needs_rosu
def test_real_attributes_are_deterministic(osu_bytes):
    assert difficulty.attributes(osu_bytes) == difficulty.attributes(osu_bytes)


@needs_rosu
def test_real_double_time_is_harder_and_a_matching_rate_changes_nothing(osu_bytes):
    nm = difficulty.attributes(osu_bytes)
    dt = difficulty.attributes(osu_bytes, mods=DT)
    assert dt["stars"] > nm["stars"] + 1
    assert difficulty.attributes(osu_bytes, mods=DT, rate=1.5) == dt


@needs_rosu
def test_real_custom_rate_lies_between_nomod_and_double_time(osu_bytes):
    nm = difficulty.attributes(osu_bytes)["stars"]
    dt = difficulty.attributes(osu_bytes, mods=DT)["stars"]
    custom = difficulty.attributes(osu_bytes, mods=DT, rate=1.25)["stars"]
    assert nm < custom < dt


@needs_rosu
def test_real_half_time_is_easier(osu_bytes):
    assert difficulty.attributes(osu_bytes, mods=HT)["stars"] < difficulty.attributes(osu_bytes)["stars"]


@needs_rosu
def test_real_hard_rock_raises_ar(osu_bytes):
    nm = difficulty.attributes(osu_bytes)
    hr = difficulty.attributes(osu_bytes, mods=HR)
    assert hr["ar"] > nm["ar"]


@needs_rosu
def test_real_lazer_rate_setting_is_honoured(osu_bytes):
    nm = difficulty.attributes(osu_bytes)["stars"]
    fast = difficulty.attributes(osu_bytes, lazer_mods=[{"acronym": "DT", "settings": {"speed_change": 1.5}}])["stars"]
    slower = difficulty.attributes(osu_bytes, lazer_mods=[{"acronym": "DT", "settings": {"speed_change": 1.1}}])[
        "stars"
    ]
    assert nm < slower < fast


@needs_rosu
def test_real_unknown_lazer_mod_is_ignored(osu_bytes):
    # rosu-pp accepts unknown acronyms and skips them, so the legacy fallback is not needed
    nm = difficulty.attributes(osu_bytes)
    dt = difficulty.attributes(osu_bytes, lazer_mods=[{"acronym": "DT"}])
    assert difficulty.attributes(osu_bytes, lazer_mods=[{"acronym": "ZZ"}]) == nm
    assert difficulty.attributes(osu_bytes, lazer_mods=[{"acronym": "DT"}, {"acronym": "ZZ"}]) == dt


@needs_rosu
def test_real_unusable_lazer_mod_setting_fails_soft(osu_bytes):
    bad = [{"acronym": "DT", "settings": {"speed_change": "fast"}}]
    assert difficulty.attributes(osu_bytes, lazer_mods=bad) == {}


@needs_rosu
def test_real_strains_of_a_sample_map(osu_bytes):
    s = difficulty.strains(osu_bytes)
    assert s["section_length"] == 400.0
    assert len(s["aim"]) == len(s["speed"]) > 100
    assert max(s["aim"]) > 0
    assert max(s["speed"]) > 0
    assert isinstance(s["reading"], list)


@needs_rosu
def test_real_strains_shrink_in_number_under_double_time(osu_bytes):
    nm = difficulty.strains(osu_bytes)
    dt = difficulty.strains(osu_bytes, mods=DT)
    assert len(dt["aim"]) < len(nm["aim"])


@needs_rosu
def test_real_garbage_input_does_not_raise():
    # rosu-pp parses garbage as an empty map, so the result is a degenerate but well-formed dict
    a = difficulty.attributes(b"not a beatmap")
    assert a.get("max_combo", 0) == 0
    assert a.get("n_circles", 0) == 0
    s = difficulty.strains(b"not a beatmap")
    assert s is None or max(s["aim"], default=0) == 0


# --- section_index --------------------------------------------------------------------------------------------


def test_section_index_without_sections():
    assert difficulty.section_index(1000, 500, 400, 0) == -1
    assert difficulty.section_index(1000, 500, 400, -3) == -1


def test_section_index_first_section_ends_at_ceil_of_second_object():
    # second object at 500 ms -> the first section ends at ceil(500/400)*400 = 800
    assert difficulty.section_index(0, 500, 400, 10) == 0
    assert difficulty.section_index(800, 500, 400, 10) == 0  # boundary belongs to the first section
    assert difficulty.section_index(800.1, 500, 400, 10) == 1
    assert difficulty.section_index(1200, 500, 400, 10) == 1
    assert difficulty.section_index(1200.1, 500, 400, 10) == 2


def test_section_index_second_object_exactly_on_a_boundary():
    assert difficulty.section_index(400, 400, 400, 10) == 0
    assert difficulty.section_index(401, 400, 400, 10) == 1


def test_section_index_times_before_the_first_section_clamp_to_zero():
    assert difficulty.section_index(-5000, 500, 400, 10) == 0


def test_section_index_clamps_to_the_last_section():
    assert difficulty.section_index(10**6, 500, 400, 10) == 9
    assert difficulty.section_index(10**6, 500, 400, 1) == 0


def test_section_index_returns_an_int():
    assert type(difficulty.section_index(1000.0, 500.0, 400.0, 10)) is int


@needs_rosu
def test_section_index_stays_within_real_strain_series(osu_bytes):
    s = difficulty.strains(osu_bytes)
    n = len(s["aim"])
    for t in (0, 1234.5, 90_000, 10**7):
        assert 0 <= difficulty.section_index(t, 600, s["section_length"], n) < n
