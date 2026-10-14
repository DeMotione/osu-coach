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
from collections import Counter
from pathlib import Path

from osu_coach.analysis.domain import ANALYSIS_VERSION, ReplayAnalysis, UnsupportedReplay, analyze
from osu_coach.beatmaps import sources
from osu_coach.beatmaps.parser import parse_beatmap_bytes
from osu_coach.config import default_cache_dir
from osu_coach.replays import eligibility, locate
from osu_coach.replays.eligibility import analysable
from osu_coach.replays.osr import parse_replay


def analyze_bytes(replay, osu_bytes: bytes, raw_replay: bytes | None = None) -> ReplayAnalysis:
    return analyze(replay, parse_beatmap_bytes(osu_bytes), osu_bytes, raw_replay)


def analyze_files(replay_path, beatmap_path) -> ReplayAnalysis:
    raw = Path(replay_path).read_bytes()
    replay = parse_replay(raw, source_path=str(replay_path))
    return analyze_bytes(replay, Path(beatmap_path).read_bytes(), raw)


def _work(replay_path: str, osu_path: str) -> ReplayAnalysis:
    raw = Path(replay_path).read_bytes()
    replay = parse_replay(raw, source_path=replay_path)
    return analyze_bytes(replay, Path(osu_path).read_bytes(), raw)


def _error_text(exc: Exception) -> str:
    return str(exc) if isinstance(exc, UnsupportedReplay) else f"analysis failed: {exc}"


class Library:
    def __init__(self, cache_dir=None):
        self.cache = Path(cache_dir or default_cache_dir())
        self.cache.mkdir(parents=True, exist_ok=True)
        self.replays: list[dict] = []
        self.maps: dict[str, str] = {}
        self.installed: dict[str, set[str]] = {"stable": set(), "lazer": set()}  # beatmap md5s in the game
        self.sources: list[str] = []
        self._limits: list[int | None] = []                 # `latest` of every scanned source
        self._unread_maps: list[tuple[str, object]] = []    # (kind, LazerStore/SongsFolder) not fully read
        self._index_path = self.cache / "index.json"
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

    def add_install(self, inst: locate.Install, progress=None, index_songs: bool = True,
                    latest: int | None = None, player: str | None = None):
        """Replays and beatmaps of an osu! install.  ``latest``: read only the newest ``latest``
        replays of ``player`` (default: whoever has the most, normally you), newest files first,
        and leave the beatmaps to :meth:`find_maps` instead of reading the whole install."""
        latest = latest or None
        self.sources.append(inst.label)
        self._limits.append(latest)
        if inst.kind == "lazer" and inst.files_dir:
            store = locate.LazerStore(inst.files_dir, self.index)
            r, m = store.scan(progress, latest, player, analysable)
            self._add(r, m, "lazer")
            self.installed["lazer"].update(m)
            if not store.exhausted:
                self._unread_maps.append(("lazer", store))
        for d in inst.replay_dirs:
            r, m = locate.scan_folder(d, self.index, latest, player, analysable)
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

    def add_folder(self, folder, source: str = "folder", latest: int | None = None, player: str | None = None,
                   maps_only: bool = False):
        """Replays and beatmaps in a folder (``maps_only``: just the beatmaps)."""
        self.sources.append(str(folder))
        self._limits.append(latest or None)
        r, m = locate.scan_folder(Path(folder), self.index, latest or None, player, analysable)
        self._add([] if maps_only else r, m, source)
        self.save_index()

    def add_map_source(self, inst: locate.Install):
        """An install's beatmaps, looked up by MD5 only when needed (:meth:`find_maps`), without its replays:
        for analysing only a few replay files."""
        if inst.kind == "lazer" and inst.files_dir:
            store = locate.LazerStore(inst.files_dir, self.index)
            store.unread = sorted(locate.list_files(store.files_dir, lambda n: len(n) == 64), key=lambda f: f[1],
                                  reverse=True)
            self._unread_maps.append(("lazer", store))
        elif inst.kind == "stable" and inst.songs:
            self._unread_maps.append(("stable", locate.SongsFolder(inst.songs, self.index)))

    def add_files(self, paths, source: str = "upload"):
        reps, maps = [], {}
        for p in map(Path, paths):
            if p.suffix.lower() == ".osr":
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

    def load_cached(self, keys) -> list[ReplayAnalysis]:
        """Analyses of earlier runs, by replay key (those not in the cache are skipped)."""
        out = []
        for key in keys:
            try:
                with open(self._cache_path(key), "rb") as fh:
                    out.append(pickle.load(fh))
            except Exception:  # noqa: BLE001 - missing / stale entry
                continue
        return out

    def analyze(self, refs: list[dict], workers: int | None = None, progress=None
                ) -> tuple[list[ReplayAnalysis], list[tuple[dict, str]]]:
        """Analyse replays (cached by replay content). Returns (analyses, errors)."""
        (self.cache / "analyses").mkdir(parents=True, exist_ok=True)
        done: list[ReplayAnalysis] = []
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
                        done.append(pickle.load(fh))
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

        def finish(item, result):
            ref, key, _ = item
            result.key = key
            result.meta["key"] = key
            result.objects["replay_key"] = key
            result.presses["replay_key"] = key
            result.meta["source"] = ref.get("source")
            with open(self._cache_path(key), "wb") as fh:
                pickle.dump(result, fh, protocol=pickle.HIGHEST_PROTOCOL)
            done.append(result)

        workers = workers if workers is not None else max(1, min(8, (os.cpu_count() or 2) - 1))
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
