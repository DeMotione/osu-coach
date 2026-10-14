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
from collections import Counter

import numpy as np
import pandas as pd

from osu_coach.analysis.domain import ReplayAnalysis

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
        date = date.replace(tzinfo=dt.UTC)
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


def mods_label(mods, rate) -> str:
    """'HDDT ×1.26', 'HR', 'NM ×0.85': the speed is spelled out when it isn't the mod's standard one."""
    mods = mods if isinstance(mods, str) and mods else "NM"
    rate = 1.0 if _nan(rate) else float(rate)
    standard = {1.0, 1.5, 0.75}
    return mods + (f" ×{rate:g}" if not any(abs(rate - s) < 1e-3 for s in standard) else "")


def settings_key(m) -> tuple:
    """What changes how hard a play of the same map is: speed (DT/HT/custom rate), the effective CS / AR / OD /
    HP (HR, EZ, Difficulty Adjust, ...) and Hidden / Flashlight. Only plays with the same key are compared."""
    def r(v, nd=1):
        return None if _nan(v) else round(float(v), nd)
    mods = m.get("mods") if isinstance(m.get("mods"), str) else (m.get("mod_string") or "")
    return (r(m.get("rate") or 1.0, 2), r(m.get("cs")), r(m.get("ar")), r(m.get("od")), r(m.get("hp")),
            "HD" in mods, "FL" in mods)


def same_settings(k1: tuple, k2: tuple) -> bool:
    """Same :func:`settings_key`; a value missing on one side (e.g. HP of plays saved by an older version)
    doesn't make them differ."""
    return all(x is None or y is None or x == y for x, y in zip(k1, k2))


def settings_label(m) -> str:
    """'×1.26 · AR 10.2 · OD 9.6 · CS 4 · HP 6': the play's speed and effective difficulty settings."""
    rate = m.get("rate") or 1.0
    parts = [f"×{float(rate):g}"] if abs(float(rate) - 1) > 1e-3 else []
    for name in ("ar", "od", "cs", "hp"):
        v = m.get(name)
        if not _nan(v):
            parts.append(f"{name.upper()} {float(v):.1f}".replace(".0", ""))
    return " · ".join(parts)


PLAY_COLUMNS = ["key", "date", "mods", "rate", "cs", "ar", "od", "hp", "bpm", "stars", "accuracy", "nmiss",
                "max_combo", "map_max_combo", "ur", "completed", "head_misses", "path", "this", "same_settings"]


def map_plays(saved: pd.DataFrame | None, a: ReplayAnalysis, others=()) -> pd.DataFrame:
    """Every play of this map by this player: the saved history ``saved`` (rows of the replays table) plus ``others`` (analyses of
    the replay files of this map on the computer) and this play itself (``this``). ``same_settings`` = same speed,
    CS / AR / OD / HP and HD / FL as this play (:func:`settings_key`). Newest first."""
    m = a.meta
    rows = {}
    if saved is not None:
        for r in saved.to_dict("records"):
            rows[r["key"]] = {**r, "date": r.get("played_at")}
    for o in list(others) + [a]:
        om = o.meta
        if (om.get("beatmap_md5") != m.get("beatmap_md5")) or ((om.get("player") or "") != (m.get("player") or "")):
            continue
        rows[o.key] = {**{k: om.get(k) for k in ("rate", "cs", "ar", "od", "hp", "bpm", "stars", "accuracy", "nmiss",
                                                  "max_combo", "map_max_combo", "ur", "completed", "head_misses")},
                       "key": o.key, "date": om.get("date"), "mods": om.get("mod_string") or "",
                       "path": str(om.get("source_path") or "")}
    if not rows:
        return pd.DataFrame(columns=PLAY_COLUMNS)
    out = pd.DataFrame(list(rows.values()))
    for c in PLAY_COLUMNS:
        if c not in out:
            out[c] = None
    mine = settings_key(m)
    out["this"] = out["key"] == a.key
    out["same_settings"] = [same_settings(settings_key(r), mine) or r["key"] == a.key for r in out.to_dict("records")]
    out["date"] = pd.to_datetime(out["date"], utc=True, errors="coerce", format="mixed")
    return out.sort_values("date", ascending=False)[PLAY_COLUMNS].reset_index(drop=True)


