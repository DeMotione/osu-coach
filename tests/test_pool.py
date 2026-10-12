import math
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from osu_coach.pool import (QUADRANTS, SKILLS, POOL_PATH, Targets, build_playlist, collection_name, load_pool,
                            map_stats, suggest, targets_from_profile)

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
    s = map_stats(stream_map())
    assert s["stream_share"] > 0.8
    assert s["stream_bpm"] == pytest.approx(120, abs=1)
    assert s["max_run"] == 16
    assert s["s_speed"] > s["s_aim"]


def test_jump_map_is_an_aim_map():
    s = map_stats(jump_map())
    assert s["jump_share"] > 0.8
    assert s["s_aim"] > s["s_speed"]
    shares = [s["q_" + q.replace("-", "_")] for q in QUADRANTS]
    assert sum(shares) == pytest.approx(1.0)
    assert all(0.2 < v < 0.3 for v in shares)


def test_non_standard_maps_are_rejected():
    assert map_stats(osu_bytes([(100, 100, 1000 + 200 * i) for i in range(50)], mode=1)) is None


def fake_pool(n=600, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "md5": [f"{i:032x}" for i in range(n)], "beatmap_id": np.arange(n) + 1,
        "beatmapset_id": np.arange(n) // 2 + 1, "creator": [f"mapper{i % 97}" for i in range(n)],
        "title": [f"song {i // 2}" for i in range(n)], "artist": "a", "version": "v",
        "stars": rng.uniform(1, 8, n), "playcount": rng.integers(1000, 10 ** 6, n),
        "stream_bpm": rng.uniform(140, 240, n), "burst_bpm": np.nan, "max_run": 20, "long_runs": 2,
        "jump_share": 0.3, "spaced_share": 0.1, "jump_dist": 3.0, "spaced_stream_share": 0.1, "od": 8.0,
        "circle_share": 0.6, "slider_share": 0.4, "reverse_share": 0.1, "slider_factor": 0.98, "ar": 9.0,
        "density_p90": 6.0, "drain_length": 150.0, "evenness": 0.5, "n_jumps": 120,
    })
    for sk in SKILLS:
        df["s_" + sk] = rng.uniform(0, 1, n)
    for q in QUADRANTS:
        df["q_" + q.replace("-", "_")] = rng.uniform(0.1, 0.4, n)
    return df


def test_suggest_stays_near_target_and_skips_played():
    pool = fake_pool()
    in_window = pool[(pool["stars"] - 4.0).abs() < 0.3]
    played = frozenset(in_window["md5"].head(5))
    out = suggest(pool, "aim", Targets(comfort=4.0, played=played), n=8)
    assert len(out) == 8
    assert out["stars"].between(3.5, 4.5).all()
    assert not set(out["md5"]) & played
    assert out["beatmapset_id"].is_unique
    assert list(out["stars"]) == sorted(out["stars"])
    assert out["skill_fit"].mean() > in_window["s_aim"].mean()
    assert out["url"].str.startswith("https://osu.ppy.sh/beatmapsets/").all()


def test_speed_suggestions_prefer_the_target_stream_bpm():
    pool = fake_pool()
    out = suggest(pool, "speed", Targets(comfort=4.0, stream_bpm=180.0), n=10)
    near = pool[(pool["stars"] - 4.0).abs() <= 0.5]
    assert (out["stream_bpm"] - 180).abs().median() < (near["stream_bpm"] - 180).abs().median()


def test_quadrant_suggestions_prefer_the_weak_quadrant():
    pool = fake_pool()
    out = suggest(pool, "quadrant", Targets(comfort=4.0, quadrant="bottom-left"), n=10)
    assert out["q_bottom_left"].mean() > pool["q_bottom_left"].mean() + 0.05
    assert "bottom-left" in out["why"].iloc[0]


def test_playlist_has_three_stages_of_increasing_difficulty():
    pl = build_playlist(fake_pool(), "aim", Targets(comfort=4.0), n=15)
    assert list(pl["stage"].unique()) == ["Warm-up", "Core", "Push"]
    means = pl.groupby("stage", sort=False)["stars"].mean().tolist()
    assert means[0] < means[1] < means[2]
    assert pl["beatmapset_id"].is_unique
    assert len(pl) == 15
    assert pl["goal"].str.len().gt(5).all()


def test_accuracy_playlist_is_easier_than_comfort():
    pl = build_playlist(fake_pool(), "accuracy", Targets(comfort=5.0), n=9)
    assert pl["stars"].mean() < 4.6
    assert pl["goal"].str.contains("accuracy").all()


