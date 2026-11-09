"""Getting maps into osu!: maps straight into lazer, stable collection, .osz downloads."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING

from osu_coach.common.errors import ApiError, Invalid, NotFound
from osu_coach.domain.exports.downloads import sets_to_download, unknown_sets
from osu_coach.features.exports.schemas import (
    ExportPreview,
    ExportRequest,
    LazerOpened,
    LazerSendResult,
    OszResult,
    StableMergeResult,
)
from osu_coach.infra.beatmaps import sources
from osu_coach.infra.exports import lazer_import
from osu_coach.infra.exports.collection_db import dumps as collection_bytes
from osu_coach.infra.exports.collection_db import merge_into
from osu_coach.infra.jobs import Reporter
from osu_coach.infra.replays import detect

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


# ------------------------------------------------------------------ exports
def _hashes(req: ExportRequest) -> list[str]:
    return list(dict.fromkeys(m.md5 for m in req.maps))


def _set_rows(req: ExportRequest) -> list[tuple[str, int]]:
    return [(m.md5, m.beatmapset_id) for m in req.maps]


def _set_count(req: ExportRequest) -> int:
    """Beatmap sets in the request: the known ones, and each map without a known set as one."""
    known = {m.beatmapset_id for m in req.maps if m.beatmapset_id > 0}
    return len(known) + len({m.md5 for m in req.maps if m.beatmapset_id <= 0})


def _look_up_sets(md5s: list[str], report: Reporter) -> tuple[list[int], int]:
    """The beatmap sets of maps whose set isn't known, from osu.direct; and how many couldn't be found."""
    found, missing = [], 0
    for i, md5 in enumerate(md5s):
        report.note(f"Looking up maps without a known beatmap set ({i + 1} of {len(md5s)})…")
        meta = sources.lookup_md5(md5)
        sid = int((meta or {}).get("beatmapset_id") or 0)
        if sid > 0:
            if sid not in found:
                found.append(sid)
        else:
            missing += 1
    return found, missing


def _stable_installs(ws: Workspace) -> list[detect.Install]:
    return [i for i in ws.installs() if i.kind == "stable"]


def export_preview(ws: Workspace, req: ExportRequest) -> ExportPreview:
    lib = ws.library
    have = lib.installed["lazer"] if lib is not None else set()
    sets = sets_to_download(_set_rows(req), have)
    unknown = unknown_sets(_set_rows(req), have)
    stable = _stable_installs(ws)
    osz = (
        stable[0].songs
        if stable and stable[0].songs
        else Path.home() / "osu-coach-maps" / lazer_import.safe_name(req.name)
    )
    return ExportPreview(
        collection=req.name,
        preferred_client=ws.preferred_client(),
        total_sets=_set_count(req),
        lazer_sets=len(sets) + len(unknown),
        lazer_approximate=bool(unknown) or bool(lib is not None and lib.has_unread_maps("lazer")),
        stable_available=bool(stable),
        osz_folder=str(osz),
    )


def collection_db(req: ExportRequest) -> bytes:
    return collection_bytes({req.name: _hashes(req)})


def lazer_program() -> Path:
    """osu!lazer's program, or 404 ``no_lazer``."""
    exe = lazer_import.find_lazer()
    if exe is None:
        raise NotFound("osu!lazer wasn't found on this computer.", "no_lazer")
    return exe


def send_to_lazer(ws: Workspace, req: ExportRequest, report: Reporter, exe: Path | None = None) -> LazerSendResult:
    """The maps lazer doesn't have yet, downloaded and handed to lazer: it imports them and deletes the .osz."""
    exe = exe or lazer_program()
    hashes, rows = _hashes(req), _set_rows(req)
    lib = ws.library
    if lib is not None and lib.has_unread_maps("lazer"):
        report.note("Checking which of these maps you already have…")
        # reads every file of the install a limited scan skipped when a map isn't there: the reports along the way
        # show that it is still going, and let a cancel stop it
        lib.find_maps(set(hashes), lambda msg: report.note(f"Checking which of these maps you already have ({msg})…"))
    have = lib.installed["lazer"] if lib is not None else set()
    sets = sets_to_download(rows, have)
    looked_up, not_found = _look_up_sets(unknown_sets(rows, have), report)
    sets += [s for s in looked_up if s not in sets]
    if not sets:
        return LazerSendResult(not_found=not_found)
    res = lazer_import.download_and_send(exe, sets, ws.cache_dir / lazer_import.MAPS_DIR, report)
    return LazerSendResult(not_found=not_found, **res)


def open_in_lazer(beatmap_id: int) -> LazerOpened:
    """The map's page in lazer, with this difficulty picked."""
    return LazerOpened(link=lazer_import.open_map(lazer_program(), beatmap_id))


def merge_stable(ws: Workspace, req: ExportRequest) -> StableMergeResult:
    stable = _stable_installs(ws)
    if not stable:
        raise NotFound("No osu!stable install found to add the collection to.", "no_stable_install")
    if detect.is_osu_running():
        raise ApiError(409, "osu_running", "Close osu! first — it rewrites collection.db when it exits.")
    res = merge_into(stable[0].root / "collection.db", {req.name: _hashes(req)})
    return StableMergeResult(path=str(res["path"]), backup=str(res["backup"]) if res.get("backup") else None)


def known_sets(set_ids: list[int]) -> list[int]:
    """The beatmap sets that can be downloaded: known ones (above 0), each once."""
    sets = list(dict.fromkeys(int(s) for s in set_ids if int(s) > 0))
    if not sets:
        raise Invalid("None of these maps has a known beatmap set to download.", "no_sets")
    return sets


def download_osz(folder: str, set_ids: list[int], report: Reporter) -> OszResult:
    sets = known_sets(set_ids)
    dest = Path(folder).expanduser()
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Invalid(f"Can't use {folder}: {exc}", "bad_folder") from exc
    ok, failed = 0, []
    with closing(sources.download_many(sets, dest, report)) as done:
        for sid, path in done:
            if path:
                ok += 1
            else:
                failed.append(sid)
    return OszResult(folder=str(dest), downloaded=ok, failed=sorted(failed, key=sets.index))
