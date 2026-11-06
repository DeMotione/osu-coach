"""Server-side state of the app.

osu! coach is a single-user app running on the player's own computer, so the state of a session — the scanned
replay library, the analysed replays and the profile built from them — lives in this process, in one
:class:`Workspace`. Settings (choices that are remembered across starts) are in ``settings.json``
in the data folder, shared with the command line.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from osu_coach.common.errors import NoProfile
from osu_coach.config import Settings, default_cache_dir
from osu_coach.domain.player import PlaySummary, Profile, build_profile_from
from osu_coach.domain.player.setup import Setup
from osu_coach.domain.replays import scope
from osu_coach.infra.jobs import BusyGate, JobManager
from osu_coach.infra.library import Library, ScanArgs
from osu_coach.infra.map_pool import load_pool
from osu_coach.infra.replays import detect
from osu_coach.infra.settings import UserSettings, load_settings, read_settings, save_settings

T = TypeVar("T")
CHECK_LATEST = 100  # replays read for a single-replay page when nothing was scanned yet
RESTORING = "Restoring your last session… This page fills in by itself in a moment."


class Workspace:
    def __init__(self, config: Settings):
        self.config = config
        self.cache_dir = Path(config.cache_dir or default_cache_dir())
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.gate = BusyGate()
        self.jobs = JobManager(self.gate)
        self._settings_lock = threading.Lock()
        self._profile_lock = threading.Lock()
        self._installs: list[detect.Install] | None = None
        # the session
        self.library: Library | None = None
        self.scan_args: ScanArgs | None = None
        self.plays: list[PlaySummary] = []  # the analysed plays, summarised
        self.errors: list[tuple[dict, str]] = []
        self.player_label = ""
        self.restoring = False  # the analysed plays of the last session are being brought back (at start-up)
        self.check_library: Library | None = None
        self._profile: Profile | None = None
        self._profile_sig: tuple | None = None
        self._memo: dict[str, Any] = {}

    # -------------------------------------------------------------- settings
    def settings(self) -> UserSettings:
        return read_settings(self.cache_dir)

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
        setup = Setup(**{k: v for k, v in s.values.items() if k in Setup.__dataclass_fields__})
        if s.client not in ("stable", "lazer"):
            setup.client = self.preferred_client()
        return setup

    def preferred_client(self) -> str:
        """The client the player uses: saved setting, else what their replays / installs say."""
        s = self.settings()
        if s.client in ("stable", "lazer"):
            return s.client
        reps = getattr(self.profile(), "replays", None) or ()
        if reps:
            return "lazer" if sum(m.client == "lazer" for m in reps) >= 0.5 * len(reps) else "stable"
        kinds = {i.kind for i in self.installs()}
        return "lazer" if kinds == {"lazer"} else "stable"

    # -------------------------------------------------------------- installs and the map pool
    def installs(self, refresh: bool = False) -> list[detect.Install]:
        """The osu! installs found on this computer and the folders the player entered (``install_paths``)."""
        if self._installs is None or refresh:
            extra = self.settings().install_paths or []
            self._installs = detect.find_installs(extra=[Path(p) for p in extra])
        return self._installs

    @staticmethod
    def pool():
        return load_pool()  # cached by infra.map_pool (per file and modification time)

    # -------------------------------------------------------------- single replays (Detailed map analysis, Play goals)
    def replay_library(self) -> Library | None:
        """The scanned library, else a quick scan of the newest replays on this computer (kept for later)."""
        if self.library is not None:
            return self.library
        if self.check_library is None:
            installs = self.installs()
            if not installs:
                return None
            lib = Library(self.cache_dir)
            for inst in installs:
                lib.add_install(inst, latest=CHECK_LATEST)
            self.check_library = lib
        return self.check_library

    # -------------------------------------------------------------- analyses and the profile
    def set_plays(self, plays: list[PlaySummary], errors: list[tuple[dict, str]], player_label: str):
        with self._profile_lock:
            self.plays, self.errors, self.player_label = list(plays), list(errors), player_label
            self._profile, self._profile_sig, self._memo = None, None, {}

    def _signature(self) -> tuple:
        s = self.settings()
        return (s.replay_set or "all", s.level_override, tuple(a.key for a in self.plays))

    def profile(self) -> Profile | None:
        """The profile of the analysed replays with the current choices (All / Best replays, level set by
        hand), rebuilt when they change; None before anything was analysed or when *Best replays* is empty."""
        if not self.plays:
            return None
        sig = self._signature()
        with self._profile_lock:
            if self._profile_sig != sig:
                s = self.settings()
                chosen = scope.select(self.plays, s.replay_set or "all")
                self._profile = build_profile_from(chosen, level=s.level_override) if chosen else None
                self._profile_sig, self._memo = sig, {}
            return self._profile

    def require_profile(self) -> Profile:
        p = self.profile()
        if p is None:
            if self.plays:
                raise NoProfile(
                    "None of the analysed replays is a passed play, so Best replays is empty — switch to All replays."
                )
            if self.restoring:
                raise NoProfile(RESTORING)
            raise NoProfile()
        return p

    def memo(self, key: str, compute: Callable[[], T]) -> T:
        """A value computed from the current profile, kept until the profile changes."""
        self.profile()
        with self._profile_lock:
            sig = self._profile_sig
            if key in self._memo:
                return self._memo[key]
        value = compute()
        with self._profile_lock:
            if self._profile_sig == sig:  # not if the profile was rebuilt meanwhile
                self._memo[key] = value
        return value

    def replay_set(self) -> str:
        rs = self.settings().replay_set or "all"
        return rs if rs in scope.REPLAY_SETS else "all"
