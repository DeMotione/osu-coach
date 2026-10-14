"""Online helpers: beatmap lookup by MD5, .osu download, search, .osz mirrors.

All network use is optional; every function fails soft (returns None / []).
Endpoints verified 2026-10: osu.direct API (md5 lookup, search, .osu, .osz),
official https://osu.ppy.sh/osu/{id} for raw .osu files, and several public
.osz mirrors with automatic fail-over.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from pathlib import Path

import requests

UA = "osu-coach/0.1 (local replay-analysis app)"
TIMEOUT = 25

_lock = threading.Lock()
_last_call: dict[str, float] = {}
# minimum spacing per host (osu.direct allows 120 req/min with 10/2s bursts)
_MIN_INTERVAL = {"osu.direct": 0.55, "osu.ppy.sh": 0.35}

OSZ_MIRRORS = [
    ("osu.direct", "https://osu.direct/api/d/{id}"),
    ("catboy.best", "https://catboy.best/d/{id}n"),
    ("nerinyan", "https://api.nerinyan.moe/d/{id}?nv=1"),
    ("sayobot", "https://dl.sayobot.cn/beatmaps/download/novideo/{id}"),
    ("nekoha", "https://mirror.nekoha.moe/api/download/{id}"),
    ("beatconnect", "https://beatconnect.io/b/{id}/?novideo=1"),
    ("osudl", "https://osudl.org/s/{id}?video=false"),
]

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers["User-Agent"] = UA
        _session = s
    return _session


def _throttle(host: str):
    gap = _MIN_INTERVAL.get(host, 0.25)
    with _lock:
        now = time.monotonic()
        wait = _last_call.get(host, 0) + gap - now
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.monotonic()


def _get(url: str, host: str, **kw) -> requests.Response | None:
    timeout = kw.pop("timeout", TIMEOUT)
    for attempt in range(3):
        _throttle(host)
        try:
            r = session().get(url, timeout=timeout, **kw)
        except requests.RequestException:
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code == 429:
            retry = float(r.headers.get("Retry-After", "5") or 5)
            time.sleep(min(retry, 30))
            continue
        return r
    return None


def lookup_md5(md5: str) -> dict | None:
    """Beatmap metadata (osu! API v2 shape) for a beatmap checksum."""
    if not re.fullmatch(r"[0-9a-f]{32}", md5 or ""):
        return None
    r = _get(f"https://osu.direct/api/v2/md5/{md5}", "osu.direct")
    if r is None or r.status_code != 200:
        return None
    try:
        d = r.json()
    except ValueError:
        return None
    return d if isinstance(d, dict) and d.get("id") else None


def download_osu(beatmap_id: int, expected_md5: str | None = None) -> bytes | None:
    """Raw .osu file. Verifies MD5 when given (maps can be updated after a play)."""
    for host, url in (
        ("osu.ppy.sh", f"https://osu.ppy.sh/osu/{beatmap_id}"),
        ("osu.direct", f"https://osu.direct/api/osu/{beatmap_id}"),
    ):
        r = _get(url, host)
        if r is None or r.status_code != 200 or not r.content.lstrip().startswith(b"osu file format"):
            continue
        if expected_md5 and hashlib.md5(r.content).hexdigest() != expected_md5:
            return None
        return r.content
    return None


def fetch_beatmap_by_md5(md5: str) -> tuple[bytes, dict] | None:
    meta = lookup_md5(md5)
    if not meta:
        return None
    data = download_osu(int(meta["id"]), expected_md5=md5)
    if data is None:
        return None
    return data, meta


def search_sets(
    query: str = "",
    sort: str = "play_count:desc",
    status: str = "ranked",
    mode: int = 0,
    amount: int = 100,
    offset: int = 0,
) -> list[dict]:
    status_code = {"ranked": 1, "approved": 2, "qualified": 3, "loved": 4}.get(status, status)
    params = {
        "q": query,
        "sort": sort,
        "mode": mode,
        "status": status_code,
        "amount": min(amount, 100),
        "offset": offset,
    }
    r = _get("https://osu.direct/api/v2/search", "osu.direct", params=params)
    if r is None or r.status_code != 200:
        return []
    try:
        d = r.json()
    except ValueError:
        return []
    return d if isinstance(d, list) else []


def download_osz(set_id: int, dest_dir: Path, progress=None) -> Path | None:
    """Download a beatmapset (.osz, no video) trying mirrors in order."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing = list(dest_dir.glob(f"{set_id} *.osz")) + list(dest_dir.glob(f"{set_id}.osz"))
    if existing:
        return existing[0]
    for name, tpl in OSZ_MIRRORS:
        url = tpl.format(id=set_id)
        if progress:
            progress(f"{set_id}: trying {name}")
        r = _get(url, name, timeout=120, allow_redirects=True, stream=True)
        if r is None or r.status_code != 200:
            continue
        ctype = r.headers.get("content-type", "")
        if "json" in ctype or "html" in ctype:
            continue
        fname = _filename_from_headers(r, set_id)
        tmp = dest_dir / (fname + ".part")
        size = 0
        try:
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
                    size += len(chunk)
        except requests.RequestException:
            tmp.unlink(missing_ok=True)
            continue
        if size < 1024 or not _looks_like_zip(tmp):
            tmp.unlink(missing_ok=True)
            continue
        final = dest_dir / fname
        tmp.replace(final)
        return final
    return None


def _filename_from_headers(r: requests.Response, set_id: int) -> str:
    cd = r.headers.get("content-disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
    name = m.group(1) if m else f"{set_id}.osz"
    try:
        from urllib.parse import unquote

        name = unquote(name)
    except Exception:  # noqa: BLE001
        pass
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or f"{set_id}.osz"
    if not name.lower().endswith(".osz"):
        name += ".osz"
    if not name.startswith(str(set_id)):
        name = f"{set_id} {name}"
    return name


def _looks_like_zip(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(2) == b"PK"


def beatmap_url(beatmap_id: int, set_id: int | None = None) -> str:
    if set_id:
        return f"https://osu.ppy.sh/beatmapsets/{set_id}#osu/{beatmap_id}"
    return f"https://osu.ppy.sh/b/{beatmap_id}"
