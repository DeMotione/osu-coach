import math

import pytest
import rosu_pp_py as rosu

from osu_coach.beatmaps.domain import PlayableBeatmap
from osu_coach.beatmaps.parser import parse_beatmap, parse_beatmap_file
from osu_coach.beatmaps.curves import SliderPath

FD = "maps/da8aae79c8f3306b5d65ec951874a7fb.osu"  # xi - FREEDOM DiVE [FOUR DIMENSIONS]


def test_reads_metadata_and_difficulty(res):
    bm = parse_beatmap_file(res(FD))
    assert bm.title == "FREEDOM DiVE"
    assert bm.version_name == "FOUR DIMENSIONS"
    assert (bm.cs, bm.ar, bm.od, bm.hp) == (4, 9, 8, 6)
    assert bm.format_version == 9
    assert bm.md5 == "da8aae79c8f3306b5d65ec951874a7fb"


def test_object_counts_match_official_metadata(res):
    bm = parse_beatmap_file(res(FD))
    kinds = [o.kind for o in bm.objects]
    assert kinds.count("circle") == 1646
    assert kinds.count("slider") == 335
    assert kinds.count("spinner") == 2


def test_max_combo_matches_rosu_pp(res):
    """Combo = circles + spinners + per slider (head + ticks + repeats + tail):
    proves slider durations and tick generation are right."""
    path = res(FD)
    bm = parse_beatmap_file(path)
    expected = rosu.Difficulty().calculate(rosu.Beatmap(path=str(path))).max_combo
    assert bm.max_combo() == expected == 2385


def test_bpm_lookup(res):
    bm = parse_beatmap_file(res(FD))
    assert bm.bpm_at(bm.objects[100].time) == pytest.approx(222.22, abs=0.01)


def test_linear_path_is_truncated_to_pixel_length():
    p = SliderPath("L", [(0, 0), (100, 0)], expected_length=50)
    assert p.length == pytest.approx(50)
    assert p.position_at(1.0) == pytest.approx((50, 0))


def test_linear_path_is_extended_to_pixel_length():
    p = SliderPath("L", [(0, 0), (100, 0)], expected_length=150)
    assert p.position_at(1.0) == pytest.approx((150, 0))


def test_perfect_circle_path_follows_the_arc():
    # quarter-ish arc through three points on circle centred (0,0) r=100
    pts = [(100, 0), (100 * math.cos(math.pi / 4), 100 * math.sin(math.pi / 4)), (0, 100)]
    p = SliderPath("P", pts, expected_length=math.pi / 2 * 100)
    mid = p.position_at(0.5)
    assert math.hypot(*mid) == pytest.approx(100, abs=0.5)
    assert p.position_at(1.0) == pytest.approx((0, 100), abs=0.5)


def test_bezier_endpoints_and_length():
    p = SliderPath("B", [(0, 0), (50, 100), (100, 0)], expected_length=None)
    assert p.position_at(0.0) == pytest.approx((0, 0))
    assert p.position_at(1.0) == pytest.approx((100, 0), abs=0.01)
    assert 100 < p.length < 200


SYNTH = """osu file format v14

[General]
StackLeniency: 0.7
Mode: 0

[Metadata]
Title:Synthetic
Artist:Test
Creator:me
Version:Stack

[Difficulty]
HPDrainRate:5
CircleSize:4
OverallDifficulty:8
ApproachRate:9
SliderMultiplier:1.4
SliderTickRate:1

[TimingPoints]
0,500,4,2,0,100,1,0

[HitObjects]
100,100,1000,1,0,0:0:0:0:
100,100,1250,1,0,0:0:0:0:
100,100,1500,1,0,0:0:0:0:
400,300,2000,1,0,0:0:0:0:
"""


def test_stacking_offsets_up_left():
    bm = parse_beatmap(SYNTH)
    pb = PlayableBeatmap(bm, mods=0)
    stacks = [pb.stack(o) for o in bm.objects]
    assert stacks == [2, 1, 0, 0]
    r = pb.radius
    assert pb.pos(bm.objects[0]) == pytest.approx((100 - 2 * r / 10, 100 - 2 * r / 10))
    assert pb.pos(bm.objects[3]) == pytest.approx((400, 300))


def test_hardrock_flips_vertically_and_tightens_windows():
    bm = parse_beatmap(SYNTH)
    nm = PlayableBeatmap(bm, mods=0)
    hr = PlayableBeatmap(bm, mods=16)
    assert hr.pos(bm.objects[3]) == pytest.approx((400, 384 - 300))
    assert hr.cs == pytest.approx(5.2)
    assert hr.od == 10 and hr.ar == 10
    assert hr.radius < nm.radius
    assert (nm.hit300, nm.hit100, nm.hit50) == (32, 76, 120)


def test_easy_halves_settings():
    hr = PlayableBeatmap(parse_beatmap(SYNTH), mods=2)
    assert hr.od == 4 and hr.ar == 4.5 and hr.cs == 2
