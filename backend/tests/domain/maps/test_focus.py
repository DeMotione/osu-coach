import pytest

from osu_coach.domain.maps.focus import Focus, parse_focus


def test_reads_a_focus():
    assert parse_focus(None) is None and parse_focus(" ") is None
    assert parse_focus("bpm:140-160,120-130") == Focus("bpm", ranges=((120.0, 130.0), (140.0, 160.0)))
    assert parse_focus("ar:9.5-10") == Focus("ar", ranges=((9.5, 10.0),))
    assert parse_focus("quadrant:top-left") == Focus("quadrant", side="top-left")
    for bad in ("bpm", "bpm:130-120", "bpm:1-2,x", "juggling:1-2", "angle:round", "quadrant:middle", "jump:2-3"):
        with pytest.raises(ValueError):
            parse_focus(bad)


def test_keeps_the_maps_on_the_weak_spot():
    bpm = parse_focus("bpm:120-130,140-160")
    assert bpm.matches({"stream_bpm": 125}) and bpm.matches({"stream_bpm": 159.4})
    # note times in whole ms: a 120 BPM stream at 119.8 is at 120, a 160 BPM one at 159.6 at 160, as on the analysis
    assert bpm.matches({"stream_bpm": 119.8}) and not bpm.matches({"stream_bpm": 159.6})
    assert not bpm.matches({"stream_bpm": 130}) and not bpm.matches({"stream_bpm": None}) and not bpm.matches({})
    assert parse_focus("run:12-20").matches({"max_run": 20}) and not parse_focus("run:12-20").matches({"max_run": 21})
    assert parse_focus("jump:long").matches({"jump_dist": 3.1}) and not parse_focus("jump:long").matches(
        {"jump_dist": 2.6}
    )
    assert parse_focus("jump:short").matches({"jump_dist": 2.3})
    assert parse_focus("angle:sharp").matches({"sharp_share": 0.7}) and parse_focus("angle:wide").matches(
        {"sharp_share": 0.3}
    )
    corner = parse_focus("quadrant:bottom-right")
    assert corner.matches({"q_bottom_right": 0.3}) and not corner.matches({"q_bottom_right": 0.25, "q_top_left": 0.5})
    long = parse_focus("slider_length:long")
    assert long.matches({"slider_length_norm": 2.0, "slider_share": 0.4})
    assert not long.matches({"slider_length_norm": 2.0, "slider_share": 0.1})  # hardly any sliders to practise
    fast = parse_focus("slider_speed:fast")  # 1.4 px/ms at CS 4 (radius 36.48): ≈ 19 circle widths a second
    assert fast.matches({"slider_velocity": 1.4, "cs": 4, "slider_share": 0.5})
    assert not fast.matches({"slider_velocity": 0.3, "cs": 4, "slider_share": 0.5})


def test_says_what_it_practises():
    assert parse_focus("bpm:120-130,140-160").label() == "streams at 120–129 and 140–159 BPM"
    assert parse_focus("run:12-20").label() == "streams of 12–20 notes"
    assert parse_focus("ar:9.5-10,10-11").label() == "AR 9.5 and AR 10–11"
    assert parse_focus("jump:long").label() == "long jumps"
    assert parse_focus("quadrant:top-left").label() == "jumps into the top-left of the screen"
    assert parse_focus("slider_speed:fast").label() == "fast sliders"
    assert parse_focus("bpm:150-160").sets_tempo and not parse_focus("ar:9-9.5").sets_tempo
