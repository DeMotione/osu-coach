"""A low-accuracy DT replay remains available to other skills but not timing aggregation."""

import pandas as pd

from osu_coach.profile.domain import skills
from osu_coach.profile.domain.algorithm import timing_evidence_eligible


def test_insufficient_accepted_timing_heads_are_unmeasured(monkeypatch):
    for name in (
        "aim_score",
        "flow_score",
        "speed_score",
        "stamina_score",
        "slider_score",
        "reading_score",
        "consistency_score",
    ):
        monkeypatch.setattr(skills, name, lambda *args, **kwargs: {"score": None})
    monkeypatch.setattr(skills, "difficulty_weights", lambda p, *args: pd.Series(1.0, index=p.index))
    rows = pd.DataFrame(
        {
            "replay_key": ["dt"] * 80,
            "run_len": [1] * 80,
            "head_hit": [True] * 80,
            "head_result": [300] * 80,
            "stars": [4.0] * 80,
            "timing_eligible": [timing_evidence_eligible(64, 0.88)] * 80,
        }
    )
    rated = skills.compute_skills(rows, None, {}, {}, {}, {})
    assert rated["accuracy"]["score"] is None
    assert rated["accuracy"]["n"] == 0
    assert "evidence gate" in rated["accuracy"]["reason"]
    rows["timing_eligible"] = timing_evidence_eligible(64, 0.880001)
    accepted = skills.compute_skills(rows, None, {}, {}, {}, {})
    assert accepted["accuracy"]["n"] == 80
    assert accepted["accuracy"]["score"] is not None
