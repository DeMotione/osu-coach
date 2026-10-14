"""The analysis session: reading the replays, keeping their progress history, building the profile.

This ties the library, progress and profile features together, so it sits here in the composition layer
rather than in any one of them.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from osu_coach.jobs.manager import Reporter
from osu_coach.library.schemas import AnalysisRequest, AnalysisResult, AnalysisStatus, SkippedReplay
from osu_coach.library.service import analyse_selection
from osu_coach.progress import repository as progress

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace

SKIPPED_SHOWN = 200


def run_analysis(ws: Workspace, req: AnalysisRequest, report: Reporter) -> AnalysisResult:
    sel, analyses, errors = analyse_selection(ws, req, report)
    lib = ws.library
    warnings = []
    report.note("Saving your progress…")
    try:  # the history is SQLite; it stays when replays or caches are deleted
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
