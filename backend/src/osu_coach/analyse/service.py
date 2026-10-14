"""Analysing the scanned replays: read the chosen replays, save the progress, build the profile, report the result."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from osu_coach.analyse.schemas import AnalysisRequest, AnalysisResult, AnalysisStatus, SkippedReplay
from osu_coach.app.errors import ApiError
from osu_coach.jobs.manager import Reporter
from osu_coach.library.service import require_library, select
from osu_coach.progress import repository as progress

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace

SKIPPED_SHOWN = 200


# ------------------------------------------------------------------ analysis
def run_analysis(ws: Workspace, req: AnalysisRequest, report: Reporter) -> AnalysisResult:
    lib = require_library(ws)
    sel = select(ws, req.player, int(req.latest), req.date_range, req.date_from, req.date_to)
    if not sel.refs:
        raise ApiError(
            409,
            "nothing_to_analyse",
            "No replays in that time range — choose a longer one." if sel.choice != "all" else "No replays to analyse.",
        )
    report(0, 1, "Preparing…")
    if req.online:
        missing = lib.missing_maps(sel.refs, progress=report.note)
        if missing:
            lib.fetch_missing(missing, progress=report)
    analyses, errors = lib.analyze(
        sel.refs,
        workers=ws.config.analysis_workers,
        progress=lambda done, total, _msg: report(done, total, f"Analysing replays… {done}/{total}"),
    )
    if not analyses:
        raise ApiError(
            422, "nothing_analysed", "None of the replays could be analysed. " + (errors[0][1] if errors else "")
        )
    warnings = []
    report.note("Saving your progress…")
    try:
        progress.update(lib.cache, analyses, lib.load_cached)
    except Exception as exc:  # noqa: BLE001 - the analysis matters more than the history
        warnings.append(f"Could not save your progress: {exc}")
    ws.set_analyses(analyses, errors, "All players" if sel.player == "*" else sel.player)
    ws.update_settings(player=sel.player)
    report.note("Building your profile…")
    prof = ws.profile()
    best = ws.replay_set() == "best"
    if prof is None:
        warnings.append("None of these replays is a passed play, so Best replays is empty — switch to All replays.")
    return AnalysisResult(
        analysed=len(analyses),
        skipped=len(errors),
        best_replays=len(prof.replays) if best and prof is not None else None,
        profile_ready=prof is not None,
        warnings=warnings,
    )


def analysis_status(ws: Workspace) -> AnalysisStatus:
    prof = ws.profile()
    return AnalysisStatus(
        analysed=len(ws.analyses),
        player_label=ws.player_label,
        replay_set=ws.replay_set(),
        profile_replays=len(prof.replays) if prof is not None else None,
        best_empty=bool(ws.analyses) and prof is None,
        skipped=[SkippedReplay(file=Path(ref["path"]).name, reason=err) for ref, err in ws.errors[:SKIPPED_SHOWN]],
        skipped_total=len(ws.errors),
    )
