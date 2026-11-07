"""The analysis session: reading the replays, keeping their progress history, building the profile.

What a scan and an analysis read is remembered in ``session.json`` (:mod:`osu_coach.infra.session_store`), so the
next start picks up where this one stopped.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from osu_coach.features.library import service as library
from osu_coach.features.library.schemas import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisStatus,
    ScanResult,
    SkippedReplay,
)
from osu_coach.features.library.service import analyze_selection
from osu_coach.infra import progress, session_store, summaries
from osu_coach.infra.jobs import Reporter
from osu_coach.infra.library import ScanArgs, load_cached_analyses

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace

log = logging.getLogger(__name__)
SKIPPED_SHOWN = 200


def _save(ws: Workspace, **sections: dict) -> None:
    try:
        session_store.update(ws.cache_dir, **sections)
    except OSError:  # remembering the session is a convenience, never a reason to fail the work
        log.warning("could not save the session", exc_info=True)


def _save_scan(ws: Workspace, args: ScanArgs) -> None:
    _save(
        ws,
        scan={
            "installs": [str(i.root) for i in args.installs],
            "map_installs": [str(i.root) for i in args.map_installs],
            "folders": args.folders,
            "files": args.files,
            "only": args.only,
        },
    )


def run_scan(ws: Workspace, args: ScanArgs, report: Reporter) -> ScanResult:
    """The scan job; what it read is remembered for the next start."""
    result = library.run_scan(ws, args, report)
    _save_scan(ws, args)
    return result


def forget_files(ws: Workspace) -> None:
    """Forget the files added by hand, also for the next start."""
    library.forget_files(ws)
    if ws.scan_args is not None:
        _save_scan(ws, ws.scan_args)


def start_restore(ws: Workspace) -> None:
    """Pick up the last session in the background (a scan job, so it shows like any other and the server starts at
    once): the analysed replays come back from their summaries (made from the analysis cache the first time, which
    can take a while), then the last scan is repeated. Does nothing without a saved session."""
    saved = session_store.load(ws.cache_dir)
    scan = saved.get("scan")
    rescan = isinstance(scan, dict) and _scan_usable(scan)
    restore = _has_analyses(saved.get("analysis"))
    if not rescan and not restore:
        return

    def work(report: Reporter) -> ScanResult | None:
        report.note("Restoring your last session…")
        try:
            _restore_analyses(ws, saved.get("analysis"))
        finally:
            ws.set_restoring(False)  # the pages say "restoring" until here, not "nothing analysed"
        if not rescan:
            return None
        installs = ws.installs()
        roots = set(scan.get("installs", []))
        maps = set(scan.get("map_installs", []))
        only = bool(scan.get("only"))
        args = ScanArgs(
            installs=[i for i in installs if str(i.root) in roots],
            folders=[f for f in scan.get("folders", []) if Path(f).expanduser().is_dir()],
            files=[f for f in scan.get("files", []) if Path(f).is_file()],
            only=only,
            map_installs=[i for i in installs if str(i.root) in maps],
        )
        return run_scan(ws, args, report)  # every replay, also when an older version saved a limit ("latest")

    ws.set_restoring(restore)
    try:
        ws.jobs.start("scan", "Restoring your last session", work)
    except Exception:
        ws.set_restoring(False)
        raise


def _scan_usable(scan: dict) -> bool:
    if scan.get("only"):
        return any(Path(f).is_file() for f in scan.get("files", []))
    return bool(scan.get("installs")) or any(Path(f).expanduser().is_dir() for f in scan.get("folders", []))


def _has_analyses(saved: object) -> bool:
    return isinstance(saved, dict) and isinstance(saved.get("keys"), list) and bool(saved["keys"])


def _restore_analyses(ws: Workspace, saved: object) -> None:
    """The analysed replays of the last session, only if every one of them is still in the analysis cache (a
    partial set would give a misleading profile)."""
    if not _has_analyses(saved):
        return
    try:
        keys = [str(k) for k in saved["keys"]]
        plays = summaries.summaries_of(ws.cache_dir, keys, lambda missing: load_cached_analyses(ws.cache_dir, missing))
        if len(plays) != len(keys):
            return
        errors = [
            ({"path": str(e["path"])}, str(e["reason"]))
            for e in saved.get("errors", [])
            if isinstance(e, dict) and "path" in e and "reason" in e
        ]
        ws.set_plays(plays, errors, str(saved.get("player_label", "")))
    except Exception:  # noqa: BLE001 - a broken session file must not keep the app from starting
        log.warning("could not restore the analysed replays", exc_info=True)


def run_analysis(ws: Workspace, req: AnalysisRequest, report: Reporter) -> AnalysisResult:
    sel, analyses, errors = analyze_selection(ws, req, report)
    lib = ws.library
    warnings = []
    plays = summaries.summarize(ws.cache_dir, analyses)
    del analyses  # only the summaries are kept
    report.note("Saving your progress…")
    try:  # the history is SQLite; it stays when replays or caches are deleted
        progress.update(lib.cache, plays, lambda keys: summaries.summaries_of(ws.cache_dir, keys, lib.load_cached))
    except Exception as exc:  # noqa: BLE001 - the analysis matters more than the history
        warnings.append(f"Could not save your progress: {exc}")
    ws.set_plays(plays, errors, "All players" if sel.player == "*" else sel.player)
    _save(
        ws,
        analysis={
            "keys": [a.key for a in plays],
            "player_label": ws.player_label,
            "errors": [{"path": ref["path"], "reason": err} for ref, err in errors],
        },
    )
    ws.update_settings(player=sel.player)
    report.note("Building your profile…")
    prof = ws.profile()
    best = ws.replay_set() == "best"
    if prof is None:
        warnings.append("None of these replays is a passed play, so Best replays is empty — switch to All replays.")
    return AnalysisResult(
        analysed=len(plays),
        skipped=len(errors),
        best_replays=len(prof.replays) if best and prof is not None else None,
        profile_ready=prof is not None,
        warnings=warnings,
    )


def analysis_status(ws: Workspace) -> AnalysisStatus:
    prof = ws.profile()
    return AnalysisStatus(
        analysed=len(ws.plays),
        player_label=ws.player_label,
        replay_set=ws.replay_set(),
        profile_replays=len(prof.replays) if prof is not None else None,
        best_empty=bool(ws.plays) and prof is None,
        skipped=[SkippedReplay(file=Path(ref["path"]).name, reason=err) for ref, err in ws.errors[:SKIPPED_SHOWN]],
        skipped_total=len(ws.errors),
        restoring=ws.restoring,
    )
