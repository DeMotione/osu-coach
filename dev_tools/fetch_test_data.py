"""Dev helper: download public sample replays (osrparse + circlecore test suites)
and fetch the exact beatmaps they were played on (matched by MD5)."""
import hashlib
import json
import pathlib
import sys
import time
import urllib.request

import osrparse

UA = {"User-Agent": "osu-coach-dev/0.1 (replay analysis test data)"}
OUT = pathlib.Path(sys.argv[1])
(OUT / "replays").mkdir(parents=True, exist_ok=True)
(OUT / "maps").mkdir(parents=True, exist_ok=True)


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def tree(repo):
    d = json.loads(get(f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1"))
    return [t["path"] for t in d["tree"] if t["path"].lower().endswith(".osr")]


sources = []
for p in tree("kszlim/osu-replay-parser"):
    if any(k in p for k in ("replay.osr", "replay2.osr", "lazer_standard_format.osr")):
        sources.append(("osrparse", f"https://raw.githubusercontent.com/kszlim/osu-replay-parser/master/{p}", p))
for p in tree("circleguard/circlecore"):
    if p.startswith("tests/resources/legit/") or p.startswith("tests/resources/auto/auto-") or p.endswith("example_replay.osr"):
        if "nmrx" in p or "dtrx" in p:
            continue  # relax replays: not useful for skill analysis tests
        sources.append(("circlecore", f"https://raw.githubusercontent.com/circleguard/circlecore/master/{p}", p))

print(len(sources), "replays to fetch")
index = []
for src, url, path in sources:
    name = f"{src}__{path.split('/')[-2]}__{path.split('/')[-1]}".replace(" ", "_")
    dest = OUT / "replays" / name
    if not dest.exists():
        dest.write_bytes(get(url))
    try:
        r = osrparse.Replay.from_path(dest)
    except Exception as e:  # noqa: BLE001
        print("parse fail", name, e)
        continue
    if r.mode != osrparse.GameMode.STD:
        continue
    md5 = r.beatmap_hash
    mp = OUT / "maps" / f"{md5}.osu"
    status = "have"
    if not mp.exists():
        try:
            meta = json.loads(get(f"https://osu.direct/api/v2/md5/{md5}"))
            bid = meta["id"]
            data = get(f"https://osu.ppy.sh/osu/{bid}")
            got = hashlib.md5(data).hexdigest()
            if got == md5:
                mp.write_bytes(data)
                status = f"ok id={bid}"
            else:
                status = f"md5 mismatch (map updated) id={bid}"
        except Exception as e:  # noqa: BLE001
            status = f"lookup fail: {e}"
        time.sleep(0.6)
    index.append({"replay": name, "md5": md5, "player": r.username, "mods": int(r.mods),
                  "n300": r.count_300, "n100": r.count_100, "n50": r.count_50, "nmiss": r.count_miss,
                  "map_ok": mp.exists(), "status": status})
    print(f"{name[:70]:70s} {r.username[:14]:14s} mods={int(r.mods):6d} 300={r.count_300} 100={r.count_100} 50={r.count_50} miss={r.count_miss} {status}")

(OUT / "index.json").write_text(json.dumps(index, indent=1))
print("maps ok:", sum(i["map_ok"] for i in index), "/", len(index))
