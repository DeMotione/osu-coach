"""Maps service helpers that don't need the web stack."""

from types import SimpleNamespace

from osu_coach.maps.domain import Targets
from osu_coach.maps.service import _played


def _ws(replays, player="Me"):
    return SimpleNamespace(settings=lambda: {"player": player}, library=SimpleNamespace(replays=replays))


def test_completed_maps_include_every_scanned_replay_of_the_player():
    """#47: a map finished outside the analysed replays (only the latest N analysed) is not suggested again."""
    replays = [
        {"mode": 0, "beatmap_md5": "scanned", "player": "Me"},
        {"mode": 0, "beatmap_md5": "someone-else", "player": "Other"},
        {"mode": 1, "beatmap_md5": "taiko", "player": "Me"},
        {"mode": 0, "beatmap_md5": None, "player": "Me"},
    ]
    t = Targets(comfort=6.0, played=frozenset({"analysed"}))
    assert _played(_ws(replays), t) == {"analysed", "scanned"}
    assert _played(_ws(replays, player="*"), t) == {"analysed", "scanned", "someone-else"}
    assert _played(SimpleNamespace(settings=lambda: {}, library=None), t) == {"analysed"}
