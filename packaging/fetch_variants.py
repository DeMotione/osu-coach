"""Get the pool's table of mod and rate configurations (osu_coach.features.maps.variant_table), which is not in git.

    python packaging/fetch_variants.py              download it next to the pool unless a current one is there
    python packaging/fetch_variants.py --require    the same, and fail when there is none (release builds)
    python packaging/fetch_variants.py upload FILE  publish a table made by tools/build_variants.py (needs gh)

The table is an asset of the GitHub release "pool-data", named after the pool and the versions of the calculations
it was made with: after the pool, MODEL_VERSION or rosu-pp changed, make it again and upload it. Without the table
a search with mods works from each map's file, which takes hours on the whole pool.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from osu_coach.features.maps import variant_table as vt

REPO = "DeMotione/osu-coach"
RELEASE = "pool-data"


def fetch(require: bool) -> int:
    if vt.load(vt.TABLE_PATH) is not None:
        return 0
    name = vt.asset_name()
    url = f"https://github.com/{REPO}/releases/download/{RELEASE}/{name}"
    temp = vt.TABLE_PATH.with_suffix(".download")
    print(f"Getting the map pool's mod table ({name}, about 60 MB)...", flush=True)
    try:
        with (
            urllib.request.urlopen(url, timeout=60) as response,
            temp.open("wb") as out,
        ):
            shutil.copyfileobj(response, out)
        if vt.load(temp) is None:
            raise ValueError("not a table of this version")
        temp.replace(vt.TABLE_PATH)
        return 0
    except (OSError, ValueError, urllib.error.URLError) as exc:
        temp.unlink(missing_ok=True)
        print(
            f"No mod table for this version ({exc}): searches with mods will read every map's file, which is slow."
        )
        return 1 if require else 0


def upload(path: Path) -> int:
    if vt.load(path) is None:
        print(f"{path} is not a table of this version of the calculations.")
        return 1
    named = path.with_name(vt.asset_name())
    shutil.copyfile(path, named)
    try:
        if (
            subprocess.run(
                ["gh", "release", "view", RELEASE, "-R", REPO],
                capture_output=True,
                check=False,
            ).returncode
            != 0
        ):
            notes = "Data files the app is built with (not a version of the app): the map pool's table of mod and rate configurations."
            subprocess.run(
                [
                    "gh",
                    "release",
                    "create",
                    RELEASE,
                    "-R",
                    REPO,
                    "--title",
                    "Map pool data",
                    "--notes",
                    notes,
                    "--latest=false",
                ],
                check=True,
            )
        subprocess.run(
            ["gh", "release", "upload", RELEASE, str(named), "-R", REPO, "--clobber"],
            check=True,
        )
    finally:
        named.unlink(missing_ok=True)
    print(f"Published {named.name}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "upload":
        sys.exit(upload(Path(sys.argv[2])))
    sys.exit(fetch("--require" in sys.argv))
