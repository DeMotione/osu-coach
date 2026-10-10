"""One replay, checked on its own: what happened in that single play.

* ``events``: every miss and combo break, with its time in the map in the osu! editor format
  (mm:ss:mmm — paste it into the editor's timeline or chat), why it happened and on what pattern;
* ``sections``: where misses cluster (parts of the map worth practising);
* ``summary``: the result and a few plain sentences on what cost the play;
* ``compare``: the same map before, and your plays at a similar star rating (from progress.sqlite).
"""
from __future__ import annotations

import datetime as dt
import math
import sqlite3
from collections import Counter

import pandas as pd

from .analysis import ReplayAnalysis

REASON_WORDS = {
    "aim": "aim", "early": "too early", "late": "too late", "no_tap": "no tap", "lost": "lost track",
    "notelock": "notelock", "spinner": "spinner", "follow": "left the slider", "released": "released the key",
    "key_swap": "swapped keys",
}
PATTERN_WORDS = {"stream": "streams", "burst": "bursts", "jump": "jumps", "spaced": "spaced streams",
                 "single": "single notes", "slider": "sliders", "spinner": "spinners"}
NO_MAP = "(map not on this computer)"


def pattern_label(pattern, bpm=None) -> str:
    """One event's pattern: 'stream 220 BPM', 'jump', 'slider', ..."""
    if not pattern or (isinstance(pattern, float) and math.isnan(pattern)):
        return ""
    name = {"spaced": "spaced stream", "single": "single note"}.get(pattern, pattern)
    if pattern in ("stream", "burst") and bpm is not None and not (isinstance(bpm, float) and math.isnan(bpm)):
        name += f" {bpm:.0f} BPM"
    return name


def timestamp(ms: float) -> str:
    """Map time as the osu! editor shows it: mm:ss:mmm."""
    ms = max(int(round(ms)), 0)
    return f"{ms // 60000:02d}:{ms // 1000 % 60:02d}:{ms % 1000:03d}"


def map_label(md: dict) -> str:
    """'Artist – Title [Version]' from read_metadata()."""
    if not md.get("Title"):
        return NO_MAP
    return f"{md.get('Artist', '')} – {md['Title']} [{md.get('Version', '')}]"


def local_time(date, tz=None) -> str:
    """A replay date (UTC) on this computer's clock."""
    if isinstance(date, str):
        date = dt.datetime.fromisoformat(date)
    if date.tzinfo is None:
        date = date.replace(tzinfo=dt.timezone.utc)
    return date.astimezone(tz).strftime("%Y-%m-%d %H:%M")


def _nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _aim_detail(r) -> str:
    out = f"{r['miss_dist']:.1f} radii from the centre" if not _nan(r.get("miss_dist")) else "outside the circle"
    al, cr = r.get("along"), r.get("cross")
    if not _nan(al) and not _nan(cr) and not _nan(r.get("dist_norm")) and r["dist_norm"] >= 1:
        out += ", overshot" if al > abs(cr) * 0.5 else (", fell short" if al < -abs(cr) * 0.5 else ", to the side")
    return out


def _detail(r) -> str:
    reason = r["reason"]
    if reason == "aim":
        return _aim_detail(r)
    if reason in ("early", "late"):
        err = r.get("err_real")
        if not _nan(err):
            return f"{abs(err):.0f} ms {'early' if err < 0 else 'late'}"
        return "pressed before the hit window" if reason == "early" else "pressed after the hit window"
    if reason == "no_tap":
        return "cursor on the note, no key pressed"
    if reason == "lost":
        d = r.get("miss_dist")
        return "no key pressed, cursor far away" + (f" ({d:.1f} radii)" if not _nan(d) else "")
    if reason == "notelock":
        return "pressed while the previous note was still open"
    if reason == "spinner":
        return "not spun enough"
    if reason == "follow":
        return "the cursor left the follow circle"
    if reason == "released":
        return "the key was let go mid-slider"
    if reason == "key_swap":
        return "keys swapped mid-slider"
    return ""


