"""Detailed Map Analysis: one play on its own (misses with map times, clusters to practise, timing, other plays
of the map)."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import pandas as pd

from osu_coach.domain import check, insights
from osu_coach.infrastructure.filesystem import locate
from osu_coach.infrastructure.database import progress
from osu_coach.infrastructure.filesystem.beatmap import read_metadata
from osu_coach.domain.replay_selection import EXCLUDE_MODS, analysable, skip_reason
from osu_coach.infrastructure.filesystem.library import Library
from osu_coach.domain.profile import build_profile

from osu_coach.api.convert import flag, integer, iso, num, text
from osu_coach.api.errors import ApiError, Invalid
from osu_coach.api.schemas.check import (
    CheckEvent,
    CheckList,
    CheckReplay,
    CheckReport,
    CheckSummary,
    MapPlay,
    MapPlays,
    PlayTiming,
    PracticeSection,
    SectionReason,
    TimingMark,
)
from osu_coach.api.state.workspace import Workspace
from osu_coach.api.services.pages import clicks

CHECK_LATEST = 100      # replays read when nothing was scanned yet
CHECK_LIST = 300        # replays listed
MAP_PLAYS_MAX = 50      # other replays of the map read for the comparison
SECTIONS_SHOWN = 5
LABEL = "Detailed map analysis"


def _hold(ws: Workspace):
    """The busy gate: waits for another check (requests overlap), refuses at once while a job runs."""
    return ws.gate.hold(LABEL, wait=60 if ws.gate.holder in (None, LABEL) else 0)


def same_file(a, b) -> bool:
    try:
        return Path(a) == Path(b)
    except TypeError:
        return False


@lru_cache(maxsize=5000)
def _map_title(path: str | None, _mtime: float) -> str:
    return check.map_label(read_metadata(path)) if path else check.NO_MAP


def map_title(path: str | None) -> str:
    if not path:
        return check.NO_MAP
    try:
        mtime = Path(path).stat().st_mtime
    except OSError:
        return check.NO_MAP
    return _map_title(path, mtime)


def check_library(ws: Workspace) -> Library | None:
    """The scanned library, else a quick scan of the newest replays on this computer (kept for later)."""
    if ws.library is not None:
        return ws.library
    if ws.check_library is None:
        installs = ws.installs()
        if not installs:
            return None
        lib = Library(ws.cache_dir)
        for inst in installs:
            lib.add_install(inst, latest=CHECK_LATEST)
        ws.check_library = lib
    return ws.check_library


def _reason(ref: dict) -> str | None:
    if analysable(ref):
        return None
    return skip_reason(ref) or ("relax / autopilot / autoplay replays aren't checked" if ref.get("mods", 0) & EXCLUDE_MODS
                                else "only osu!standard is supported")


def _replay(ref: dict, lib: Library) -> CheckReplay:
    mods = "".join(ref.get("lazer_mods") or []) or ref.get("mod_string") or "NM"
    return CheckReplay(path=str(ref["path"]), played_at=iso(ref.get("timestamp")), player=ref.get("player") or "",
                       map=map_title(lib.maps.get(ref.get("beatmap_md5"))), mods=mods, accuracy=num(ref.get("accuracy")),
                       beatmap_md5=ref.get("beatmap_md5"), analysable=analysable(ref), reason=_reason(ref))


def _require_replay_file(path: str) -> Path:
    p = Path(path)
    if p.suffix.lower() != ".osr":
        raise Invalid("Not a replay file (.osr).", "not_a_replay")
    if not p.is_file():
        raise ApiError(404, "replay_not_found", "The replay file is no longer on this computer.")
    return p


def replay_list(ws: Workspace, path: str | None, only_map: bool) -> CheckList:
    """Replays to pick from, newest first; ``path`` (a replay opened elsewhere or uploaded) is always in the list,
    ``only_map``: only (all of) the plays of that replay's map."""
    with _hold(ws):
        lib = check_library(ws)
        if path:
            p = _require_replay_file(path)
            if lib is None:
                lib = ws.check_library = Library(ws.cache_dir)
            if not any(same_file(r["path"], p) for r in lib.replays):
                lib.add_files([p])
        if lib is None:
            return CheckList(available=False, replays=[], selected=None, focus_md5=None, only_map=False)
        every = lib.eligible("*")
        refs = every[:CHECK_LIST]
        if path and not any(same_file(r["path"], path) for r in refs):
            h = next((r for r in lib.replays if same_file(r["path"], path)), None) or locate.replay_header(Path(path))
            if h:
                refs = [h] + refs
        if not refs:
            return CheckList(available=True, replays=[], selected=None, focus_md5=None, only_map=False)
        chosen = next((r for r in refs if path and same_file(r["path"], path)), refs[0])
        focus = chosen.get("beatmap_md5")
        if only_map and focus:
            mine = [r for r in every if r.get("beatmap_md5") == focus]
            refs = [r for r in refs if r.get("beatmap_md5") == focus]
            refs += [r for r in mine if not any(same_file(r["path"], x["path"]) for x in refs)]
            refs.sort(key=lambda r: str(r.get("timestamp") or ""), reverse=True)
        if lib.has_unread_maps():
            lib.missing_maps(refs)          # the map titles of the list
        return CheckList(available=True, replays=[_replay(r, lib) for r in refs], selected=str(chosen["path"]),
                         focus_md5=focus, only_map=bool(only_map and focus))


