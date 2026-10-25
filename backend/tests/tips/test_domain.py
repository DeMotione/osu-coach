import dataclasses

import pytest

from osu_coach.library.repository import analyze_files
from osu_coach.profile.domain import build_profile
from osu_coach.settings.domain import Setup
from osu_coach.tips.domain import make_tips, practice_plan
from tests.conftest import replay_and_map


@pytest.fixture(scope="module")
def base():
    names = ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr"]
    return build_profile([analyze_files(*replay_and_map(n)[:2]) for n in names])


def with_(p, **kw):
    return dataclasses.replace(p, **kw)


def tip(tips, category, word=""):
    found = [t for t in tips if t.category == category and word.lower() in t.title.lower()]
    return found[0] if found else None


def _quadrant(significant):
    return {
        "quadrant": "bottom-right",
        "miss_rate": 0.1,
        "rest_miss_rate": 0.04,
        "relative_risk": 2.5,
        "z": 5.0,
        "objects": 900,
        "misses": 90,
        "mean_dx": -6.0,
        "mean_dy": -5.0,
        "along": -0.2,
        "aim_miss_rate": 0.08,
        "significant": significant,
    }


def test_significant_weak_quadrant_is_top_priority(base):
    tips = make_tips(with_(base, worst_quadrant=_quadrant(True)), Setup(device="tablet", handedness="right"))
    t = tip(tips, "Quadrant")
    assert t.severity == 3 and "BOTTOM-RIGHT" in t.title
    text = " ".join(t.actions)
    assert "short" in text  # clicks land towards the middle -> not reaching the corner
    assert "nearest your hand" in text


def test_noisy_weak_quadrant_is_low_priority(base):
    t = tip(make_tips(with_(base, worst_quadrant=_quadrant(False)), Setup()), "Quadrant")
    assert t.severity == 1


def _tapping(base, **kw):
    return with_(base, tapping={**base.tapping, **kw})


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


def _aim_misses_in(base, pattern: str, spaced: bool = False, n: int = 200):
    """The base profile with its misses replaced by n aim misses on notes of one pattern (jumps at normal speed,
    or streams — where they count as speed-aim misses)."""
    from osu_coach.profile.domain import miss_causes

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
