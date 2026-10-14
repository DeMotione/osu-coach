import numpy as np
import pytest

from osu_coach.domain.beatmap import PlayableBeatmap
from osu_coach.infrastructure.filesystem.beatmap import parse_beatmap
from osu_coach.domain.features import object_features

HEADER = """osu file format v14

[General]
StackLeniency: 0.7
Mode: 0

[Metadata]
Title:Features
Artist:Test
Creator:me
Version:Synthetic

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
"""


def make_map(objs):
    lines = [f"{x},{y},{t},1,0,0:0:0:0:" for x, y, t in objs]
    return parse_beatmap(HEADER + "\n".join(lines) + "\n")


def test_stream_of_quarter_notes_is_labelled_stream():
    # 120 BPM -> 1/4 = 125 ms, 12 notes, small spacing
    objs = [(100 + 15 * i, 200, 1000 + 125 * i) for i in range(12)]
    df = object_features(PlayableBeatmap(make_map(objs)))
    assert (df["run_len"] == 12).all()
    assert (df["pattern"].iloc[1:] == "stream").all()
    assert df["stream_bpm"].iloc[5] == pytest.approx(120, abs=0.5)


def test_large_spacing_on_half_beats_is_jump():
    pts = [(60, 60), (450, 320), (60, 320), (450, 60), (60, 60)]
    objs = [(x, y, 1000 + 250 * i) for i, (x, y) in enumerate(pts)]
    df = object_features(PlayableBeatmap(make_map(objs)))
    assert list(df["pattern"].iloc[1:]) == ["jump"] * 4
    assert df["dist_norm"].iloc[1] > 4


def test_angle_straight_line_vs_back_and_forth():
    line = make_map([(100, 192, 1000), (200, 192, 1250), (300, 192, 1500)])
    zig = make_map([(100, 192, 1000), (300, 192, 1250), (100, 192, 1500)])
    a_line = object_features(PlayableBeatmap(line))["angle"].iloc[2]
    a_zig = object_features(PlayableBeatmap(zig))["angle"].iloc[2]
    assert a_line == pytest.approx(180, abs=1)
    assert a_zig == pytest.approx(0, abs=1)


def test_quadrants_and_direction():
    m = make_map([(100, 100, 1000), (400, 300, 1500)])
    df = object_features(PlayableBeatmap(m))
    assert list(df["quadrant"]) == ["top-left", "bottom-right"]
    assert df["dir8"].iloc[1] == "down-right"


def test_hardrock_flips_quadrant():
    m = make_map([(100, 100, 1000), (400, 300, 1500)])
    df = object_features(PlayableBeatmap(m, mods=16))
    assert list(df["quadrant"]) == ["bottom-left", "top-right"]


def test_rate_converts_to_real_time():
    objs = [(100 + 15 * i, 200, 1000 + 125 * i) for i in range(12)]
    df = object_features(PlayableBeatmap(make_map(objs), mods=64))
    assert df["stream_bpm"].iloc[5] == pytest.approx(180, abs=0.5)
    assert np.allclose(df["dt_real"].iloc[1:], 125 / 1.5)


def test_simultaneous_notes_do_not_produce_infinite_stream_bpm():
    # 2B-style: two notes at the same time inside a stream
    objs = [(100 + 15 * i, 200, 1000 + 125 * i) for i in range(10)] + [(300, 300, 1000 + 125 * 5)]
    objs.sort(key=lambda o: o[2])
    df = object_features(PlayableBeatmap(make_map(objs)))
    assert np.isfinite(df["stream_bpm"].dropna()).all()
    assert df["stream_bpm"].dropna().median() == pytest.approx(120, abs=0.5)
