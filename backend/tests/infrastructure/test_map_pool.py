import pytest

from osu_coach.maps.domain import QUADRANTS, SKILLS
from osu_coach.maps.repository import POOL_PATH, load_pool, save_pool, stats_from_osu

HEADER = """osu file format v14

[General]
StackLeniency: 0.7
Mode: {mode}

[Metadata]
Title:Pool
Artist:Test
Creator:me
Version:Synthetic
BeatmapID:1
BeatmapSetID:1

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


def osu_bytes(objs, mode=0):
    lines = [f"{x},{y},{t},1,0,0:0:0:0:" for x, y, t in objs]
    return (HEADER.format(mode=mode) + "\n".join(lines) + "\n").encode()


def stream_map():
    objs, t = [], 1000
    for block in range(6):
        for i in range(16):          # 1/4 notes at 120 BPM = 125 ms apart, tiny spacing
            objs.append((100 + (i % 8) * 12, 200 + (block % 2) * 10, t))
            t += 125
        t += 1000
    return osu_bytes(objs)


def jump_map():
    pts = [(60, 60), (450, 320), (60, 320), (450, 60)]
    return osu_bytes([(pts[i % 4][0], pts[i % 4][1], 1000 + 250 * i) for i in range(80)])


def test_stream_map_is_a_speed_map():
    s = stats_from_osu(stream_map())
    assert s["stream_share"] > 0.8
    assert s["stream_bpm"] == pytest.approx(120, abs=1)
    assert s["max_run"] == 16
    assert s["s_speed"] > s["s_aim"]


def test_jump_map_is_an_aim_map():
    s = stats_from_osu(jump_map())
    assert s["jump_share"] > 0.8
    assert s["s_aim"] > s["s_speed"]
    shares = [s["q_" + q.replace("-", "_")] for q in QUADRANTS]
    assert sum(shares) == pytest.approx(1.0)
    assert all(0.2 < v < 0.3 for v in shares)


def test_non_standard_and_broken_maps_are_rejected():
    assert stats_from_osu(osu_bytes([(100, 100, 1000 + 200 * i) for i in range(50)], mode=1)) is None
    assert stats_from_osu(b"not a beatmap") is None


def test_pool_file_round_trips(tmp_path):
    path = save_pool([{"md5": "a" * 32, "stars": 4.123456, "bpm": float("nan")}], tmp_path / "pool.json.gz")
    pool = load_pool(path)
    assert pool["md5"].tolist() == ["a" * 32] and pool["stars"].iloc[0] == pytest.approx(4.1235)
    assert pool["bpm"].isna().all()
    assert load_pool(tmp_path / "missing.json.gz").empty


@pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built")
def test_bundled_pool_covers_beginner_to_advanced():
    pool = load_pool()
    assert len(pool) >= 4500
    assert pool["stars"].between(2, 8, inclusive="left").mean() > 0.8      # most of it is 2-8 stars
    assert pool["md5"].is_unique
    assert pool["stars"].min() < 1.5 and pool["stars"].max() > 7.5
    assert {"s_" + s for s in SKILLS} <= set(pool.columns)
