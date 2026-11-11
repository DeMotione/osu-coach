"""Maps service helpers that don't need the web stack."""

import datetime as dt
from types import SimpleNamespace

import pandas as pd

from osu_coach.domain.maps.suggestions import Targets
from osu_coach.features.maps.service import _played, completed
from osu_coach.infra.settings import UserSettings


def _ws(replays, player="Me"):
    return SimpleNamespace(settings=lambda: UserSettings({"player": player}), library=SimpleNamespace(replays=replays))


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
    assert _played(SimpleNamespace(settings=lambda: UserSettings(), library=None), t) == {"analysed"}


def test_completed_maps_are_the_pool_maps_finished_last_first():
    """The list a playlist's finished maps go to: pool maps only, with the last time each was finished."""
    pool = pd.DataFrame(
        [
            {
                "md5": md5,
                "beatmap_id": i,
                "beatmapset_id": 10 + i,
                "artist": "A",
                "title": md5,
                "version": "V",
                "stars": 5.0,
            }
            for i, md5 in enumerate(("analysed", "scanned", "both", "never"), start=1)
        ]
    )
    profile = SimpleNamespace(
        replays=(
            SimpleNamespace(beatmap_md5="analysed", date=dt.datetime(2026, 11, 1, 12)),
            SimpleNamespace(beatmap_md5="both", date=dt.datetime(2026, 11, 2, 12)),
            SimpleNamespace(beatmap_md5="not-in-pool", date=dt.datetime(2026, 11, 9, 12)),
        )
    )
    replays = [
        {"mode": 0, "beatmap_md5": "scanned", "player": "Me", "timestamp": "2026-11-03T08:00:00"},
        {"mode": 0, "beatmap_md5": "both", "player": "Me", "timestamp": "2026-11-05T08:00:00"},
        {"mode": 0, "beatmap_md5": "both", "player": "Me", "timestamp": "2026-10-01T08:00:00"},
    ]
    ws = SimpleNamespace(
        pool=lambda: pool,
        profile=lambda: profile,
        settings=lambda: UserSettings({"player": "Me"}),
        library=SimpleNamespace(replays=replays),
    )
    maps = completed(ws)
    assert [(m.md5, m.played_at) for m in maps] == [
        ("both", "2026-11-05T08:00:00Z"),
        ("scanned", "2026-11-03T08:00:00Z"),
        ("analysed", "2026-11-01T12:00:00Z"),
    ]
    assert maps[0].url == "https://osu.ppy.sh/beatmapsets/13#osu/3"
    no_plays = SimpleNamespace(pool=lambda: pool, profile=lambda: None, settings=lambda: UserSettings(), library=None)
    assert completed(no_plays) == []
