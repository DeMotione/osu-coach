"""Finding replays (scan), choosing which to analyse (selection) and reading them."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from osu_coach.common.errors import ApiError, Invalid, NotFound
from osu_coach.common.schemas import Count
from osu_coach.domain.analysis.models import Play
from osu_coach.domain.replays import scope
from osu_coach.features.library.schemas import (
    AnalysisRequest,
    InstallOut,
    LibraryOut,
    PlayerCount,
    ScanRequest,
    ScanResult,
    SelectionOut,
    UploadedFile,
)
from osu_coach.infra import clock
from osu_coach.infra.jobs import Reporter
from osu_coach.infra.library import Library, ScanArgs
from osu_coach.infra.replays import detect
from osu_coach.infra.uploads import MAX_UPLOAD_BYTES, UPLOAD_SUFFIXES, find_upload, safe_upload_name, upload_target

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


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
    saved = ws.settings().install_paths or []
    if str(inst.root) not in saved:
        ws.update_settings(install_paths=[*saved, str(inst.root)])
    ws.installs(refresh=True)
    return inst


# ------------------------------------------------------------------ scan
def kept_files(ws: Workspace) -> list[str]:
    """The replay and beatmap files added by hand in earlier scans that are still there."""
    return [f for f in (ws.scan_args.files if ws.scan_args else []) if Path(f).is_file()]


def scan_args(ws: Workspace, req: ScanRequest) -> ScanArgs:
    """What a scan reads. Files added by hand are kept: the new ones are added to the ones added before (each file
    once), so adding a few replays later doesn't drop the rest (#38)."""
    only = req.mode == "files"
    files = list(dict.fromkeys(kept_files(ws) + [str(resolve_upload(ws, f)) for f in req.files]))
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


def run_scan(ws: Workspace, args: ScanArgs, report: Reporter) -> ScanResult:
    """Read every replay (and the beatmaps) of the chosen sources into a new library. How many of them are
    analysed is chosen afterwards (``select``), so the count found is the full one (#36)."""
    lib = Library(ws.cache_dir)
    warnings = []
    report.note("Scanning for replays…")
    for inst in args.installs:
        report.note(f"Scanning {inst.label}…")
        lib.add_install(inst, progress=report.note)
    for f in args.folders:
        path = Path(f).expanduser()
        if path.is_dir():
            report.note(f"Scanning {path}…")
            lib.add_folder(path)
        else:
            warnings.append(f"Folder not found: {f}")
    if args.files:
        lib.add_files(args.files)
    for inst in args.map_installs:
        lib.add_map_source(inst)
    players = lib.players()
    if players and lib.has_unread_maps():
        report.note("Looking for the beatmaps of these replays…")
        lib.missing_maps(lib.eligible(players[0][0]), progress=report.note)
    ws.set_library(lib, args)
    return ScanResult(replays=len(lib.standard_replays()), players=len(players), warnings=warnings)


def _file_out(path: str) -> UploadedFile:
    p = Path(path)
    return UploadedFile(
        id=p.name, name=p.name, path=path, kind=UPLOAD_SUFFIXES[p.suffix.lower()], size=p.stat().st_size
    )


def library_out(ws: Workspace) -> LibraryOut:
    lib = ws.library
    if lib is None:
        return LibraryOut(scanned=False, mode=None, sources=[], replays=0, players=[], files=[])
    return LibraryOut(
        scanned=True,
        mode="files" if ws.scan_args and ws.scan_args.only else "library",
        sources=list(lib.sources),
        replays=len(lib.standard_replays()),
        players=[PlayerCount(name=n, replays=c) for n, c in lib.players()],
        files=[_file_out(f) for f in kept_files(ws) if Path(f).suffix.lower() in UPLOAD_SUFFIXES],
    )


def forget_files(ws: Workspace) -> None:
    """Drop the files added by hand: from the next scans, and their replays from the library now."""
    args = ws.scan_args
    if args is None or not args.files:
        return
    gone = set(args.files)
    ws.set_library(ws.library, replace(args, files=[]))
    if ws.library is not None:
        ws.library.replays = [r for r in ws.library.replays if r.get("path") not in gone]


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
        today = clock.today()
        start, end = date_from or today - dt.timedelta(days=30), date_to or today
        if start > end:
            raise Invalid("The start of the date range is after its end.", "invalid_date_range")
    since, until = scope.date_window(
        choice, [r.get("timestamp") for r in every], start, end, now=clock.now(), tz=clock.local_tz()
    )
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
    missing = lib.missing_maps(sel.refs)  # looks in the beatmap sources not read yet (only dropped files)
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
        left_out=[Count(label=reason, count=n) for reason, n in left.most_common(3)],
        left_out_total=sum(left.values()),
    )


# ------------------------------------------------------------------ analysis
def analyze_selection(
    ws: Workspace, req: AnalysisRequest, report: Reporter
) -> tuple[Selection, list[Play], list[tuple[dict, str]]]:
    """Fetch what is missing (when online) and analyse the selected replays. What to do with the analyses
    (progress history, profile) is up to the caller: see :mod:`osu_coach.features.library.session`."""
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


def save_upload(ws: Workspace, name: str, data: bytes) -> UploadedFile:
    clean = safe_upload_name(name)
    kind = UPLOAD_SUFFIXES.get(Path(clean).suffix.lower())
    if kind is None:
        raise Invalid(f"{name}: only .osr replays and .osu beatmaps can be added.", "unsupported_file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise Invalid(f"{name}: file too large.", "file_too_large")
    dest = upload_target(ws.cache_dir, clean)
    dest.write_bytes(data)
    return UploadedFile(id=clean, name=name, path=str(dest), kind=kind, size=len(data))


def resolve_upload(ws: Workspace, upload_id: str) -> Path:
    """An uploaded file by its id; only files inside the uploads folder."""
    p = find_upload(ws.cache_dir, upload_id)
    if p is None:
        raise NotFound(f"Uploaded file {upload_id} not found — add it again.", "upload_not_found")
    return p