# ------------------------------------------------------------------ the report
def report(ws: Workspace, path: str, online: bool) -> CheckReport:
    p = _require_replay_file(path)
    with _hold(ws):
        lib = check_library(ws)
        if lib is None:
            lib = ws.check_library = Library(ws.cache_dir)
        ref = next((r for r in lib.replays if same_file(r["path"], p)), None)
        if ref is None:
            lib.add_files([p])
            ref = next((r for r in lib.replays if same_file(r["path"], p)), None)
        if ref is None:
            raise Invalid("Not an osu! replay.", "not_a_replay")
        reason = _reason(ref)
        if reason:
            raise ApiError(422, "not_checkable", f"This replay can't be checked: {reason}.")
        missing = lib.missing_maps([ref])
        if missing and online:
            lib.fetch_missing(missing)
        analyses, errors = lib.analyze([ref], workers=1)
        if not analyses:
            raise ApiError(422, "check_failed", f"Can't check this replay: {errors[0][1] if errors else 'unknown error'}")
        a = analyses[0]
        same = [r for r in lib.replays if r.get("beatmap_md5") == ref.get("beatmap_md5") and analysable(r)
                and (r.get("player") or "") == (ref.get("player") or "") and not same_file(r["path"], ref["path"])]
        others = lib.analyze(same[:MAP_PLAYS_MAX], workers=ws.config.analysis_workers)[0] if same else []
        conn = progress.connect(lib.cache)
        try:
            cmp = check.compare(progress.saved_plays(conn, a), a, others)
            progress.record(conn, [a] + list(others))
        finally:
            conn.close()
    return _report(a, cmp, str(p))


