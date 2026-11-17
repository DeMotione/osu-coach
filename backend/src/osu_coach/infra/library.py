"""Replay library: discovery -> beatmap lookup (local first, then online) ->
cached, parallel analysis.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import multiprocessing
import os
import pickle
import threading
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

import pandas as pd

from osu_coach.config import default_cache_dir
from osu_coach.domain.analysis.estimate import Plan
from osu_coach.domain.analysis.models import ANALYSIS_VERSION, Play, ReplayMeta, UnsupportedReplay
from osu_coach.domain.analysis.notes import HitObjects, KeyPresses
from osu_coach.domain.player import PlaySummary
from osu_coach.domain.player import summarize as summarize_play
from osu_coach.domain.replays import eligibility
from osu_coach.domain.replays.eligibility import analysable
from osu_coach.infra import summaries
from osu_coach.infra.analysis import analyze
from osu_coach.infra.beatmaps import sources
from osu_coach.infra.beatmaps.parser import parse_beatmap_bytes
from osu_coach.infra.replays import detect, locate
from osu_coach.infra.replays.osr import parse_replay


def analyze_bytes(replay, osu_bytes: bytes, raw_replay: bytes | None = None) -> Play:
    return analyze(replay, parse_beatmap_bytes(osu_bytes), osu_bytes, raw_replay)


def analyze_files(replay_path, beatmap_path) -> Play:
    raw = Path(replay_path).read_bytes()
    replay = parse_replay(raw, source_path=str(replay_path))
    return analyze_bytes(replay, Path(beatmap_path).read_bytes(), raw)


def _work(replay_path: str, osu_path: str) -> Play:
    raw = Path(replay_path).read_bytes()
    replay = parse_replay(raw, source_path=replay_path)
    return analyze_bytes(replay, Path(osu_path).read_bytes(), raw)


@dataclass
class CachedAnalysis:
    """How an analysis is stored in the cache: the meta dict and the notes / key presses as data frames (the format
    of every osu! coach version so far)."""

    key: str
    meta: dict
    objects: pd.DataFrame = field(repr=False)
    presses: pd.DataFrame = field(repr=False)


# The class cache files name: written by earlier versions (before the code moved) or by this one
CACHED_CLASSES = {
    ("osu_coach.analysis.domain", "ReplayAnalysis"),
    ("osu_coach.domain.analysis.models", "ReplayAnalysis"),
    (__name__, "CachedAnalysis"),
}


class _Unpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if (module, name) in CACHED_CLASSES:
            return CachedAnalysis
        return super().find_class(module, name)


def to_play(cached: CachedAnalysis) -> Play:
    meta = ReplayMeta.from_dict({**cached.meta, "key": cached.key})
    return Play(meta, HitObjects.from_columns(cached.objects), KeyPresses.from_columns(cached.presses))


def to_cached(play: Play) -> CachedAnalysis:
    objects = pd.DataFrame(play.notes.to_columns()).assign(replay_key=play.key)
    presses = pd.DataFrame(play.presses.to_columns()).assign(replay_key=play.key)
    return CachedAnalysis(play.key, play.meta.to_dict(), objects, presses)


def read_cached(fh) -> Play:
    """One analysis from its cache file (also one written before the analysis classes moved)."""
    return to_play(_Unpickler(fh).load())


def _error_text(exc: Exception) -> str:
    return str(exc) if isinstance(exc, UnsupportedReplay) else f"analysis failed: {exc}"


def load_cached_analyses(cache: Path, keys) -> list[Play]:
    """Analyses saved by earlier runs, by replay key (those not in the cache are skipped)."""
    out = []
    for key in keys:
        try:
            with open(cache / "analyses" / f"{key}-v{ANALYSIS_VERSION}.pkl", "rb") as fh:
                out.append(read_cached(fh))
        except Exception:  # noqa: BLE001 - missing / stale entry
            continue
    return out


class Library:
    def __init__(self, cache_dir=None):
        self.cache = Path(cache_dir or default_cache_dir())
        self.cache.mkdir(parents=True, exist_ok=True)
        self.replays: list[dict] = []
        self.maps: dict[str, str] = {}
        self.installed: dict[str, set[str]] = {"stable": set(), "lazer": set()}  # beatmap md5s in the game
        self.sources: list[str] = []
        self._limits: list[int | None] = []  # `latest` of every scanned source
        self._unread_maps: list[tuple[str, object]] = []  # (kind, LazerStore/SongsFolder) not fully read
        self._index_path = self.cache / "index.json"
        self._index_lock = threading.RLock()  # the keys of an estimate (a request) and of an analysis (a job)
        try:
            self.index = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.index = {}
        if not isinstance(self.index, dict):
            self.index = {}
        locate.upgrade_index(self.index)
        for p in (self.cache / "maps").glob("*.osu"):
            self.maps.setdefault(p.stem, str(p))

    @property
    def scan_limit(self) -> int | None:
        """How many of the newest replays (per player) every scanned source is certain to
        include; None if all replays were read."""
        limits = [n for n in self._limits if n]
        return min(limits) if limits else None

    # -------------------------------------------------------------- discovery
    def save_index(self):
        with self._index_lock:
            tmp = self._index_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.index), encoding="utf-8")
            os.replace(tmp, self._index_path)

    def _add(self, replays: list[dict], maps: dict[str, str], source: str):
        known = {r["path"] for r in self.replays}
        for h in replays:
            if h["path"] not in known:
                h = dict(h, source=source)
                self.replays.append(h)
                known.add(h["path"])
        for md5, path in maps.items():
            self.maps.setdefault(md5, path)

    def add_install(
        self,
        inst: detect.Install,
        progress=None,
        index_songs: bool = True,
        latest: int | None = None,
        player: str | None = None,
        oldest: float | None = None,
    ):
        """Replays and beatmaps of an osu! install.  ``latest``: read only the newest ``latest``
        replays of ``player`` (default: whoever has the most, normally you), newest files first, none older than
        ``oldest`` (a Unix time), and leave the beatmaps to :meth:`find_maps` instead of reading the whole
        install."""
        latest = latest or None
        self.sources.append(inst.label)
        self._limits.append(latest)
        if inst.kind == "lazer" and inst.files_dir:
            store = locate.LazerStore(inst.files_dir, self.index)
            r, m = store.scan(progress, latest, player, analysable, oldest)
            self._add(r, m, "lazer")
            self.installed["lazer"].update(m)
            if not store.exhausted:
                self._unread_maps.append(("lazer", store))
        for d in inst.replay_dirs:
            r, m = locate.scan_folder(d, self.index, latest, player, analysable, oldest)
            self._add(r, m, inst.kind)
        if inst.kind == "stable" and inst.songs and index_songs:
            songs = locate.SongsFolder(inst.songs, self.index)
            if latest:
                self._unread_maps.append(("stable", songs))
            else:
                m = songs.scan(progress)
                self._add([], m, "stable")
                self.installed["stable"].update(m)
        self.save_index()

    def add_folder(
        self,
        folder,
        source: str = "folder",
        latest: int | None = None,
        player: str | None = None,
        maps_only: bool = False,
        oldest: float | None = None,
    ):
        """Replays and beatmaps in a folder (``maps_only``: just the beatmaps; ``oldest``: see :meth:`add_install`)."""
        self.sources.append(str(folder))
        self._limits.append(latest or None)
        r, m = locate.scan_folder(Path(folder), self.index, latest or None, player, analysable, oldest)
        self._add([] if maps_only else r, m, source)
        self.save_index()

    def add_map_source(self, inst: detect.Install):
        """An install's beatmaps, looked up by MD5 only when needed (:meth:`find_maps`), without its replays:
        for analysing only a few replay files."""
        if inst.kind == "lazer" and inst.files_dir:
            store = locate.LazerStore(inst.files_dir, self.index)
            store.unread = sorted(
                locate.list_files(store.files_dir, lambda n: len(n) == 64), key=lambda f: f[1], reverse=True
            )
            self._unread_maps.append(("lazer", store))
        elif inst.kind == "stable" and inst.songs:
            self._unread_maps.append(("stable", locate.SongsFolder(inst.songs, self.index)))

    def add_files(self, paths, source: str = "upload"):
        """Replays (.osr, or a file of lazer's store: no extension) and beatmaps (.osu) given one by one."""
        reps, maps = [], {}
        for p in map(Path, paths):
            if p.suffix.lower() == ".osr" or not p.suffix:
                h = locate.replay_header(p)
                if h:
                    reps.append(h)
            elif p.suffix.lower() == ".osu":
                maps[locate.file_md5(p)] = str(p)
        self._add(reps, maps, source)

    # -------------------------------------------------------------- selection
    def standard_replays(self) -> list[dict]:
        """Replays that can be analysed (see :func:`analysable`)."""
        return eligibility.standard_replays(self.replays)

    def left_out(self, player: str | None = None, since: str | None = None) -> Counter:
        """Reasons for osu!standard replays of ``player`` that can't be analysed (lazer mods the
        simulation can't follow), counted.  ``since``: only replays played at or after this
        timestamp (ISO, as in the headers)."""
        return eligibility.left_out(self.replays, player, since)

    def players(self) -> list[tuple[str, int]]:
        return eligibility.player_counts(self.replays)

    def eligible(self, player: str | None = None, limit: int | None = None) -> list[dict]:
        return eligibility.eligible(self.replays, player, limit)

    # -------------------------------------------------------------- beatmaps
    def has_unread_maps(self, kind: str | None = None) -> bool:
        """A limited scan left parts of an install ("lazer" / "stable", default any) unread."""
        return any(not src.exhausted for k, src in self._unread_maps if kind is None or k == kind)

    def find_maps(self, md5s=None, progress=None) -> int:
        """Look for beatmaps in the parts of the osu! installs a limited scan didn't read, newest
        files first, stopping as soon as all are found.  ``md5s``: default = the beatmaps of all
        found replays.  Returns how many of them were found."""
        if md5s is None:
            md5s = {r["beatmap_md5"] for r in self.standard_replays()}
        want = {m for m in md5s if m not in self.maps}
        found = 0
        for kind, src in self._unread_maps:
            if not want:
                break
            if src.exhausted:
                continue
            m = src.find(want, progress)
            for md5, path in m.items():
                self.maps.setdefault(md5, path)
            self.installed[kind].update(m)
            found += len(want & m.keys())
            want -= m.keys()
        self._unread_maps = [(k, s) for k, s in self._unread_maps if not s.exhausted]
        self.save_index()
        return found

    def missing_maps(self, refs: list[dict], progress=None) -> list[str]:
        """Beatmaps of these replays that aren't on this computer (after looking for them in the
        parts of the installs a limited scan didn't read)."""
        need = {r["beatmap_md5"] for r in refs}
        if self._unread_maps and need - self.maps.keys():
            self.find_maps(need, progress)
        return sorted(m for m in need if m not in self.maps)

    def fetch_missing(self, md5s: list[str], progress=None) -> int:
        """Download missing .osu files by MD5 (osu.direct lookup + official file, MD5-verified)."""
        out_dir = self.cache / "maps"
        out_dir.mkdir(parents=True, exist_ok=True)
        got = 0
        for i, md5 in enumerate(md5s):
            if progress:
                progress(i, len(md5s), f"downloading beatmap {i + 1}/{len(md5s)}")
            res = sources.fetch_beatmap_by_md5(md5)
            if res is None:
                continue
            path = out_dir / f"{md5}.osu"
            path.write_bytes(res[0])
            self.maps[md5] = str(path)
            got += 1
        return got

    # -------------------------------------------------------------- analysis
    def _cache_path(self, key: str) -> Path:
        return self.cache / "analyses" / f"{key}-v{ANALYSIS_VERSION}.pkl"

    def load_cached(self, keys) -> list[Play]:
        """Analyses of earlier runs, by replay key (those not in the cache are skipped)."""
        return load_cached_analyses(self.cache, keys)

    def analyze(
        self, refs: list[dict], workers: int | None = None, progress=None
    ) -> tuple[list[Play], list[tuple[dict, str]]]:
        """Analyse replays (cached by replay content). Returns (analyses, errors)."""
        (self.cache / "analyses").mkdir(parents=True, exist_ok=True)
        done: list[Play] = []
        errors: list[tuple[dict, str]] = []
        todo: list[tuple[dict, str, str]] = []
        for ref in refs:
            try:
                key = hashlib.md5(Path(ref["path"]).read_bytes()).hexdigest()
            except OSError as exc:
                errors.append((ref, f"cannot read replay: {exc}"))
                continue
            cp = self._cache_path(key)
            if cp.exists():
                try:
                    with open(cp, "rb") as fh:
                        done.append(read_cached(fh))
                    continue
                except Exception:  # noqa: BLE001 - stale/corrupt cache entry: recompute
                    cp.unlink(missing_ok=True)
            osu = self.maps.get(ref["beatmap_md5"])
            if not osu:
                errors.append((ref, "beatmap not found (not installed and not downloaded)"))
                continue
            todo.append((ref, key, osu))
        total = len(done) + len(todo)
        if progress:
            progress(len(done), total, f"{len(done)} replays loaded from cache")

        def finish(item, result: Play):
            ref, key, _ = item
            result = Play(replace(result.meta, key=key, source=ref.get("source") or ""), result.notes, result.presses)
            with open(self._cache_path(key), "wb") as fh:
                pickle.dump(to_cached(result), fh, protocol=pickle.HIGHEST_PROTOCOL)
            done.append(result)

        workers = workers if workers is not None else default_workers()
        if workers > 1 and len(todo) >= 4:
            try:
                ctx = multiprocessing.get_context("spawn")
                with cf.ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
                    futs = {ex.submit(_work, item[0]["path"], item[2]): item for item in todo}
                    for fut in cf.as_completed(futs):
                        item = futs[fut]
                        try:
                            finish(item, fut.result())
                        except Exception as exc:  # noqa: BLE001
                            errors.append((item[0], _error_text(exc)))
                        if progress:
                            progress(len(done) + len(errors), total, item[0].get("path", ""))
                return done, errors
            except (OSError, cf.process.BrokenProcessPool, RuntimeError):
                todo = [it for it in todo if it[1] not in {a.key for a in done}]
        for item in todo:
            try:
                finish(item, _work(item[0]["path"], item[2]))
            except Exception as exc:  # noqa: BLE001
                errors.append((item[0], _error_text(exc)))
            if progress:
                progress(len(done) + len(errors), total, item[0].get("path", ""))
        return done, errors

    def replay_keys(self, refs: list[dict]) -> dict[str, str]:
        """{path: key} of these replays (the MD5 of the file), cached in the index by size and time like the
        beatmaps', so an estimate or a repeated analysis doesn't read every replay file again. Unreadable ones are
        left out."""
        out: dict[str, str] = {}
        with self._index_lock:
            cache = self.index.setdefault("files", {})
            changed = False
            for ref in refs:
                path = str(ref["path"])
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                hit = cache.get(path)
                key = locate._md5_of(path, st.st_size, st.st_mtime_ns, cache)
                changed |= cache.get(path) is not hit  # read again: a new entry to keep
                if key:
                    out[path] = key
            if changed:
                try:
                    self.save_index()
                except OSError:  # the keys are only kept to save time
                    pass
        return out

    def plan(self, refs: list[dict]) -> Plan:
        """What analysing these replays will take (see ``domain.analysis.estimate``): those analysed and summarised
        already, those whose cached analysis is summarised again, and the size of each one still to analyse."""
        keys = self.replay_keys(refs)
        stored = summaries.stored_keys(self.cache, keys.values())
        new: list[tuple[float, bool]] = []
        from_cache = done = 0
        seen: set[str] = set()
        for ref in refs:
            key = keys.get(str(ref["path"]))
            if key is None or key in seen:
                continue
            seen.add(key)
            cached = self._cache_path(key).exists()
            if cached and key in stored:
                done += 1
            elif cached:
                from_cache += 1
            else:
                try:
                    size = os.stat(ref["path"]).st_size
                except OSError:
                    continue
                new.append((size / 1e6, bool(ref.get("is_lazer"))))
        return Plan(tuple(new), from_cache, done)

    def summarize_replays(
        self, refs: list[dict], workers: int | None = None, progress=None
    ) -> tuple[list[PlaySummary], list[tuple[dict, str]]]:
        """The summaries of these replays (in their order), for the analysis job: a stored summary as it is, else
        made from the cached analysis, else from analysing the replay. The making is spread over ``workers``
        processes, and each returns the summary only, not the whole analysis: the job never holds every play's notes,
        and summarising is no longer done one play after the other once the analyses are made (#95)."""
        errors: list[tuple[dict, str]] = []
        keys = self.replay_keys(refs)
        keyed: list[tuple[dict, str]] = []
        for ref in refs:
            key = keys.get(str(ref["path"]))
            if key is None:
                errors.append((ref, "cannot read replay"))
            else:
                keyed.append((ref, key))
        have = summaries.load(self.cache, [key for _, key in keyed])
        jobs: list[tuple[dict, str, tuple]] = []
        for ref, key in keyed:
            cp = self._cache_path(key)
            if key in have and cp.exists():
                continue
            osu = self.maps.get(ref["beatmap_md5"])
            if cp.exists() or osu:
                jobs.append((ref, key, (str(cp), ref["path"], osu, key, ref.get("source") or "")))
            else:
                errors.append((ref, "beatmap not found (not installed and not downloaded)"))
        made, failed = _summaries_in_workers(self.cache, jobs, _summary_job, workers, progress, len(keyed) - len(jobs))
        have.update(made)
        errors += failed
        return [have[key] for _, key in keyed if key in have], errors


# ------------------------------------------------------------------ summaries made in worker processes
SAVE_EVERY = 50  # summaries stored at a time while they are made, so an interrupted run keeps them


def _write_cached(path: Path, play: Play) -> None:
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    with open(temp, "wb") as fh:
        pickle.dump(to_cached(play), fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(temp, path)


def _summary_job(cache_file: str, replay_path: str, osu_path: str | None, key: str, source: str) -> PlaySummary:
    """One replay's summary, in a worker: from its cached analysis, else by analysing it (and caching that)."""
    path = Path(cache_file)
    if path.exists():
        try:
            with open(path, "rb") as fh:
                return summarize_play(read_cached(fh))
        except Exception:  # noqa: BLE001 - stale/corrupt cache entry: analysed again
            path.unlink(missing_ok=True)
    if not osu_path:
        raise UnsupportedReplay("beatmap not found (not installed and not downloaded)")
    play = _work(replay_path, osu_path)
    play = Play(replace(play.meta, key=key, source=source), play.notes, play.presses)
    _write_cached(path, play)
    return summarize_play(play)


def _cached_summary_job(cache_file: str, key: str) -> PlaySummary | None:
    try:
        with open(cache_file, "rb") as fh:
            return summarize_play(read_cached(fh))
    except Exception:  # noqa: BLE001 - not in the cache any more
        return None


def default_workers() -> int:
    """Every core, at most 8: the app waits for the analysis anyway, and the workers run at a lower priority so it
    still answers (one core left idle made a first analysis ~13% slower on 4 cores)."""
    return max(1, min(8, os.cpu_count() or 2))


def _lower_priority() -> None:
    try:
        os.nice(5)  # POSIX; on Windows the workers keep the normal priority
    except (AttributeError, OSError):
        pass


def _summaries_in_workers(cache: Path, jobs: list[tuple], fn, workers, progress, done_before: int = 0):
    """Run ``fn(*args)`` for each (ref, key, args) of ``jobs`` (one per key) in worker processes, or in this one when
    there are few: {key: summary} of those that gave one, stored as they come, and [(ref, error)] of those that
    failed."""
    (cache / "analyses").mkdir(parents=True, exist_ok=True)
    jobs = list({key: (ref, key, args) for ref, key, args in jobs}.values())
    made: dict[str, PlaySummary] = {}
    errors: list[tuple[dict, str]] = []
    handled: set[str] = set()
    pending: list[PlaySummary] = []
    total = done_before + len(jobs)
    if progress:
        progress(done_before, total, f"{done_before} replays loaded from cache")

    def finish(ref, key, result=None, exc: Exception | None = None):
        handled.add(key)
        if exc is not None:
            errors.append((ref, _error_text(exc)))
        elif result is not None:
            made[key] = result
            pending.append(result)
            if len(pending) >= SAVE_EVERY:
                summaries.save(cache, pending)
                pending.clear()
        if progress:
            progress(done_before + len(handled), total, (ref or {}).get("path", key))

    workers = workers if workers is not None else default_workers()
    if workers > 1 and len(jobs) >= 4:
        try:
            ctx = multiprocessing.get_context("spawn")
            with cf.ProcessPoolExecutor(
                max_workers=min(workers, len(jobs)), mp_context=ctx, initializer=_lower_priority
            ) as ex:
                futs = {ex.submit(fn, *args): (ref, key) for ref, key, args in jobs}
                for fut in cf.as_completed(futs):
                    ref, key = futs[fut]
                    try:
                        result = fut.result()
                    except cf.process.BrokenProcessPool:
                        raise
                    except Exception as exc:  # noqa: BLE001 - this replay can't be analysed
                        finish(ref, key, exc=exc)
                    else:
                        finish(ref, key, result)
        except (OSError, cf.process.BrokenProcessPool, RuntimeError):  # no worker processes: the rest in this one
            pass
    for ref, key, args in jobs:
        if key in handled:
            continue
        try:
            result = fn(*args)
        except Exception as exc:  # noqa: BLE001 - this replay can't be analysed
            finish(ref, key, exc=exc)
        else:
            finish(ref, key, result)
    summaries.save(cache, pending)
    return made, errors


def cached_summaries(
    cache: Path | str, keys: list[str], workers: int | None = None, progress=None
) -> list[PlaySummary]:
    """The summaries of these plays: stored ones, the others made from their cached analyses in worker processes
    (after an update of the app every summary is made again) and stored. Plays found in neither are left out."""
    cache = Path(cache)
    keys = list(keys)
    have = summaries.load(cache, keys)
    jobs = [
        (None, key, (str(cache / "analyses" / f"{key}-v{ANALYSIS_VERSION}.pkl"), key))
        for key in dict.fromkeys(keys)
        if key not in have
    ]
    made, _ = _summaries_in_workers(cache, jobs, _cached_summary_job, workers, progress, len(keys) - len(jobs))
    have.update(made)
    return [have[k] for k in keys if k in have]


@dataclass
class ScanArgs:
    """What the last scan read, so it can be repeated (new files added, the next start)."""

    installs: list[detect.Install] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    only: bool = False  # only these files, not the library
    map_installs: list[detect.Install] = field(default_factory=list)  # beatmaps only, for ``only``
