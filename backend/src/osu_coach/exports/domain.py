"""Collection policy: how new collections combine with existing ones, and which sets a playlist still needs."""
from __future__ import annotations


def merge_collections(existing: list[tuple[str, list[str]]], new: list[tuple[str, list[str]]]):
    """Same-name collections are replaced in place, others kept, new names appended.
    Returns (merged, replaced names, added names)."""
    new_names = {n for n, _ in new}
    replaced = [n for n, _ in existing if n in new_names]
    pending = dict(new)
    merged = []
    for name, hashes in existing:
        merged.append((name, pending.pop(name) if name in pending else hashes))
    added = list(pending)
    merged.extend(pending.items())
    return merged, replaced, added


def sets_to_download(playlist_rows, have_md5) -> list[int]:
    """Beatmap sets of the playlist with at least one difficulty that isn't installed."""
    have = set(have_md5 or ())
    out = []
    for md5, sid in playlist_rows:
        if str(md5) not in have and int(sid) not in out:
            out.append(int(sid))
    return out
