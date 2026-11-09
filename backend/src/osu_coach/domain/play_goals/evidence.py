"""Which plays are evidence for a map in a mod configuration: verified, comparable plays of one player."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Sequence

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.play_goals.models import AccuracyRange, Blocker, EvidenceRow, GoalPlay, MapRow, Reason
from osu_coach.domain.play_goals.pool import CONFIGS

MIN_PLAYS = 10
MIN_MAPS = 5
LAZER_MOD_BITS = {"EZ": 2, "HD": 8, "HR": 16, "DT": 64, "NC": 64, "NF": 0}


def sim_ok(meta: ReplayMeta) -> bool:
    # lazer replays rarely match the header exactly; 90% agreement is enough to locate breaks.
    return meta.sim_match is True or (finite_or_none(meta.sim_agreement) or 0) >= 0.9


def configuration(meta: ReplayMeta, lazer_mods: object = None) -> str | None:
    """The play's mod configuration (a :data:`CONFIGS` name), or None when it isn't a supported one. Lazer plays need
    their mods with settings read back from the replay file (``lazer_mods``)."""
    bits = meta.mods
    if not isinstance(bits, int) or meta.client not in ("stable", "lazer"):
        return None
    bits &= ~1  # NoFail changes no difficulty
    if bits & 512:
        bits = (bits & ~512) | 64
    name = next((name for name, value in CONFIGS.items() if value == bits), None)
    if name is None or abs((finite_or_none(meta.rate) or 1) - (1.5 if bits & 64 else 1)) > 1e-6:
        return None
    if meta.client == "lazer":
        if not isinstance(lazer_mods, list | tuple):
            return None
        actual = 0
        for mod in lazer_mods:
            if not isinstance(mod, dict) or mod.get("acronym") not in LAZER_MOD_BITS:
                return None
            acronym = mod["acronym"]
            actual |= LAZER_MOD_BITS[acronym]
            extra = set(mod.get("settings") or {})
            if acronym == "EZ":
                extra -= {"retries"}
            if acronym in ("DT", "NC") and (mod.get("settings") or {}).get("speed_change") == 1.5:
                extra -= {"speed_change"}
            if extra:
                return None
        if actual != bits:
            return None
    return name


def play_configuration(play: GoalPlay) -> str | None:
    return configuration(play.meta, play.lazer_mods)


def full_combo(play: GoalPlay) -> bool:
    m = play.meta
    return m.completed and m.n_played == m.n_objects and m.nmiss == 0 and m.sim_match is True and not len(play.events)


def evidence(plays: Sequence[GoalPlay], player: str | None) -> list[EvidenceRow]:
    """The player's verified plays in supported configurations, each score once."""
    if player is None:
        return []
    seen, out = set(), []
    for a in plays:
        m = a.meta
        mods = play_configuration(a)
        key = (m.beatmap_md5, str(m.date), m.score)
        if m.player != player or mods is None or key in seen or not sim_ok(m):
            continue
        if any(finite_or_none(v) is None for v in (m.stars, m.ar, m.od, m.bpm, m.length_s, m.accuracy)):
            continue
        seen.add(key)
        out.append(
            EvidenceRow(
                key=a.key,
                beatmap_md5=m.beatmap_md5,
                date=str(m.date),
                client=m.client,
                mods_name=mods,
                completed=m.completed,
                n_played=m.n_played,
                n_objects=m.n_objects,
                stars=m.stars,
                ar=m.ar,
                od=m.od,
                bpm=m.bpm,
                length_s=m.length_s,
                accuracy=m.accuracy,
                aim=m.aim,
                speed=m.speed,
                fc=full_combo(a),
                breaks=len(a.events),
                stream_share=a.stream_share,
                jump_share=a.jump_share,
            )
        )
    return out


def same_map(target: MapRow, rows: Sequence[EvidenceRow]) -> list[EvidenceRow]:
    """The plays of the target map in its configuration."""
    return [
        r
        for r in rows
        if r.beatmap_md5 == target["md5"] and r.mods_name == target["mods"] and r.client == target["client"]
    ]


