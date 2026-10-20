"""Whether the built web app (frontend/dist) is up to date with its sources, for run.bat.

    python packaging/web_build_check.py check   exit 0: up to date; 1: build it; 2: install packages, then build
    python packaging/web_build_check.py stamp   after a build: remember what it was built from

The sources are fingerprinted by content (not by file times), so switching to a branch with other web code
rebuilds it, and switching back to code that was built before doesn't. Packages (npm ci) are installed again only
when package-lock.json changed or node_modules is missing.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "frontend"
STAMP = WEB / "dist" / ".built-from.json"
SOURCES = ("index.html", "package.json", "package-lock.json", "vite.config.ts", "src", "public")


def _files() -> list[Path]:
    out = []
    for name in SOURCES:
        p = WEB / name
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out += [f for f in p.rglob("*") if f.is_file() and ".test." not in f.name]
    out += sorted(WEB.glob("tsconfig*.json"))
    return sorted(out)


def _digest(files: list[Path]) -> str:
    h = hashlib.sha256()
    for f in files:
        h.update(f.relative_to(WEB).as_posix().encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))  # the same code checked out with CRLF or LF
    return h.hexdigest()


def current() -> dict[str, str]:
    return {"sources": _digest(_files()), "lock": _digest([WEB / "package-lock.json"])}


def check() -> int:
    if not (WEB / "node_modules").is_dir():
        return 2
    try:
        built = json.loads(STAMP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        built = {}
    now = current()
    if not (WEB / "dist" / "index.html").is_file() or built.get("sources") != now["sources"]:
        return 2 if built.get("lock") not in (None, now["lock"]) else 1
    return 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "check"
    if command == "stamp":
        STAMP.write_text(json.dumps(current()), encoding="utf-8")
        return 0
    if command == "check":
        return check()
    print(__doc__, file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
