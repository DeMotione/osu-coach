"""Which replays can be analysed, and picking them from replay headers (dicts as the library lists them)."""
from __future__ import annotations

from collections import Counter

from osu_coach.domain.analysis import UNSUPPORTED_LAZER_MODS
from osu_coach.domain.replay import MOD_BITS

# relax / autopilot / autoplay / cinema / target practice: not the player's own aim+tapping
EXCLUDE_MODS = MOD_BITS["RX"] | MOD_BITS["AP"] | MOD_BITS["AT"] | (1 << 22) | (1 << 23)


def skip_reason(h: dict) -> str | None:
    """Why a replay can't be analysed, judging by its header (lazer mods the simulation can't
    follow); None if it can."""
    for m in h.get("lazer_mods") or ():
        if m in UNSUPPORTED_LAZER_MODS:
            return UNSUPPORTED_LAZER_MODS[m]
    return None


def analysable(h: dict) -> bool:
    """osu!standard, played by the player themself, with mods the simulation can follow."""
    return h.get("mode") == 0 and not (h.get("mods", 0) & EXCLUDE_MODS) and skip_reason(h) is None


def dedupe(refs: list[dict]) -> list[dict]:
    """The same play found in several places is kept once."""
    seen, out = set(), []
    for r in refs:
        k = (r.get("beatmap_md5"), r.get("timestamp"), r.get("score"), r.get("player"))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def standard_replays(refs: list[dict]) -> list[dict]:
    return [r for r in refs if analysable(r)]


def eligible(refs: list[dict], player: str | None = None, limit: int | None = None) -> list[dict]:
    """Analysable replays (of ``player``, "*" = anyone), duplicates removed, newest first."""
    picked = standard_replays(refs)
    if player and player != "*":
        picked = [r for r in picked if r.get("player") == player]
    picked = sorted(dedupe(picked), key=lambda r: r.get("timestamp", ""), reverse=True)
    return picked[:limit] if limit else picked


def left_out(refs: list[dict], player: str | None = None, since: str | None = None) -> Counter:
    """Reasons osu!standard replays of ``player`` can't be analysed, counted. ``since``: only replays
    played at or after this ISO timestamp."""
    picked = [r for r in refs if r.get("mode") == 0 and not (r.get("mods", 0) & EXCLUDE_MODS)
              and (not player or player == "*" or r.get("player") == player)
              and (not since or r.get("timestamp", "") >= since)]
    return Counter(skip_reason(r) for r in dedupe(picked) if skip_reason(r))


def player_counts(refs: list[dict]) -> list[tuple[str, int]]:
    return Counter(r.get("player", "") for r in dedupe(standard_replays(refs))).most_common()
