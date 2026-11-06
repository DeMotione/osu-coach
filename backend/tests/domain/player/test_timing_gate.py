"""A low-accuracy DT replay remains available to other skills but not to the accuracy rating."""

from osu_coach.common.texts import message
from osu_coach.domain.player.algorithm import timing_evidence_eligible
from osu_coach.domain.replays.models import MOD_BITS
from tests.domain.player.helpers import rate

DT = MOD_BITS["DT"]


def _singles():
    return [{"replay_key": f"dt{k}", "map_md5": f"m{k}"} for k in range(3) for _ in range(40)]


def test_insufficient_accepted_timing_heads_are_unmeasured():
    assert not timing_evidence_eligible(DT, 0.88)
    rejected = rate(_singles(), mods=DT, accuracy=0.88)["accuracy"]
    assert rejected.score is None
    assert "evidence gate" in message(rejected.reason)
    assert timing_evidence_eligible(DT, 0.880001)
    accepted = rate(_singles(), mods=DT, accuracy=0.880001)["accuracy"]
    assert accepted.hit_single_notes == 120
    assert accepted.score is not None