def events(a: ReplayAnalysis) -> pd.DataFrame:
    """Misses (judged miss: the results screen's count), slider heads missed while the slider still
    scored, and slider breaks — in map order."""
    o = a.objects
    P = o[o["played"]]
    rows = []
    for _, r in P.iterrows():
        kind = r["kind"]
        what = None
        if r["result"] == 0:
            what, reason = "miss", ("spinner" if kind == "spinner" else (r["miss_reason"] or "lost"))
        elif kind == "slider" and not r["head_hit"]:
            what, reason = "combo break", r["miss_reason"] or "lost"
        if what:
            rows.append({**r.to_dict(), "what": what, "reason": reason})
        if kind == "slider" and r.get("broke") == True:  # noqa: E712 - also numpy bools; None/NaN aren't
            rows.append({**r.to_dict(), "what": "slider break", "reason": r["break_reason"] or "follow"})
    cols = ["time", "timestamp", "what", "reason", "detail", "pattern", "stream_bpm", "idx"]
    if not rows:
        return pd.DataFrame(columns=cols)
    ev = pd.DataFrame(rows)
    ev["pattern"] = ev["pattern"].where(ev["kind"] != "slider", "slider").where(ev["kind"] != "spinner", "spinner")
    ev["detail"] = [_detail(r) for r in ev.to_dict("records")]
    ev["timestamp"] = ev["time"].map(timestamp)
    return ev.sort_values(["time", "idx"], kind="stable")[cols].reset_index(drop=True)


def sections(ev: pd.DataFrame, gap_ms: float = 3000) -> list[dict]:
    """Misses / breaks less than ``gap_ms`` apart, grouped; most events first."""
    if ev is None or ev.empty:
        return []
    ev = ev.sort_values("time")
    groups, cur, last = [], [], None
    for r in ev.to_dict("records"):
        if cur and r["time"] - last > gap_ms:
            groups.append(cur)
            cur = []
        cur.append(r)
        last = r["time"]
    groups.append(cur)
    out = []
    for g in groups:
        df = pd.DataFrame(g)
        pats = df["pattern"].dropna().value_counts()
        bpm = pd.to_numeric(df["stream_bpm"], errors="coerce").dropna()
        out.append({"start": float(df["time"].min()), "end": float(df["time"].max()), "count": len(df),
                    "reasons": dict(Counter(df["reason"])), "pattern": pats.index[0] if len(pats) else None,
                    "bpm": float(bpm.max()) if len(bpm) else None})
    out.sort(key=lambda s: (-s["count"], s["start"]))
    return out


def _counted(c: Counter) -> str:
    return ", ".join(f"{n} {REASON_WORDS.get(k, k)}" for k, n in c.most_common())


