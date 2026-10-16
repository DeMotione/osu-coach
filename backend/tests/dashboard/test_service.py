from osu_coach.dashboard.service import experimental_facts


def test_accuracy_facts_name_the_direction_of_the_measured_rate():
    facts = experimental_facts(
        "accuracy", {"maps": 66, "hit_single_notes": 1234, "measured": 0.114, "expected": 0.0976}
    )

    assert "1,234 hit single notes" in facts
    assert "88.6% hit as 300s" in facts
    assert "non-300 rate on hit single notes (lower is better): 11.4% vs assumed 9.76%" in facts