def _report(a, cmp: dict, path: str) -> CheckReport:
    ev = check.events(a)
    s = check.summary(a, ev)
    m = a.meta
    rate = num(s["rate"]) or 1.0
    verdict = list(s["verdict"])
    if not s["completed"] and not any(v.startswith("Failed") for v in verdict):
        verdict.append("Failed play.")
    summary = CheckSummary(
        player=s["player"] or "", played_at=iso(s["date"]), map=text(s["map"]) or check.NO_MAP,
        mods_label=check.mods_label(s["mods"], rate), client=text(s["client"]), creator=text(m.get("creator")),
        beatmap_id=integer(m.get("beatmap_id")) or None, accuracy=num(s["accuracy"]), combo=integer(s["combo"]),
        map_combo=integer(s["map_combo"]), misses=int(s["misses"]), slider_breaks=int(s["slider_breaks"]),
        stars=num(s["stars"]), bpm=num(s["bpm"]), ur=num(s["ur"]), rate=rate, ar=num(m.get("ar")), od=num(m.get("od")),
        cs=num(m.get("cs")), hp=num(m.get("hp")), length_s=num(s.get("length_s")), completed=bool(s["completed"]),
        sim_exact=bool(s["sim_exact"]), sim_agreement=num(s["sim_agreement"]), verdict=verdict)
    events = [CheckEvent(time=float(r["time"]), timestamp=r["timestamp"], what=r["what"], reason=r["reason"],
                         reason_label=check.REASON_WORDS.get(r["reason"], r["reason"]), detail=r["detail"] or "",
                         pattern=check.pattern_label(r["pattern"], r["stream_bpm"]))
              for r in ev.to_dict("records")]
    sections = []
    for x in check.practice_sections(a, ev)[:SECTIONS_SHOWN]:
        reasons = [SectionReason(reason=k, label=check.REASON_WORDS.get(k, k), count=int(n))
                   for k, n in sorted(x["reasons"].items(), key=lambda kv: -kv[1])]
        sections.append(PracticeSection(
            start=check.timestamp(x["start"]), end=check.timestamp(x["end"]), seconds=float(x["seconds"]),
            notes=int(x["notes"]), count=int(x["count"]), reasons=reasons,
            pattern=check.pattern_label(x["pattern"], x["bpm"]) if x["pattern"] else "",
            first_event=check.timestamp(x["first_event"]), last_event=check.timestamp(x["last_event"])))
    t = insights.play_timing(a)
    timing = None
    if t is not None:
        marks = [TimingMark(time=float(r["time"]), what=r["what"],
                            label=f"{r['timestamp']} {r['what']}: {check.REASON_WORDS.get(r['reason'], r['reason'])}")
                 for r in ev.to_dict("records")]
        timing = PlayTiming(time=t["time"], error=t["error"], result=t["result"], trend=[num(v) for v in t["trend"]],
                            window_300=num(t["window_300"]), top=float(t["top"]), length_ms=float(t["length_ms"]),
                            marks=marks)
    prof = _single_profile(a)
    return CheckReport(path=path, summary=summary, events=events, sections=sections, timing=timing,
                       map_plays=_map_plays(cmp), clicks_screen=clicks(prof.objects, "screen") if prof else None,
                       clicks_movement=clicks(prof.objects, "movement") if prof else None)


def _single_profile(a):
    try:
        return build_profile([a])
    except Exception:  # noqa: BLE001 - a very short play may be too little for a profile
        return None


def _map_plays(cmp: dict) -> MapPlays:
    plays: pd.DataFrame = cmp.get("plays")
    rows = []
    if plays is not None:
        for r in plays.to_dict("records"):
            path = r["path"] if isinstance(r.get("path"), str) else ""
            date = r.get("date")
            rows.append(MapPlay(
                this=bool(r["this"]), same_settings=bool(r["same_settings"]),
                played_at=iso(date) if date is not None and not pd.isna(date) else None,
                mods_label=check.mods_label(r.get("mods"), r.get("rate")), settings_label=check.settings_label(r) or "–",
                bpm=num(r.get("bpm")), stars=num(r.get("stars")), accuracy=num(r.get("accuracy")),
                misses=integer(r.get("nmiss")), combo=integer(r.get("max_combo")), ur=num(r.get("ur")),
                passed=flag(r.get("completed")), path=path, path_exists=bool(path) and Path(path).exists()))
    best = cmp.get("map_best")
    return MapPlays(first=plays is None or len(plays) <= 1, settings=cmp.get("settings") or "normal speed",
                    same_settings_plays=int(cmp.get("map_plays", 0)), best_misses=integer(cmp.get("map_best_misses")),
                    best_accuracy=num(cmp.get("map_best_accuracy")), is_best=None if best is None else bool(best),
                    ur_median=num(cmp.get("ur_median", math.nan)), other_settings=int(cmp.get("other_settings", 0)),
                    rows=rows)
