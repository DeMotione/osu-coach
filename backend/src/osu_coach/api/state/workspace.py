"""Server-side state of the app.

osu! coach is a single-user app running on the player's own computer, so the state of a session — the scanned
replay library, the analysed replays and the profile built from them — lives in this process, in one
:class:`Workspace`. Settings (choices that are remembered across starts) are in the domain's ``settings.json``
in the data folder, shared with the command line.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from osu_coach.infrastructure.database import progress
from osu_coach.infrastructure.filesystem import locate
from osu_coach.domain import selection
from osu_coach.domain.setup import Setup
from osu_coach.domain.analysis import ReplayAnalysis
from osu_coach.infrastructure.filesystem.library import Library
from osu_coach.infrastructure.filesystem.settings_store import load_settings, save_settings
from osu_coach.infrastructure.filesystem.map_pool import load_pool
from osu_coach.domain.profile import Profile, build_profile

from osu_coach.config import Settings, default_cache_dir
from osu_coach.api.errors import NoProfile
from osu_coach.api.state.jobs import BusyGate, JobManager

T = TypeVar("T")


@dataclass
class ScanArgs:
    """What the last scan read, so it can be repeated further back (more replays)."""
    installs: list[locate.Install] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    only: bool = False                                            # only these files, not the library
    map_installs: list[locate.Install] = field(default_factory=list)   # beatmaps only, for ``only``


class Workspace:
    def __init__(self, config: Settings):
        self.config = config
        self.cache_dir = Path(config.cache_dir or default_cache_dir())
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.gate = BusyGate()
        self.jobs = JobManager(self.gate)
        self._settings_lock = threading.Lock()
        self._profile_lock = threading.Lock()
        self._installs: list[locate.Install] | None = None
        # the session
        self.library: Library | None = None
        self.scan_args: ScanArgs | None = None
        self.analyses: list[ReplayAnalysis] = []
        self.errors: list[tuple[dict, str]] = []
        self.player_label = ""
        self.check_library: Library | None = None
        self._profile: Profile | None = None
        self._profile_sig: tuple | None = None
        self._memo: dict[str, Any] = {}

    # -------------------------------------------------------------- settings
    def settings(self) -> dict:
        return load_settings(self.cache_dir)

    def update_settings(self, **changes) -> dict:
        """Change some settings (read-modify-write under a lock, keeping every other key)."""
        with self._settings_lock:
            s = load_settings(self.cache_dir)
            s.update(changes)
            save_settings(s, self.cache_dir)
            return s

    def setup(self) -> Setup:
        """The player's setup; the osu! client falls back to :meth:`preferred_client`."""
        s = self.settings()
        setup = Setup(**{k: v for k, v in s.items() if k in Setup.__dataclass_fields__})
        if s.get("client") not in ("stable", "lazer"):
            setup.client = self.preferred_client()
        return setup

    def preferred_client(self) -> str:
        """The client the player uses: saved setting, else what their replays / installs say."""
        s = self.settings()
        if s.get("client") in ("stable", "lazer"):
            return s["client"]
        reps = getattr(self.profile(), "replays", None)
        if reps is not None and len(reps) and "client" in reps:
            return "lazer" if (reps["client"] == "lazer").mean() >= 0.5 else "stable"
        kinds = {i.kind for i in self.installs()}
        return "lazer" if kinds == {"lazer"} else "stable"

    # -------------------------------------------------------------- installs and the map pool
    def installs(self, refresh: bool = False) -> list[locate.Install]:
        if self._installs is None or refresh:
            self._installs = locate.find_installs()
        return self._installs

    @staticmethod
    def pool():
        return load_pool()      # cached by the domain (per file and modification time)

    # -------------------------------------------------------------- analyses and the profile
    def set_analyses(self, analyses: list[ReplayAnalysis], errors: list[tuple[dict, str]], player_label: str):
        with self._profile_lock:
            self.analyses, self.errors, self.player_label = list(analyses), list(errors), player_label
            self._profile, self._profile_sig, self._memo = None, None, {}

    def _signature(self) -> tuple:
        s = self.settings()
        return (s.get("replay_set", "all"), s.get("level_override"), tuple(a.key for a in self.analyses))

    def profile(self) -> Profile | None:
        """The profile of the analysed replays with the current choices (All / Best replays, level set by
        hand), rebuilt when they change; None before anything was analysed or when *Best replays* is empty."""
        if not self.analyses:
            return None
        sig = self._signature()
        with self._profile_lock:
            if self._profile_sig != sig:
                s = self.settings()
                chosen = selection.select(self.analyses, s.get("replay_set", "all"))
                self._profile = build_profile(chosen, level=s.get("level_override")) if chosen else None
                self._profile_sig, self._memo = sig, {}
            return self._profile

    def require_profile(self) -> Profile:
        p = self.profile()
        if p is None:
            if self.analyses:
                raise NoProfile("None of the analysed replays is a passed play, so Best replays is empty — switch "
                                "to All replays.")
            raise NoProfile()
        return p

    def save_progress(self, lib: Library, analyses: list[ReplayAnalysis]) -> None:
        """Add the analyses to the progress history (SQLite; it stays when replays or caches are deleted)."""
        progress.update(lib.cache, analyses, lib.load_cached)

    def memo(self, key: str, compute: Callable[[], T]) -> T:
        """A value computed from the current profile, kept until the profile changes."""
        self.profile()
        with self._profile_lock:
            sig = self._profile_sig
            if key in self._memo:
                return self._memo[key]
        value = compute()
        with self._profile_lock:
            if self._profile_sig == sig:        # not if the profile was rebuilt meanwhile
                self._memo[key] = value
        return value

    def replay_set(self) -> str:
        rs = self.settings().get("replay_set", "all")
        return rs if rs in selection.REPLAY_SETS else "all"
