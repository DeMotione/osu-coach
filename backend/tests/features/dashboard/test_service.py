from osu_coach.domain.player.messages import Message
from osu_coach.domain.player.ratings import SkillRating
from osu_coach.features.dashboard.service import skill_facts


def test_accuracy_facts_name_the_direction_of_the_measured_rate():
    facts = skill_facts(
        "accuracy",
        SkillRating(None, 66, Message("not_enough_data"), hit_single_notes=1234, measured=0.114, expected=0.0976),
    )

    assert "1,234 hit single notes" in facts
    assert "88.6% hit as 300s" in facts
    assert "non-300 rate on hit single notes (lower is better): 11.4% vs assumed 9.76%" in facts


def test_overview_tips_and_playlists_name_the_same_weaknesses():
    """One scoring system: the Overview, the practice plan and the playlist's first skill all come from the ratings."""
    from osu_coach.common.texts import SKILL_LABELS
    from osu_coach.domain.player import build_profile
    from osu_coach.features.dashboard.service import overview
    from osu_coach.features.maps.service import default_skill
    from osu_coach.features.tips.rules import practice_plan
    from osu_coach.infra.library import analyze_files
    from tests.conftest import INDEX, sample_paths

    p = build_profile([analyze_files(*sample_paths(name)) for name in INDEX])
    assert p.weaknesses, "all the fixture replays together have a comfort level and something to work on"
    page = overview(p)
    assert page.weaknesses == [SKILL_LABELS[k] for k in p.weaknesses]
    assert page.strengths == [SKILL_LABELS[k] for k in p.strengths]
    assert SKILL_LABELS[p.weaknesses[0]] in " ".join(practice_plan(p))
    rated = {k: v.score for k, v in p.skill_ratings.items() if v.score is not None}
    first = next(k for k in p.weaknesses if k in rated and k != "consistency")
    assert default_skill(p, rated) == first
