"""Analyse new plays by themselves (#71).

A thread polls the osu! installs of the last scan for replays osu! saves while osu! coach runs
(:class:`~osu_coach.replays.watch.ReplayWatcher`). A new one is added to the library (no rescan: the scan's other
files haven't changed), and when the saved Analyse choices (player, time range, newest N) take it in, the analysis
runs again with those choices as an ``analysis`` job: only the new replay is really analysed, the rest come from the
cache. Its result names the new plays, so the web app can say so. Busy with another job: it tries again later.
Off with the ``auto_analyse`` setting; nothing to watch in files-only mode or before a scan.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from osu_coach.app import session
from osu_coach.app.errors import ApiError, Busy
from osu_coach.library.schemas import AnalysisRequest, AnalysisResult, NewPlay
from osu_coach.library.service import select
from osu_coach.replays.watch import ReplayWatcher
from osu_coach.settings.service import app_settings

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace
    from osu_coach.jobs.manager import Job, Reporter

log = logging.getLogger("osu_coach.app.autoanalyse")
POLL_S = 3.0


def _request(ws: Workspace) -> AnalysisRequest:
    """The analysis the Replays page would run now: its choices are saved in the settings."""
    s = app_settings(ws)
    return AnalysisRequest(
        player=s.player, latest=s.latest, date_range=s.date_range, date_from=s.date_from, date_to=s.date_to
    )


def _key(path: str) -> str | None:
    try:
        return hashlib.md5(Path(path).read_bytes()).hexdigest()  # the analysis cache's key (Library.analyze)
    except OSError:
        return None


class AutoAnalyser:
    def __init__(self, ws: Workspace, interval: float = POLL_S):
        self.ws = ws
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._watcher: ReplayWatcher | None = None
        self._watching: tuple = ()
        self._new: list[tuple[Path, str]] = []  # noticed, not in the library yet
        self._ready: list[str] = []  # in the library and in the analysis choices: to analyse

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="auto-analyse", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - one bad poll must not end the watching
                log.exception("auto-analyse failed")

    def tick(self) -> Job | None:
        """One poll: notice new replays, add them, start the analysis when nothing else runs (returned)."""
        ws, args = self.ws, self.ws.scan_args
        if not app_settings(ws).auto_analyse or args is None or args.only or ws.library is None:
            self._watcher, self._watching, self._new, self._ready = None, (), [], []
            return None
        watching = tuple((i.kind, str(i.root)) for i in args.installs)
        if self._watcher is None or watching != self._watching:  # (re)start: only what osu! saves from now on
            self._watcher, self._watching = ReplayWatcher(args.installs), watching
            return None
        self._new += self._watcher.poll()
        if self._new:
            try:
                with ws.gate.hold("Adding your new play"):
                    self._ready += self._add(self._new)
            except Busy:
                return None  # a scan or an analysis is running: next time
            self._new = []
        if not self._ready:
            return None
        paths = list(self._ready)
        try:
            job = ws.jobs.start("analysis", "Analysing your new play", lambda report: self._analyse(paths, report))
        except Busy:
            return None
        self._ready = []
        return job

    def _add(self, found: list[tuple[Path, str]]) -> list[str]:
        """Add the replays to the library; the ones the analysis choices take in (player, time range)."""
        lib = self.ws.library
        for kind in {k for _, k in found}:
            lib.add_files([p for p, k in found if k == kind], source=kind)
        paths = {str(p) for p, _ in found}
        req = _request(self.ws)
        try:
            sel = select(self.ws, req.player, int(req.latest), req.date_range, req.date_from, req.date_to)
        except ApiError:
            return []
        return [r["path"] for r in sel.refs if r["path"] in paths]

    def _analyse(self, paths: list[str], report: Reporter) -> AnalysisResult:
        result = session.run_analysis(self.ws, _request(self.ws), report)
        by_key = {a.key: a for a in self.ws.analyses}
        new = []
        for path in paths:
            a = by_key.get(_key(path) or "")
            if a is not None:
                new.append(NewPlay(path=path, map=str(a.meta.get("map_name") or a.meta.get("title") or "a map")))
        return result.model_copy(update={"new_plays": new})
