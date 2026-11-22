"""Finding replays (scan), choosing which to analyse (selection) and reading them."""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from osu_coach.common.errors import ApiError, Invalid, NotFound
from osu_coach.common.schemas import Count
from osu_coach.domain.analysis.estimate import DOWNLOAD, STARTUP, STORED, Plan, analysis_seconds, parallel_work
from osu_coach.domain.player import PlaySummary
from osu_coach.domain.replays import eligibility, scope
from osu_coach.domain.replays.selection import MOST_REPLAYS
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
from osu_coach.infra import analysis_speed, clock
from osu_coach.infra.jobs import Reporter
from osu_coach.infra.library import Library, ScanArgs, default_workers
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
def _days(ws: Workspace) -> int:
    """How many days back a scanned library's replays are analysed (0: any age)."""
    days = ws.config.recent_days
    return scope.RECENT_DAYS if days is None else days


def _oldest(ws: Workspace, now: dt.datetime) -> dt.datetime | None:
    days = _days(ws)
    return scope.recent_start(now, days) if days else None


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
    if req.installs is None:
        skipped = set(ws.settings().skipped_installs)
        chosen = [i for i in installs if str(i.root) not in skipped]
    else:
        chosen = [i for i in installs if str(i.root) in set(req.installs)]
    folders = [f.strip().strip('"') for f in req.folders if f.strip().strip('"')]
    return ScanArgs(
        installs=[] if only else chosen,
        folders=[] if only else folders,
        files=files,
        only=only,
        map_installs=list(installs) if only else [],
    )


def run_scan(ws: Workspace, args: ScanArgs, report: Reporter) -> ScanResult:
    """Read the replays (and the beatmaps) of the chosen sources into a new library: newest first, until the newest
    ``MOST_REPLAYS`` of the player are certain (the one analysed last, else whoever has the most replays: you) or
    the files are older than the last year (``scope.RECENT_DAYS``). How
    many of them are analysed is chosen afterwards (``select``, #36). The beatmaps are then looked up only for those
    replays, not read from the whole Songs folder (#95)."""
    lib = Library(ws.cache_dir)
    warnings = []
    player = ws.settings().player or None
    since = _oldest(ws, clock.now())
    oldest = since.timestamp() if since else None  # older files can't hold a play of the last year
    report.note("Scanning for replays…")
    for inst in args.installs:
        report.note(f"Scanning {inst.label}…")
        lib.add_install(inst, progress=report.note, latest=MOST_REPLAYS, player=player, oldest=oldest)
    for f in args.folders:
        path = Path(f).expanduser()
        if path.is_dir():
            report.note(f"Scanning {path}…")
            lib.add_folder(path, latest=MOST_REPLAYS, player=player, oldest=oldest)
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
    oldest: dt.datetime | None = None  # the last year's start (a scanned library, not files added by hand)


def select(
    ws: Workspace, player: str | None, latest: int, date_range: str, date_from: dt.date | None, date_to: dt.date | None
) -> Selection:
    """The replays an analysis with these choices reads: the player's (``*`` = everyone's) newest first, in the
    time range, at most ``latest``. A scanned library's are of the last year only (``scope.RECENT_DAYS``); files
    added by hand are taken whenever they were played, the newest ``MOST_REPLAYS`` of them."""
    lib = require_library(ws)
    only = bool(ws.scan_args and ws.scan_args.only)
    now = clock.now()
    oldest = None if only else _oldest(ws, now)
    every_player = lib.standard_replays()
    recent = every_player if oldest is None else scope.filter_refs(every_player, oldest, None)
    players = eligibility.player_counts(recent)
    if not players:
        if every_player:
            raise ApiError(
                409,
                "no_recent_replays",
                f"The replays found there are all older than a year: only the plays of the last {_days(ws)} days "
                "are analysed.",
            )
        raise ApiError(
            409, "no_replays", "No osu!standard replays found there (relax/autopilot/autoplay replays are skipped)."
        )
    names = [n for n, _ in players]
    opts = names + (["*"] if len(names) > 1 else [])
    player = player if player in opts else names[0]
    limit = min(latest or MOST_REPLAYS, MOST_REPLAYS)  # files added by hand too: their newest
    every = lib.eligible(player)
    if oldest is not None:
        every = scope.filter_refs(every, oldest, None)
    choice = "all" if only else date_range
    start = end = None
    if choice == "custom":
        today = clock.today()
        start, end = date_from or today - dt.timedelta(days=30), date_to or today
        if start > end:
            raise Invalid("The start of the date range is after its end.", "invalid_date_range")
    since, until = scope.date_window(
        choice, [r.get("timestamp") for r in every], start, end, now=now, tz=clock.local_tz()
    )
    if oldest is not None:
        since = max(since, oldest) if since else oldest
    refs = scope.filter_refs(every, since, until)[:limit]
    found = len(every)
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
        oldest=oldest,
    )


def estimate(ws: Workspace, refs: list[dict]) -> tuple[Plan, float]:
    """What analysing these replays takes, and how long it is expected to (on this computer, as far as measured)."""
    plan = require_library(ws).plan(refs)
    return plan, analysis_seconds(plan, _workers(ws), analysis_speed.speed(ws.cache_dir))


def _workers(ws: Workspace) -> int:
    return ws.config.analysis_workers or default_workers()


def selection_out(ws: Workspace, sel: Selection) -> SelectionOut:
    lib = require_library(ws)
    missing = lib.missing_maps(sel.refs)  # looks in the beatmap sources not read yet (only dropped files)
    oldest = sel.oldest.isoformat() if sel.oldest else None
    left = lib.left_out(sel.player, since=sel.refs[-1]["timestamp"] if sel.limit and sel.refs else oldest)
    plan, seconds = estimate(ws, sel.refs)
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
        recent_days=_days(ws) if sel.oldest else None,
        already_analysed=plan.stored,
        estimate_seconds=round(seconds, 1),
        download_seconds=round(DOWNLOAD * len(missing), 1),
    )


# ------------------------------------------------------------------ analysis
def analyze_selection(
    ws: Workspace, req: AnalysisRequest, report: Reporter
) -> tuple[Selection, list[PlaySummary], list[tuple[dict, str]]]:
    """Fetch what is missing (when online) and analyse the selected replays, giving their summaries: made in worker
    processes, so the job never holds every play's notes (``Library.summarize_replays``). What to do with them
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
    plan, seconds = estimate(ws, sel.refs)
    missing = lib.missing_maps(sel.refs, progress=report.note) if ws.settings().online(req.online) else []
    report.detail(replays=len(sel.refs), estimate_seconds=round(seconds + DOWNLOAD * len(missing), 1))
    if missing:
        lib.fetch_missing(missing, progress=report)
    started = time.monotonic()
    plays, errors = lib.summarize_replays(
        sel.refs,
        workers=ws.config.analysis_workers,
        progress=lambda done, total, _msg: report(done, total, f"Analysing replays… {done}/{total}"),
    )
    # how fast this computer is: the next estimates follow it
    took = time.monotonic() - started - STARTUP - STORED * plan.stored
    analysis_speed.record(ws.cache_dir, parallel_work(plan, _workers(ws)), took, len(plan.new))
    if not plays:
        raise ApiError(
            422, "nothing_analysed", "None of the replays could be analysed. " + (errors[0][1] if errors else "")
        )
    return sel, plays, errors


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
