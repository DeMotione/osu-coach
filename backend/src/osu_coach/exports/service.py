"""Getting maps into osu!: lazer import folder, stable collection, .osz downloads."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING

from osu_coach.app.errors import ApiError, Invalid, NotFound
from osu_coach.beatmaps import sources
from osu_coach.exports import lazer_import
from osu_coach.exports.collection_db import dumps as collection_bytes
from osu_coach.exports.collection_db import merge_into
from osu_coach.exports.domain import sets_to_download
from osu_coach.exports.schemas import ExportPreview, ExportRequest, LazerPackResult, OszResult, StableMergeResult
from osu_coach.jobs.manager import Reporter
from osu_coach.replays import detect

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


# ------------------------------------------------------------------ exports
def _hashes(req: ExportRequest) -> list[str]:
    return list(dict.fromkeys(m.md5 for m in req.maps))


def _set_rows(req: ExportRequest) -> list[tuple[str, int]]:
    return [(m.md5, m.beatmapset_id) for m in req.maps]


def _stable_installs(ws: Workspace) -> list[detect.Install]:
    return [i for i in ws.installs() if i.kind == "stable"]


def export_preview(ws: Workspace, req: ExportRequest) -> ExportPreview:
    lib = ws.library
    have = lib.installed["lazer"] if lib is not None else set()
    sets = sets_to_download(_set_rows(req), have)
    stable = _stable_installs(ws)
    osz = (
        stable[0].songs
        if stable and stable[0].songs
        else Path.home() / "osu-coach-maps" / lazer_import.safe_name(req.name)
    )
    return ExportPreview(
        collection=req.name,
        preferred_client=ws.preferred_client(),
        total_sets=len({m.beatmapset_id for m in req.maps}),
        lazer_sets=len(sets),
        lazer_approximate=bool(lib is not None and lib.has_unread_maps("lazer")),
        lazer_folder=str(lazer_import.default_pack_dir(req.name)),
        stable_available=bool(stable),
        osz_folder=str(osz),
    )


def collection_db(req: ExportRequest) -> bytes:
    return collection_bytes({req.name: _hashes(req)})


def lazer_zip(req: ExportRequest) -> tuple[bytes, str]:
    return lazer_import.pack_zip({req.name: _hashes(req)}, req.name), f"{lazer_import.safe_name(req.name)}.zip"


def build_lazer_pack(ws: Workspace, req: ExportRequest, report: Reporter) -> LazerPackResult:
    """The lazer import folder: the collection plus the maps lazer doesn't have yet."""
    hashes, rows = _hashes(req), _set_rows(req)
    lib = ws.library
    if lib is not None and lib.has_unread_maps("lazer"):
        report.note("Checking which of these maps you already have…")
        # reads every file of the install a limited scan skipped when a map isn't there: the reports along the way
        # show that it is still going, and let a cancel stop it
        lib.find_maps(set(hashes), lambda msg: report.note(f"Checking which of these maps you already have ({msg})…"))
    sets = sets_to_download(rows, lib.installed["lazer"] if lib is not None else set())
    res = lazer_import.build_pack(lazer_import.default_pack_dir(req.name), {req.name: hashes}, sets, progress=report)
    if ws.config.reveal_folders:
        lazer_import.reveal(res["path"])
    return LazerPackResult(path=str(res["path"]), maps=list(res["maps"]), failed=list(res["failed"]))


def merge_stable(ws: Workspace, req: ExportRequest) -> StableMergeResult:
    stable = _stable_installs(ws)
    if not stable:
        raise NotFound("No osu!stable install found to add the collection to.", "no_stable_install")
    if detect.is_osu_running():
        raise ApiError(409, "osu_running", "Close osu! first — it rewrites collection.db when it exits.")
    res = merge_into(stable[0].root / "collection.db", {req.name: _hashes(req)})
    return StableMergeResult(path=str(res["path"]), backup=str(res["backup"]) if res.get("backup") else None)


def download_osz(folder: str, set_ids: list[int], report: Reporter) -> OszResult:
    dest = Path(folder).expanduser()
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Invalid(f"Can't use {folder}: {exc}", "bad_folder") from exc
    sets = list(dict.fromkeys(int(s) for s in set_ids))
    ok, failed = 0, []
    with closing(sources.download_many(sets, dest, report)) as done:
        for sid, path in done:
            if path:
                ok += 1
            else:
                failed.append(sid)
    return OszResult(folder=str(dest), downloaded=ok, failed=sorted(failed, key=sets.index))