def compare(saved: pd.DataFrame | None, a: ReplayAnalysis, others=()) -> dict:
    """This play against the player's other plays of the same map (:func:`map_plays`). Best / not best is
    only judged against plays with the same settings: a DT ×1.5 play (285 BPM) and a ×1.26 play (240 BPM)
    of the same map are different challenges."""
    m = a.meta
    plays = map_plays(saved, a, others)
    rest = plays[~plays["this"]]
    same = rest[rest["same_settings"]]
    out = {"plays": plays, "map_plays": int(len(same)), "map_plays_all": int(len(rest)),
           "other_settings": int(len(rest) - len(same)), "settings": settings_label(m)}
    if len(same):
        sm = same.assign(_m=pd.to_numeric(same["head_misses"], errors="coerce").fillna(
            pd.to_numeric(same["nmiss"], errors="coerce")), _a=pd.to_numeric(same["accuracy"], errors="coerce"))
        best = sm.sort_values(["_m", "_a"], ascending=[True, False]).iloc[0]
        hm, acc = m.get("head_misses") or 0, m.get("accuracy") or 0
        out.update(map_best_misses=int(best["_m"]), map_best_accuracy=float(best["_a"]),
                   map_best=bool(hm < best["_m"] or (hm == best["_m"] and acc > best["_a"])),
                   map_best_date=best["date"])
        urs = pd.to_numeric(same["ur"], errors="coerce").dropna()
        if len(urs):
            out["ur_median"] = float(urs.median())
        out["accuracy_median"] = float(sm["_a"].median())
        out["misses_median"] = float(sm["_m"].median())
    return out


# ------------------------------------------------------------------ practice sections
LEAD_BEATS = 4      # a section starts one measure (4 beats) before the first miss ...
TAIL_BEATS = 2      # ... and ends half a measure after the last one


def practice_sections(a: ReplayAnalysis, ev: pd.DataFrame | None = None, gap_ms: float = 3000,
                      min_events: int = 2) -> list[dict]:
    """Parts of the map to cut out and practise on their own (e.g. a custom difficulty with just that part):
    each cluster of misses / breaks (:func:`sections`) widened by a measure before and half a measure after,
    snapped to the notes of the map. ``start`` / ``end`` = map time (ms) of its first / last note, ``seconds``
    = length in real time (with the play's speed), ``notes`` = how many notes, plus the cluster itself."""
    ev = events(a) if ev is None else ev
    secs = [s for s in sections(ev, gap_ms) if s["count"] >= min_events]
    if not secs:
        return []
    o = a.objects
    times = o["time"].to_numpy(float)
    ends = o["end_time"].fillna(o["time"]).to_numpy(float)
    beat = o["beat_len"] if "beat_len" in o else pd.Series(500.0, index=o.index)
    rate = float(a.meta.get("rate") or 1.0)
    out = []
    for s in secs:
        i0 = int(np.searchsorted(times, s["start"], side="left"))
        i1 = max(int(np.searchsorted(times, s["end"], side="right")) - 1, i0)
        b0 = float(beat.iloc[min(i0, len(beat) - 1)]) if len(beat) else 500.0
        b1 = float(beat.iloc[min(i1, len(beat) - 1)]) if len(beat) else 500.0
        lo = int(np.searchsorted(times, s["start"] - LEAD_BEATS * b0, side="left"))
        hi = int(np.searchsorted(times, s["end"] + TAIL_BEATS * b1, side="right")) - 1
        lo, hi = max(0, min(lo, i0)), min(len(times) - 1, max(hi, i1))
        start, end = float(times[lo]), float(ends[hi])
        out.append({**s, "start": start, "end": end, "first_event": s["start"], "last_event": s["end"],
                    "notes": hi - lo + 1, "seconds": (end - start) / 1000.0 / rate})
    return out
