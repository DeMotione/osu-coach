"""How long an analysis will take, worked out before it starts so the player knows what to expect (#95).

A replay's analysis takes about as long as its file is big (the cursor frames are most of the file and the simulation
walks them); a lazer replay is followed far more often while a slider is held, so it costs several times more per
byte. The numbers are one core of a slow 2016 4-core AMD A10, fitted on 61 real replays (within ~15-18% each);
``speed`` scales them to the computer at hand, measured by its own analyses (``infra.analysis_speed``).
"""

from __future__ import annotations

from dataclasses import dataclass

STABLE = (0.127, 5.48)  # seconds of one core: base + per MB of the replay file
LAZER = (-0.054, 19.7)
LEAST = 0.05  # no replay is free
FROM_CACHE = 0.06  # a summary made again from a cached analysis (after an update of the app)
STORED = 0.005  # a summary read from the store
STARTUP = 3.0  # starting the worker processes
AFTERWARDS = 0.02  # per play: the progress history and the profile, once the plays are summarised
EFFICIENCY = 0.8  # workers never keep every core fully busy
DOWNLOAD = 1.5  # one missing beatmap looked up and downloaded


@dataclass(frozen=True, slots=True)
class Plan:
    """What an analysis will have to do with its replays."""

    new: tuple[tuple[float, bool], ...]  # (file size in MB, lazer) of each replay to analyse
    from_cache: int  # replays whose cached analysis is summarised again
    stored: int  # replays already analysed and summarised

    @property
    def replays(self) -> int:
        return len(self.new) + self.from_cache + self.stored


def replay_seconds(megabytes: float, lazer: bool) -> float:
    """One core's seconds to analyse and summarise a replay of this size."""
    base, per_mb = LAZER if lazer else STABLE
    return max(LEAST, base + per_mb * megabytes)


def parallel_work(plan: Plan, workers: int) -> float:
    """The analysing and summarising itself, spread over ``workers`` processes (they start from 4 replays on), on
    the computer fitted on."""
    work = sum(replay_seconds(mb, lazer) for mb, lazer in plan.new) + FROM_CACHE * plan.from_cache
    return work / (max(1, workers) * EFFICIENCY) if len(plan.new) + plan.from_cache >= 4 else work


def analysis_seconds(plan: Plan, workers: int, speed: float = 1.0) -> float:
    """The whole analysis on ``workers`` processes of a computer ``speed`` times as slow as the one fitted on."""
    work = parallel_work(plan, workers)
    if not work:
        return STORED * plan.stored
    return STARTUP + work * max(speed, 0.05) + STORED * plan.stored + AFTERWARDS * plan.replays