def summary(a: ReplayAnalysis, ev: pd.DataFrame | None = None) -> dict:
    """The result of the play plus ``verdict``: a few sentences on what cost it."""
    m = a.meta
    ev = events(a) if ev is None else ev
    o = a.objects
    P = o[o["played"] & (o["kind"] != "spinner")]
    misses = ev[ev["what"] == "miss"]
    breaks = ev[ev["what"] == "slider break"]
    heads = ev[ev["what"] == "combo break"]
    ends = int(((P["kind"] == "slider") & P["head_hit"] & (P["end_hit"] == False)).sum())  # noqa: E712
    out = {
        "player": m.get("player") or "", "date": m.get("date"), "map": m.get("map_name"), "mods": m.get("mod_string") or "",
        "rate": m.get("rate", 1.0), "stars": m.get("stars"), "bpm": m.get("bpm"), "length_s": m.get("length_s"),
        "accuracy": m.get("accuracy"), "combo": m.get("max_combo"), "map_combo": m.get("map_max_combo"),
        "counts": (m.get("n300"), m.get("n100"), m.get("n50"), m.get("nmiss")), "misses": len(misses),
        "slider_breaks": len(breaks), "heads_missed": len(heads), "slider_ends_missed": ends, "ur": m.get("ur"),
        "mean_error": m.get("mean_error"), "completed": bool(m.get("completed")), "client": m.get("client"),
        "sim_exact": m.get("sim_match") is True, "sim_agreement": m.get("sim_agreement"),
    }
    verdict = []
    if misses.empty and breaks.empty and heads.empty:
        verdict.append("No misses and no combo breaks." + (f" {ends} slider end(s) missed (no combo break)."
                                                            if ends else ""))
    else:
        parts = []
        if len(misses):
            reasons = Counter(misses["reason"])
            only = len(reasons) == 1
            parts.append(f"{len(misses)} miss{'es' if len(misses) != 1 else ''}"
                         + (f" — {'both' if len(misses) == 2 else 'all'} {REASON_WORDS.get(next(iter(reasons)))}"
                            if only and len(misses) > 1 else f": {_counted(reasons)}"))
        if len(breaks):
            parts.append(f"{len(breaks)} slider break{'s' if len(breaks) != 1 else ''} "
                         f"({_counted(Counter(breaks['reason']))})")
        if len(heads):
            parts.append(f"{len(heads)} slider head{'s' if len(heads) != 1 else ''} missed")
        verdict.append("; ".join(parts) + ".")
        aim = ev[ev["reason"] == "aim"]
        if len(aim) >= 2:
            pats = Counter(PATTERN_WORDS.get(p, p) for p in aim["pattern"].dropna())
            verdict.append("Aim misses on " + ", ".join(f"{p} ({n})" for p, n in pats.most_common(3)) + ".")
        secs = [s for s in sections(ev) if s["count"] >= 2]
        if secs:
            s = secs[0]
            where = PATTERN_WORDS.get(s["pattern"], s["pattern"] or "")
            bpm = f" at {s['bpm']:.0f} BPM" if s["bpm"] and s["pattern"] in ("stream", "burst") else ""
            verdict.append(f"Most in one place: {timestamp(s['start'])}–{timestamp(s['end'])} ({s['count']} of "
                           f"{len(ev)}{', ' + where + bpm if where else ''}).")
    if not out["completed"]:
        last = P["time"].max() if len(P) else None
        verdict.append("Failed" + (f" at {timestamp(last)}" if last is not None and not _nan(last) else "") + ".")
    if not _nan(out["ur"]):
        me = out["mean_error"]
        verdict.append(f"Timing: UR {out['ur']:.0f}" + (f", on average {abs(me):.1f} ms {'early' if me < 0 else 'late'}"
                                                        if not _nan(me) else "") + ".")
    out["verdict"] = verdict
    return out


def compare(conn: sqlite3.Connection, a: ReplayAnalysis, window: float = 0.5) -> dict:
    """This play against the player's other saved plays: the same map before, and plays within
    ``window`` stars (misses per 100 notes, accuracy, UR)."""
    m = a.meta
    df = pd.read_sql_query("SELECT key, beatmap_md5, stars, accuracy, head_misses, n_played, ur FROM replays "
                           "WHERE player = ? AND key != ?", conn, params=(m.get("player") or "", a.key))
    out = {"map_plays": 0, "similar_n": 0}
    if df.empty:
        return out
    mine = (m.get("head_misses") or 0) / max(m.get("n_played") or 1, 1) * 100
    same = df[df["beatmap_md5"] == m.get("beatmap_md5")]
    if len(same):
        best = same.sort_values(["head_misses", "accuracy"], ascending=[True, False]).iloc[0]
        hm, acc = m.get("head_misses") or 0, m.get("accuracy") or 0
        out.update(map_plays=len(same), map_best_misses=int(best["head_misses"]),
                   map_best_accuracy=float(best["accuracy"]),
                   map_best=bool(hm < best["head_misses"] or (hm == best["head_misses"] and acc > best["accuracy"])))
    stars = m.get("stars")
    if not _nan(stars):
        sim = df[(df["stars"] - stars).abs() <= window]
        if len(sim):
            rate = sim["head_misses"] / sim["n_played"].clip(lower=1) * 100
            out.update(similar_n=len(sim), similar_range=(stars - window, stars + window), misses_per_100=mine,
                       misses_median=float(rate.median()), accuracy_median=float(sim["accuracy"].median()),
                       ur_median=float(sim["ur"].median()) if sim["ur"].notna().any() else math.nan,
                       misses_better_than=float((rate > mine).mean()),
                       accuracy_better_than=float((sim["accuracy"] < (m.get("accuracy") or 0)).mean()))
    return out
