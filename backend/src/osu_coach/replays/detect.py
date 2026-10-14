"""Find osu! on this computer: stable installs (native Windows or Wine) and lazer data folders.

* stable: ``<root>/Data/r`` (replays of your local scores, saved automatically), ``<root>/Replays`` (exported
  with F2), beatmaps in ``Songs`` (or the ``BeatmapDirectory`` from ``osu!.<user>.cfg``), collections in
  ``collection.db``.
* lazer: everything lives in a content-addressed store ``<data>/files/a/ab/<sha256>``. Exported replays land
  in ``<data>/exports``. A custom data location is read from ``storage.ini``.
"""
from __future__ import annotations

import getpass
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Install:
    kind: str                                   # "stable" | "lazer"
    root: Path
    songs: Path | None = None
    replay_dirs: list[Path] = field(default_factory=list)
    files_dir: Path | None = None
    collection_db: Path | None = None

    @property
    def label(self) -> str:
        return f"osu!{self.kind} – {self.root}"


# ------------------------------------------------------------------ candidates
def stable_candidates() -> list[Path]:
    home = Path.home()
    c: list[Path] = []
    if os.name == "nt":
        if os.environ.get("LOCALAPPDATA"):
            c.append(Path(os.environ["LOCALAPPDATA"]) / "osu!")
        for var in ("ProgramFiles", "ProgramFiles(x86)"):
            if os.environ.get(var):
                c.append(Path(os.environ[var]) / "osu!")
        for drive in "CDEFG":
            c += [Path(f"{drive}:/osu!"), Path(f"{drive}:/Games/osu!")]
        return c
    osupath = home / ".local/share/osuconfig/osupath"
    try:
        c.append(Path(osupath.read_text(encoding="utf-8").strip()))
    except OSError:
        pass
    c += [home / ".local/share/osu-wine/OSU", home / ".local/share/osu-wine/osu!"]
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = os.environ.get("USER", "")
    for prefix in (home / ".wine_osu", home / ".wineosu", home / ".wine", home / "osu/prefix",
                   home / ".local/share/osu-wine/WINE.win32", home / ".local/share/wineprefixes/osu-stable",
                   home / ".local/share/osuconfig/WINE.win32"):
        c += [prefix / "drive_c/osu!", prefix / "drive_c/users" / user / "AppData/Local/osu!",
              prefix / "drive_c/users" / user / "Local Settings/Application Data/osu!"]
    if sys.platform == "darwin":
        c.append(home / "Applications/osu!.app/Contents/Resources/drive_c/osu!")
    return c


def lazer_candidates() -> list[Path]:
    home = Path.home()
    if os.name == "nt":
        base = [Path(os.environ["APPDATA"]) / "osu"] if os.environ.get("APPDATA") else []
    elif sys.platform == "darwin":
        base = [home / "Library/Application Support/osu"]
    else:
        data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
        base = [data / "osu", data / "osu-lazer"]
    out = list(base)
    for b in base:  # a moved data folder is recorded in storage.ini (FullPath = ...)
        try:
            for line in (b / "storage.ini").read_text(encoding="utf-8-sig").splitlines():
                k, _, v = line.partition("=")
                if k.strip().lower() == "fullpath" and v.strip():
                    out.insert(0, Path(v.strip()))
        except OSError:
            pass
    return out


# ------------------------------------------------------------------ detection
def stable_install(root: Path) -> Install | None:
    root = Path(root)
    try:
        if not root.is_dir():
            return None
        cfgs = list(root.glob("osu!.*.cfg"))
        if not ((root / "osu!.db").exists() or (root / "Songs").is_dir() or cfgs or (root / "Data" / "r").is_dir()):
            return None
    except OSError:
        return None
    songs = root / "Songs"
    for cfg in cfgs:
        if cfg.name.lower() == "osu!.cfg":
            continue
        try:
            for line in cfg.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                k, _, v = line.partition("=")
                if k.strip() == "BeatmapDirectory" and v.strip():
                    p = Path(v.strip())
                    cand = p if p.is_absolute() else root / p
                    if cand.is_dir():
                        songs = cand
        except OSError:
            continue
    replay_dirs = [d for d in (root / "Data" / "r", root / "Replays") if d.is_dir()]
    coll = root / "collection.db"
    return Install("stable", root, songs if songs.is_dir() else None, replay_dirs, None,
                   coll if coll.exists() or (root / "osu!.db").exists() else None)


def lazer_install(root: Path) -> Install | None:
    root = Path(root)
    try:
        if not (root / "files").is_dir() or not ((root / "client.realm").exists() or (root / "framework.ini").exists()):
            return None
    except OSError:
        return None
    replay_dirs = [d for d in (root / "exports",) if d.is_dir()]
    return Install("lazer", root, None, replay_dirs, root / "files", None)


def find_installs(stable_roots=None, lazer_roots=None) -> list[Install]:
    """osu! installs on this computer.  Set ``OSU_COACH_NO_AUTODETECT=1`` to skip the
    automatic search (only explicitly given roots are checked; used by the tests)."""
    if os.environ.get("OSU_COACH_NO_AUTODETECT", "").strip() not in ("", "0"):
        stable_roots = stable_roots if stable_roots is not None else []
        lazer_roots = lazer_roots if lazer_roots is not None else []
    out, seen = [], set()
    for roots, fn in ((stable_roots if stable_roots is not None else stable_candidates(), stable_install),
                      (lazer_roots if lazer_roots is not None else lazer_candidates(), lazer_install)):
        for r in roots:
            try:
                key = Path(r).resolve()
            except OSError:
                continue
            if key in seen:
                continue
            inst = fn(Path(r))
            if inst:
                seen.add(key)
                out.append(inst)
    return out


def is_osu_running() -> bool:
    """Best effort: osu!stable rewrites collection.db on exit, so merging while it
    runs would be undone."""
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq osu!.exe"], capture_output=True, text=True,
                                 timeout=10).stdout
            return "osu!.exe" in out
        for pid in os.listdir("/proc"):
            if pid.isdigit():
                try:
                    if b"osu!.exe" in Path(f"/proc/{pid}/cmdline").read_bytes():
                        return True
                except OSError:
                    continue
    except Exception:  # noqa: BLE001
        return False
    return False
