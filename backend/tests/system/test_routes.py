"""Health and the labels every page uses."""

import pytest

from osu_coach.profile.domain import SKILL_HELP, SKILL_LABELS

pytestmark = pytest.mark.usefixtures("_isolated")


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["version"] and body["core_version"]


def test_meta_has_every_skill_with_its_explanation(client):
    m = client.get("/api/meta").json()
    assert [s["key"] for s in m["skills"]] == list(SKILL_LABELS)
    for s in m["skills"]:
        assert (s["what"], s["how"], s["practise"]) == SKILL_HELP[s["key"]]
    assert m["latest_choices"] == [100, 500, 1000, 0]
    assert {c["key"] for c in m["date_choices"]} == {"all", "session", "7d", "30d", "custom"}
    assert len(m["lazer_instructions"]) == 3
