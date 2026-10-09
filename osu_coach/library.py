"""Replay library: discovery -> beatmap lookup (local first, then online) ->
cached, parallel analysis. Also stores the app settings (player setup).
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import multiprocessing
import os
import pickle
import sys
from collections import Counter
from pathlib import Path

from . import locate, sources
from .analysis import ANALYSIS_VERSION, ReplayAnalysis, analyze
from .osr import MOD_BITS, parse_replay

# relax / autopilot / autoplay / cinema / target practice: not the player's own aim+tapping
EXCLUDE_MODS = MOD_BITS["RX"] | MOD_BITS["AP"] | MOD_BITS["AT"] | (1 << 22) | (1 << 23)


def default_cache_dir() -> Path:
    if os.environ.get("OSU_COACH_CACHE"):
        return Path(os.environ["OSU_COACH_CACHE"])
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "osu-coach"


def _work(replay_path: str, osu_path: str) -> ReplayAnalysis:
    raw = Path(replay_path).read_bytes()
    replay = parse_replay(raw, source_path=replay_path)
    return analyze(replay, Path(osu_path).read_bytes(), raw)


class Library:
    def __init__(self, cache_dir=None):
        self.cache = Path(cache_dir or default_cache_dir())
        self.cache.mkdir(parents=True, exist_ok=True)
        self.replays: list[dict] = []
        self.maps: dict[str, str] = {}
        self.sources: list[str] = []
        self._index_path = self.cache / "index.json"
        try:
            self.index = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.index = {}
        for p in (self.cache / "maps").glob("*.osu"):
            self.maps.setdefault(p.stem, str(p))

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

    def add_install(self, inst: locate.Install, progress=None, index_songs: bool = True):
        self.sources.append(inst.label)
        if inst.kind == "lazer" and inst.files_dir:
            r, m = locate.scan_lazer_store(inst.files_dir, self.index, progress)
            self._add(r, m, "lazer")
        for d in inst.replay_dirs:
            r, m = locate.scan_folder(d, self.index)
            self._add(r, m, inst.kind)
        if inst.kind == "stable" and inst.songs and index_songs:
            self._add([], locate.index_songs(inst.songs, self.index, progress), "stable")
        self.save_index()

    def add_folder(self, folder, source: str = "folder"):
        self.sources.append(str(folder))
        r, m = locate.scan_folder(Path(folder), self.index)
        self._add(r, m, source)
        self.save_index()

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
        return [r for r in self.replays if r.get("mode") == 0 and not (r.get("mods", 0) & EXCLUDE_MODS)]

    def players(self) -> list[tuple[str, int]]:
        return Counter(r.get("player", "") for r in self._dedupe(self.standard_replays())).most_common()

    @staticmethod
    def _dedupe(refs: list[dict]) -> list[dict]:
        seen, out = set(), []
        for r in refs:
            k = (r.get("beatmap_md5"), r.get("timestamp"), r.get("score"), r.get("player"))
            if k not in seen:
                seen.add(k)
                out.append(r)
        return out

    def eligible(self, player: str | None = None, limit: int | None = None) -> list[dict]:
        refs = self.standard_replays()
        if player and player != "*":
            refs = [r for r in refs if r.get("player") == player]
        refs = sorted(self._dedupe(refs), key=lambda r: r.get("timestamp", ""), reverse=True)
        return refs[:limit] if limit else refs

    # -------------------------------------------------------------- beatmaps
    def missing_maps(self, refs: list[dict]) -> list[str]:
        return sorted({r["beatmap_md5"] for r in refs if r["beatmap_md5"] not in self.maps})

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
                            errors.append((item[0], f"analysis failed: {exc}"))
                        if progress:
                            progress(len(done) + len(errors), total, item[0].get("path", ""))
                return done, errors
            except (OSError, cf.process.BrokenProcessPool, RuntimeError):
                todo = [it for it in todo if it[1] not in {a.key for a in done}]
        for item in todo:
            try:
                finish(item, _work(item[0]["path"], item[2]))
            except Exception as exc:  # noqa: BLE001
                errors.append((item[0], f"analysis failed: {exc}"))
            if progress:
                progress(len(done) + len(errors), total, item[0].get("path", ""))
        return done, errors


# ------------------------------------------------------------------ settings
def load_settings(cache_dir=None) -> dict:
    try:
        return json.loads((Path(cache_dir or default_cache_dir()) / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict, cache_dir=None) -> None:
    p = Path(cache_dir or default_cache_dir())
    p.mkdir(parents=True, exist_ok=True)
    (p / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