def test_targets_from_profile():
    p = SimpleNamespace(levels={"comfort_stars": 3.2}, overview={}, tapping={"comfort_bpm": 160, "limit_bpm": 180},
                        worst_quadrant={"quadrant": "bottom-left", "significant": True},
                        reading={"high_ar_miss_rate": 0.1, "mid_ar_miss_rate": 0.04, "low_ar_miss_rate": math.nan},
                        replays=pd.DataFrame({"beatmap_md5": ["a" * 32]}), weaknesses=["aim"])
    t = targets_from_profile(p)
    assert t.comfort == pytest.approx(3.2)
    assert t.stream_bpm == 170
    assert t.quadrant == "bottom-left"
    assert t.ar_range == (9.0, 9.7)
    assert "a" * 32 in t.played
    assert collection_name("quadrant", t) == "osu-coach: Weak quadrant (bottom-left) (3.2★)"


def test_targets_fallback_for_a_new_player():
    p = SimpleNamespace(levels={"comfort_stars": math.nan}, overview={"avg_stars": math.nan}, tapping={},
                        worst_quadrant={"quadrant": "top-left", "significant": False}, reading={}, replays=None)
    t = targets_from_profile(p)
    assert t.comfort == 2.5 and t.stream_bpm is None and t.quadrant is None


@pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built")
def test_bundled_pool_covers_beginner_to_advanced():
    pool = load_pool()
    assert len(pool) >= 2000
    assert pool["md5"].is_unique
    assert pool["stars"].min() < 1.5 and pool["stars"].max() > 7.5
    assert {"s_" + s for s in SKILLS} <= set(pool.columns)


@pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built")
@pytest.mark.parametrize("comfort,bpm", [(2.0, None), (3.5, 150.0), (6.5, 200.0)])
def test_bundled_pool_gives_full_playlists_for_every_skill(comfort, bpm):
    """Even where a skill has little material (streams at 2★), the playlist is full,
    near the player's level, and has no repeated songs."""
    pool = load_pool()
    for sk in SKILLS:
        pl = build_playlist(pool, sk, Targets(comfort=comfort, stream_bpm=bpm), n=9)
        assert len(pl) == 9, (sk, comfort)
        assert pl["title"].str.lower().str.replace(r"\s*[\(\[].*?[\)\]]", "", regex=True).is_unique, sk
        assert (pl["stars"] - comfort).abs().max() < 2.0, sk


@pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built")
def test_accuracy_maps_have_tight_hit_windows_for_the_level():
    pool = load_pool()
    pl = build_playlist(pool, "accuracy", Targets(comfort=4.0), n=9)
    level = pool[(pool["stars"] - pl["stars"].mean()).abs() < 0.5]
    assert pl["od"].mean() > level["od"].mean()


# ------------------------------------------------------------------ COCOSO ranking (optional, Mark's request)
def test_cocoso_matches_the_published_formula_on_a_small_example():
    from osu_coach.pool import cocoso_scores
    df = pd.DataFrame({"a": [1.0, 0.5, 0.0], "b": [0.0, 0.5, 1.0]})
    k = cocoso_scores(df, {"a": 0.6, "b": 0.4})
    r = {"a": np.array([1.0, 0.505, 0.01]), "b": np.array([0.01, 0.505, 1.0])}
    S = 0.6 * r["a"] + 0.4 * r["b"]
    P = r["a"] ** 0.6 + r["b"] ** 0.4
    ka, kb = (S + P) / (S + P).sum(), S / S.min() + P / P.min()
    kc = (0.5 * S + 0.5 * P) / (0.5 * S.max() + 0.5 * P.max())
    assert np.allclose(k, (ka * kb * kc) ** (1 / 3) + (ka + kb + kc) / 3)


def test_cocoso_prefers_balanced_maps_where_the_weighted_sum_ties():
    """Same weighted sum, but one map is near 0 on one criterion: COCOSO's product part puts it lower."""
    from osu_coach.pool import cocoso_scores
    df = pd.DataFrame({"skill_fit": [1.0, 0.5, 0.0], "star_fit": [0.0, 0.5, 1.0]})
    w = {"skill_fit": 0.5, "star_fit": 0.5}
    k = cocoso_scores(df, w)
    assert k[1] > k[0] and k[1] > k[2]          # the balanced map wins
    assert len(set(np.round(0.5 * df["skill_fit"] + 0.5 * df["star_fit"], 9))) == 1   # weighted sum: a tie


def test_ranking_option_reaches_suggestions_and_playlists():
    pool = fake_pool()
    a = suggest(pool, "aim", Targets(comfort=4.0), n=10)
    b = suggest(pool, "aim", Targets(comfort=4.0, ranking="cocoso"), n=10)
    assert len(a) == len(b) == 10 and b["beatmapset_id"].is_unique
    assert b["stars"].between(3.0, 5.0).all()
    pl = build_playlist(pool, "speed", Targets(comfort=4.0, stream_bpm=180.0, ranking="cocoso"), n=15)
    assert list(pl["stage"].unique()) == ["Warm-up", "Core", "Push"] and len(pl) == 15
    assert Targets(comfort=4.0).ranking == "weighted"                        # default unchanged
