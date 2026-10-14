"""Map Suggestion, playlists (Skill Development) and getting maps into osu! (lazer import folder, stable
collection, .osz downloads)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from osu_coach.infrastructure.filesystem import lazer_import, locate
from osu_coach.infrastructure.http import sources
from osu_coach.infrastructure.filesystem.collection_db import dumps as collection_bytes
from osu_coach.domain.collection_policy import sets_to_download
from osu_coach.infrastructure.filesystem.collection_db import merge_into
from osu_coach.domain.map_recommendations import (
    SKILLS,
    Targets,
    build_playlist,
    collection_name,
    recommendations,
    skill_label,
    targets_from_profile,
)
from osu_coach.domain.profile import Profile

from osu_coach.api.convert import integer, num, text
from osu_coach.api.errors import ApiError, Invalid, NotFound
from osu_coach.api.state.jobs import Reporter
from osu_coach.api.schemas.exports import ExportPreview, ExportRequest, LazerPackResult, OszResult, StableMergeResult
from osu_coach.api.schemas.maps import MapRow, Playlist, PlaylistSkill, PlaylistStage, Suggestions, SuggestionSection
from osu_coach.api.state.workspace import Workspace

SUGGESTIONS_PER_SKILL = 5
PLAYLIST_SKILLS = SKILLS + ["quadrant", "general"]


def map_rows(df: pd.DataFrame | None) -> list[MapRow]:
    if df is None or df.empty:
        return []
    rows = []
    for r in df.to_dict("records"):
        rows.append(MapRow(
            md5=str(r["md5"]), beatmap_id=integer(r.get("beatmap_id")) or 0,
            beatmapset_id=integer(r.get("beatmapset_id")) or 0, artist=text(r.get("artist")) or "",
            title=text(r.get("title")) or "", version=text(r.get("version")) or "", creator=text(r.get("creator")),
            stars=num(r.get("stars")), bpm=num(r.get("bpm")), ar=num(r.get("ar")), od=num(r.get("od")),
            length_s=num(r.get("drain_length")), why=text(r.get("why")) or "", url=text(r.get("url")) or "",
            stage=text(r.get("stage")), goal=text(r.get("goal"))))
    return rows


def _pool(ws: Workspace) -> pd.DataFrame:
    pool = ws.pool()
    if pool.empty:
        raise ApiError(500, "pool_missing", "The bundled map pool is missing.")
    return pool


# ------------------------------------------------------------------ suggestions
def suggestions(ws: Workspace, p: Profile) -> Suggestions:
    pool = _pool(ws)
    t = targets_from_profile(p)
    hidden = set(ws.settings().get("hidden_maps") or [])
    if hidden:
        pool = pool[~pool["md5"].isin(hidden)]
    sections = []
    for sk, df in recommendations(pool, p, per_skill=SUGGESTIONS_PER_SKILL):
        title = "Level up" if sk == "general" else skill_label(sk, t)
        score = None if sk in ("general", "quadrant") else num(p.skills.get(sk, {}).get("score"))
        sections.append(SuggestionSection(skill=sk, title=title, score=score,
                                          maps=map_rows(df.assign(stage=skill_label(sk, t)))))
    return Suggestions(comfort=float(t.comfort), pool_size=len(ws.pool()), hidden=len(hidden), sections=sections,
                       collection_name=f"osu-coach: Map Suggestion ({t.comfort:.1f}★)",
                       preferred_client=ws.preferred_client())


def hide(ws: Workspace, md5s: list[str]) -> int:
    hidden = set(ws.settings().get("hidden_maps") or []) | set(md5s)
    ws.update_settings(hidden_maps=sorted(hidden))
    return len(hidden)


# ------------------------------------------------------------------ playlists
def playlist(ws: Workspace, skill: str | None, n: int, comfort: float | None) -> Playlist:
    pool = _pool(ws)
    p = ws.profile()
    if p is not None:
        t = targets_from_profile(p)
    else:
        t = Targets(comfort=float(comfort if comfort is not None else ws.settings().get("manual_comfort", 2.5)))
    options = SKILLS + (["quadrant"] if t.quadrant else [])
    default = p.weaknesses[0] if p is not None and p.weaknesses else "aim"
    default = default if default in options else options[0]
    skill = skill or default
    if skill not in PLAYLIST_SKILLS:
        raise Invalid(f"Unknown skill {skill}.", "unknown_skill")
    if skill == "quadrant" and not t.quadrant:
        raise ApiError(409, "no_weak_quadrant", "No clearly weak quadrant in your replays — pick another skill.")
    pl = build_playlist(pool, skill, t, n=n)
    stages = [PlaylistStage(stage=str(stage), goal=str(part["goal"].iloc[0]), maps=map_rows(part))
              for stage, part in pl.groupby("stage", sort=False)] if not pl.empty else []
    skills = [PlaylistSkill(key=k, label=skill_label(k, t),
                            score=num(p.skills.get(k, {}).get("score")) if p is not None else None) for k in options]
    return Playlist(skill=skill, skills=skills, default_skill=default, has_profile=p is not None,
                    comfort=float(t.comfort), stream_bpm=num(t.stream_bpm), maps=n,
                    collection_name=collection_name(skill, t), stages=stages, preferred_client=ws.preferred_client())


# ------------------------------------------------------------------ exports
def _hashes(req: ExportRequest) -> list[str]:
    return list(dict.fromkeys(m.md5 for m in req.maps))


def _set_rows(req: ExportRequest) -> list[tuple[str, int]]:
    return [(m.md5, m.beatmapset_id) for m in req.maps]


def _stable_installs(ws: Workspace) -> list[locate.Install]:
    return [i for i in ws.installs() if i.kind == "stable"]


def export_preview(ws: Workspace, req: ExportRequest) -> ExportPreview:
    lib = ws.library
    have = lib.installed["lazer"] if lib is not None else set()
    sets = sets_to_download(_set_rows(req), have)
    stable = _stable_installs(ws)
    osz = stable[0].songs if stable and stable[0].songs else \
        Path.home() / "osu-coach-maps" / lazer_import.safe_name(req.name)
    return ExportPreview(collection=req.name, preferred_client=ws.preferred_client(),
                         total_sets=len({m.beatmapset_id for m in req.maps}), lazer_sets=len(sets),
                         lazer_approximate=bool(lib is not None and lib.has_unread_maps("lazer")),
                         lazer_folder=str(lazer_import.default_pack_dir(req.name)),
                         stable_available=bool(stable), osz_folder=str(osz))


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
        lib.find_maps(set(hashes))
    sets = sets_to_download(rows, lib.installed["lazer"] if lib is not None else set())
    res = lazer_import.build_pack(lazer_import.default_pack_dir(req.name), {req.name: hashes}, sets, progress=report)
    if ws.config.reveal_folders:
        lazer_import.reveal(res["path"])
    return LazerPackResult(path=str(res["path"]), maps=list(res["maps"]), failed=list(res["failed"]))


def merge_stable(ws: Workspace, req: ExportRequest) -> StableMergeResult:
    stable = _stable_installs(ws)
    if not stable:
        raise NotFound("No osu!stable install found to add the collection to.", "no_stable_install")
    if locate.is_osu_running():
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
    for i, sid in enumerate(sets, 1):
        report(i - 1, len(sets), f"Downloading {i}/{len(sets)} (set {sid})")
        if sources.download_osz(sid, dest):
            ok += 1
        else:
            failed.append(sid)
    return OszResult(folder=str(dest), downloaded=ok, failed=failed)
