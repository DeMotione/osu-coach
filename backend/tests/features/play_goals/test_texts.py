from collections import Counter

from osu_coach.domain.play_goals.models import Reach, Reason, Recommendation
from osu_coach.features.play_goals import texts


def test_every_verdict_and_reason_has_a_text():
    assert set(texts.TONES) <= set(texts.VERDICTS)
    for code in (
        "fc_exists",
        "qualitative",
        "own_attempts_only",
        "outside_range",
        "peers_no_fc",
        "practice_first",
        "needs_evidence",
    ):
        assert texts.reason(Reason(code))
    assert texts.reason(Reason("recent_best", (3, 0.9, 40, False))).endswith(
        "40 combo-breaking event(s), did not finish."
    )
    assert Reach("unknown", (), "unassessed").verdict in texts.VERDICTS


def test_skipped_attempts_text():
    why = Counter({Reason("other_client", ("+NM", "lazer", "stable")): 1, Reason("sim_mismatch"): 1})
    text = texts.skipped(why)
    assert text and "2 attempt(s)" in text and "osu!lazer" in text and "simulation" in text
    assert texts.skipped(Counter()) is None


def test_dynamics_text():
    assert texts.dynamics(["speed"]) == "Streamy"
    assert texts.dynamics(["aim", "reading"]) == "Jumpy + Reading-heavy"
    assert texts.dynamics(["stamina", "speed"]) == "Stamina-heavy + Streamy"
    assert texts.dynamics([]) == "Balanced"


def test_recommendation_labels_the_pp_scenario():
    rec = Recommendation(
        map={"md5": "m", "mods": "HD", "s_aim": 0.8},
        practice_accuracy=0.95,
        accuracy=None,
        pp=100.0,
        pp_ss=150.0,
        pp_accuracy=0.95,
        local_best_accuracy=None,
        achieved=False,
        stage="starter",
        projected=False,
        score=1.0,
    )
    out = texts.recommendation(rec, [])
    assert out["pp_label"].startswith("Conditional")
    assert out["why"] == "Trains HD reading." and out["stage"] == "Starter"
    assert out["map"]["dynamics"] == "Jumpy"
    assert texts.recommendation(rec, [{"skill": "aim", "title": "Jump aim"}])["why"] == "Trains jump aim."
