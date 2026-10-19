"""Finding replays (scan), choosing which to analyse (selection) and reading them."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from osu_coach.analysis.domain import ReplayAnalysis
from osu_coach.app.errors import ApiError, Invalid
from osu_coach.app.schemas import Count
from osu_coach.jobs.manager import Reporter
from osu_coach.library.repository import Library
from osu_coach.library.schemas import (
    AnalysisRequest,
    InstallOut,
    LibraryOut,
    PlayerCount,
    ScanRequest,
    ScanResult,
    SelectionOut,
)
from osu_coach.library.uploads import resolve_upload
from osu_coach.replays import detect, scope

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


@dataclass
class ScanArgs:
    """What the last scan read, so it can be repeated further back (more replays)."""

    installs: list[detect.Install] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    only: bool = False  # only these files, not the library
    map_installs: list[detect.Install] = field(default_factory=list)  # beatmaps only, for ``only``


def install_out(inst: detect.Install) -> InstallOut:
    return InstallOut(
        kind=inst.kind,
        root=str(inst.root),
        label=inst.label,
        songs=str(inst.songs) if inst.songs else None,
        replay_dirs=[str(d) for d in inst.replay_dirs],
        files_dir=str(inst.files_dir) if inst.files_dir else None,
        collection_db=str(inst.collection_db) if inst.collection_db else None,
    )


def add_install_path(ws: Workspace, path: str) -> detect.Install:
    """Remember an osu! folder that wasn't found automatically (``install_paths``); it is listed and scanned like
    the ones that were."""
    raw = path.strip().strip('"').strip()
    if not raw:
        raise Invalid("Enter the folder osu! is in.", "not_osu_folder")
    root = Path(raw).expanduser()
    inst = detect.install_at(root)
    if inst is None:
        raise Invalid(
            f"No osu! found in {root}. For osu!stable choose the folder with osu!.exe and Songs in it; "
            "for osu!lazer its data folder (the one with files and client.realm in it).",
            "not_osu_folder",
        )
    saved = ws.settings().get("install_paths")
    saved = [p for p in saved if isinstance(p, str)] if isinstance(saved, list) else []
    if str(inst.root) not in saved:
        ws.update_settings(install_paths=[*saved, str(inst.root)])
    ws.installs(refresh=True)
    return inst


# ------------------------------------------------------------------ scan
def scan_args(ws: Workspace, req: ScanRequest) -> ScanArgs:
    only = req.mode == "files"
    files = [str(resolve_upload(ws, f)) for f in req.files]
    if only and not files:
        raise Invalid("Add the replay files to analyse first.", "no_files")
    installs = ws.installs()
    chosen = installs if req.installs is None else [i for i in installs if str(i.root) in set(req.installs)]
    folders = [f.strip().strip('"') for f in req.folders if f.strip().strip('"')]
    return ScanArgs(
        installs=[] if only else chosen,
        folders=[] if only else folders,
        files=files,
        only=only,
        map_installs=list(installs) if only else [],
    )


def run_scan(ws: Workspace, args: ScanArgs, latest: int, report: Reporter) -> ScanResult:
    """Read the replays (and beatmaps) of the chosen sources into a new library; ``latest``: only the newest
    replays (0 = all)."""
    limit = latest or None
    lib = Library(ws.cache_dir)
    warnings = []
    report.note(f"Looking for your newest {limit} replays…" if limit else "Scanning for replays…")
    for inst in args.installs:
        report.note(f"Scanning {inst.label}…")
        lib.add_install(inst, progress=report.note, latest=limit)
    for f in args.folders:
        path = Path(f).expanduser()
        if path.is_dir():
            report.note(f"Scanning {path}…")
            lib.add_folder(path, latest=limit)
        else:
            warnings.append(f"Folder not found: {f}")
    if args.files:
        lib.add_files(args.files)
    for inst in args.map_installs:
        lib.add_map_source(inst)
    players = lib.players()
    if players and lib.has_unread_maps():
        report.note("Looking for the beatmaps of these replays…")
        lib.missing_maps(lib.eligible(players[0][0], limit), progress=report.note)
    ws.library, ws.scan_args = lib, args
    return ScanResult(
        replays=len(lib.standard_replays()), players=len(players), scan_limit=lib.scan_limit, warnings=warnings
    )


def needs_more(lib: Library, latest: int) -> bool:
    """The last scan stopped earlier than ``latest`` replays (0 = all) asks for."""
    return lib.scan_limit is not None and (not latest or latest > lib.scan_limit)


def library_out(ws: Workspace) -> LibraryOut:
    lib = ws.library
    if lib is None:
        return LibraryOut(scanned=False, mode=None, sources=[], scan_limit=None, replays=0, players=[])
    return LibraryOut(
        scanned=True,
        mode="files" if ws.scan_args and ws.scan_args.only else "library",
        sources=list(lib.sources),
        scan_limit=lib.scan_limit,
        replays=len(lib.standard_replays()),
        players=[PlayerCount(name=n, replays=c) for n, c in lib.players()],
    )


def require_library(ws: Workspace) -> Library:
    if ws.library is None:
        raise ApiError(409, "not_scanned", "Scan for replays first.")
    return ws.library


# ------------------------------------------------------------------ selection
@dataclass
class Selection:
    player: str
    players: list[tuple[str, int]]
    refs: list[dict]
    found: int
    limit: int | None
    only: bool
    choice: str
    start: dt.date | None
    end: dt.date | None
    since: dt.datetime | None


def select(
    ws: Workspace, player: str | None, latest: int, date_range: str, date_from: dt.date | None, date_to: dt.date | None
) -> Selection:
    """The replays an analysis with these choices reads: the player's (``*`` = everyone's) newest first, in the
    time range, at most ``latest`` (only when scanning the library, not dropped files)."""
    lib = require_library(ws)
    players = lib.players()
    if not players:
        raise ApiError(
            409, "no_replays", "No osu!standard replays found there (relax/autopilot/autoplay replays are skipped)."
        )
    names = [n for n, _ in players]
    opts = names + (["*"] if len(names) > 1 else [])
    player = player if player in opts else names[0]
    only = bool(ws.scan_args and ws.scan_args.only)
    limit = None if only else (latest or None)
    every = lib.eligible(player)
    choice = "all" if only else date_range
    start = end = None
    if choice == "custom":
        today = dt.date.today()
        start, end = date_from or today - dt.timedelta(days=30), date_to or today
        if start > end:
            raise Invalid("The start of the date range is after its end.", "bad_date_range")
    since, until = scope.date_window(choice, [r.get("timestamp") for r in every], start, end)
    refs = scope.filter_refs(every, since, until)[:limit]
    counts = dict(players)
    found = sum(counts.values()) if player == "*" else counts.get(player, 0)
    return Selection(
        player=player,
        players=players,
        refs=refs,
        found=found,
        limit=limit,
        only=only,
        choice=choice,
        start=start,
        end=end,
        since=since,
    )


def selection_out(ws: Workspace, sel: Selection) -> SelectionOut:
    lib = require_library(ws)
    missing = lib.missing_maps(sel.refs)  # looks in the parts of the installs a limited scan didn't read
    names = [n for n, _ in sel.players]
    left = lib.left_out(sel.player, since=sel.refs[-1]["timestamp"] if sel.limit and sel.refs else None)
    return SelectionOut(
        player=sel.player,
        players=[PlayerCount(name=n, replays=c) for n, c in sel.players],
        files_mode=sel.only,
        replays=len(sel.refs),
        found=sel.found,
        newest_only=bool(sel.limit and sel.found > len(sel.refs)),
        missing_maps=len(missing),
        date_range=sel.choice,
        date_from=sel.start,
        date_to=sel.end,
        empty_range=not sel.refs and sel.choice != "all",
        older_hint=bool(lib.scan_limit and sel.limit and sel.player not in ("*", names[0]) and sel.found < sel.limit),
        left_out=[Count(label=reason, count=n) for reason, n in left.most_common(3)],
        left_out_total=sum(left.values()),
    )


# ------------------------------------------------------------------ analysis
def analyse_selection(
    ws: Workspace, req: AnalysisRequest, report: Reporter
) -> tuple[Selection, list[ReplayAnalysis], list[tuple[dict, str]]]:
    """Fetch what is missing (when online) and analyse the selected replays. What to do with the analyses
    (progress history, profile) is up to the caller: see ``app.session``."""
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
    return sel, analyses, errors