def comparable(target: MapRow, rows: Sequence[EvidenceRow]) -> list[EvidenceRow]:
    """Completed plays of maps like the target (difficulty, length, patterns), newest first, at most two per map."""
    selected = []
    for row in rows:
        if row.mods_name != target["mods"] or row.client != target["client"] or not row.completed:
            continue
        if row.n_played != row.n_objects:
            continue
        if any(
            abs(getattr(row, k) - target[k]) > gap for k, gap in (("stars", 0.6), ("ar", 1), ("od", 1), ("bpm", 25))
        ):
            continue
        if not 0.5 <= row.length_s / max(1, target["length_s"]) <= 2:
            continue
        if any(
            abs(getattr(row, k) - (finite_or_none(target.get(k)) or 0)) > 0.25 for k in ("stream_share", "jump_share")
        ):
            continue
        if any(
            finite_or_none(getattr(row, k)) is not None
            and finite_or_none(target.get(k)) is not None
            and abs(getattr(row, k) - target[k]) > max(0.5, target[k] * 0.35)
            for k in ("aim", "speed")
        ):
            continue
        selected.append(row)
    selected.sort(key=lambda r: r.date, reverse=True)
    # One map cannot dominate the range, even if it has hundreds of retries.
    counts: Counter = Counter()
    balanced = []
    for row in selected:
        if counts[row.beatmap_md5] < 2:
            balanced.append(row)
            counts[row.beatmap_md5] += 1
    return balanced[:60]


def accuracy_range(target: MapRow, rows: Sequence[EvidenceRow]) -> AccuracyRange | None:
    """The middle 80% of the comparable plays' accuracy; None without enough plays on enough maps."""
    peers = comparable(target, rows)
    maps = len({r.beatmap_md5 for r in peers})
    if len(peers) < MIN_PLAYS or maps < MIN_MAPS:
        return None
    values = sorted(r.accuracy for r in peers)
    return AccuracyRange(
        low=values[math.floor((len(values) - 1) * 0.1)],
        high=values[math.ceil((len(values) - 1) * 0.9)],
        median=statistics.median(values),
        plays=len(peers),
        maps=maps,
    )


def skipped_attempts(
    plays: Sequence[GoalPlay], rows: Sequence[EvidenceRow], player: str | None, target: MapRow
) -> Counter[Reason]:
    """Why the player's attempts of the target map are not usable evidence, with how many of each (empty if none)."""
    kept = {r.key for r in rows}
    why: Counter[Reason] = Counter()
    for a in plays:
        m = a.meta
        if m.beatmap_md5 != target["md5"] or m.player != player or a.key in kept:
            continue
        mods = f"+{m.mod_string or 'NM'}"
        config = play_configuration(a)
        if m.client != target["client"]:
            why[Reason("other_client", (mods, m.client, target["client"]))] += 1
        elif not sim_ok(m):
            why[Reason("sim_mismatch")] += 1
        elif config is None:
            why[Reason("unsupported_mods", (mods,))] += 1
        elif config != target["mods"]:
            why[Reason("other_mods", (mods, target["mods"]))] += 1
        else:
            why[Reason("incomplete")] += 1
    return why


def blocker_skill(reason: str, pattern: str) -> str:
    """The skill a miss or break of this reason on this pattern points at."""
    if reason in ("follow", "released", "key_swap") or pattern == "slider":
        return "sliders"
    if pattern in ("stream", "burst") and reason in ("late", "early", "no_tap"):
        return "speed"
    if reason == "lost":
        return "reading"
    if reason in ("early", "late"):
        return "accuracy"
    return "flow_aim" if pattern == "spaced" else "aim"


def blockers(plays: Sequence[GoalPlay], target: MapRow) -> list[Blocker]:
    """The three skills whose misses and breaks stop most attempts of the target in its configuration."""
    events: Counter[str] = Counter()
    times: dict[str, Counter[str]] = {}
    attempts: dict[str, set[str]] = {}
    for a in plays:
        m = a.meta
        if m.beatmap_md5 != target["md5"] or play_configuration(a) != target["mods"] or m.client != target["client"]:
            continue
        ev = a.events
        for reason, pattern, timestamp in zip(ev.reason, ev.pattern, ev.timestamp, strict=True):
            skill = blocker_skill(reason, pattern)
            events[skill] += 1
            times.setdefault(skill, Counter())[timestamp] += 1
            attempts.setdefault(skill, set()).add(a.key)
    ranked = sorted(events, key=lambda k: (-len(attempts[k]), -events[k], k))[:3]
    return [
        Blocker(skill, events[skill], len(attempts[skill]), tuple(t for t, _ in times[skill].most_common(5)))
        for skill in ranked
    ]
