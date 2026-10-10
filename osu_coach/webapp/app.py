"""osu! coach — Streamlit UI.  Start with:  osu-coach ui
(or: streamlit run osu_coach/webapp/app.py)
"""
from __future__ import annotations

import datetime as dt
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from osu_coach import lazer_import, locate, progress, sources
from osu_coach.advice import Setup, make_tips, practice_plan, sayo_settings, suggest_tablet_area
from osu_coach.collection_db import dumps as collection_bytes
from osu_coach.collection_db import merge_into
from osu_coach.library import Library, default_cache_dir, load_settings, save_settings
from osu_coach.pool import (SKILLS, Targets, build_playlist, collection_name, load_pool, recommendations,
                            skill_label, targets_from_profile)
from osu_coach.profile import MISS_LABELS, SKILL_LABELS, build_profile, click_points, click_summary

ACCENT, GOOD, BAD, MUTED, INFO = "#ff66aa", "#5fd3a0", "#ff5c7a", "#8b8fa3", "#6fb7ff"
PAGES = ["Replays", "Overview", "Progress", "Aim", "Tapping", "Sliders & reading", "Tips & setup",
         "Map suggestions", "Improve a skill"]
MISS_SHORT = {"aim": "Aim", "early": "Too early", "late": "Too late", "no_tap": "No tap", "lost": "Lost track",
              "notelock": "Notelock"}
DIR_ANGLE = {"right": 0, "up-right": 45, "up": 90, "up-left": 135, "left": 180, "down-left": 225, "down": 270,
             "down-right": 315}
SEVERITY = {3: ("High impact", "red"), 2: ("Medium impact", "orange"), 1: ("Nice to know", "gray")}

st.set_page_config(page_title="osu! coach", page_icon=":material/sports_esports:", layout="wide")


# ------------------------------------------------------------------ helpers
def settings() -> dict:
    if "settings" not in st.session_state:
        st.session_state.settings = load_settings()
    return st.session_state.settings


def profile():
    return st.session_state.get("profile")


@st.cache_resource(show_spinner=False)
def installs_cached():
    return locate.find_installs()


@st.cache_data(show_spinner=False)
def pool_cached() -> pd.DataFrame:
    return load_pool()


def isnan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def fmt(v, spec: str = ".1f", suffix: str = "", none: str = "–") -> str:
    if isnan(v):
        return none
    try:
        return format(v, spec) + suffix
    except (TypeError, ValueError):
        return str(v)


def pct(v, digits: int = 1) -> str:
    return "–" if isnan(v) else f"{v * 100:.{digits}f}%"


def style(fig: go.Figure, height: int = 320, title: str | None = None, legend: bool = False) -> go.Figure:
    fig.update_layout(template="plotly_dark", height=height, title=title, showlegend=legend,
                      margin=dict(l=10, r=10, t=44 if title else 10, b=10), font=dict(size=13),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    if legend:
        fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.12, x=0, bgcolor="rgba(0,0,0,0)"))
    return fig


def need_profile():
    p = profile()
    if p is None:
        st.info("No replays analysed yet. Open **Replays** in the sidebar, scan your replays and press "
                "**Analyse replays**.")
        st.stop()
    return p


def played(p) -> pd.DataFrame:
    O = p.objects
    return O[O["played"] & (O["kind"] != "spinner")]


def maps_table(df: pd.DataFrame, extra: list[str] | None = None):
    if df is None or df.empty:
        st.caption("No maps found for this.")
        return
    t = pd.DataFrame({
        "Map": df["artist"].astype(str) + " – " + df["title"].astype(str) + " [" + df["version"].astype(str) + "]",
        "★": df["stars"].round(2), "BPM": df["bpm"].round(0), "AR": df["ar"],
        "Length": [f"{int(s // 60)}:{int(s % 60):02d}" if not isnan(s) else "–" for s in df["drain_length"]],
        "Why": df["why"],
    })
    for col in extra or []:
        t[col.capitalize()] = df[col]
    t["Link"] = df["url"]
    st.dataframe(t, hide_index=True, column_config={
        "Link": st.column_config.LinkColumn("Link", display_text="open ↗", width="small"),
        "★": st.column_config.NumberColumn(format="%.2f", width="small"),
        "BPM": st.column_config.NumberColumn(format="%d", width="small"),
        "AR": st.column_config.NumberColumn(format="%.1f", width="small"),
        "Length": st.column_config.TextColumn(width="small"),
        "Map": st.column_config.TextColumn(width="large"),
    })


def setup_from_settings() -> Setup:
    s = settings()
    setup = Setup(**{k: v for k, v in s.items() if k in Setup.__dataclass_fields__})
    if s.get("client") not in ("stable", "lazer"):
        setup.client = preferred_client()
    return setup


def preferred_client() -> str:
    """The client the player uses: saved setting, else what their replays / installs say."""
    s = settings()
    if s.get("client") in ("stable", "lazer"):
        return s["client"]
    p = profile()
    reps = getattr(p, "replays", None)
    if reps is not None and len(reps) and "client" in reps:
        return "lazer" if (reps["client"] == "lazer").mean() >= 0.5 else "stable"
    kinds = {i.kind for i in installs_cached()}
    return "lazer" if kinds == {"lazer"} else "stable"


# ------------------------------------------------------------------ Replays
LATEST_CHOICES = [100, 500, 1000, 0]   # 0 = all replays


def latest_label(n: int) -> str:
    return f"Latest {n}" if n else "All"


def page_replays():
    st.title("Your replays")
    st.caption("osu! coach reads your replay files (.osr), replays every note against the beatmap and measures how "
               "you aim and tap. Everything runs on this computer.")
    sett = settings()
    installs = installs_cached()
    with st.container(border=True):
        st.subheader("1 · Find replays")
        chosen = []
        if installs:
            for inst in installs:
                if st.checkbox(inst.label, value=True, key=f"inst::{inst.root}"):
                    chosen.append(inst)
        else:
            st.write("No osu! installation was found automatically on this computer. Add a folder below or drop "
                     "replay files.")
        folders = st.text_area(
            "Extra folders (one per line)", value=sett.get("folders") or os.environ.get("OSU_COACH_DEMO", ""),
            height=80, help="Folders are searched recursively for .osr replays and .osu beatmaps. "
                            "osu!stable keeps your replays in <osu!>/Data/r; in lazer use the Export button on the "
                            "results screen (files land in <lazer data>/exports).")
        uploads = st.file_uploader("…or drop replay files", type=["osr", "osu"], accept_multiple_files=True)
        saved = sett.get("latest", 500)
        latest = st.radio(
            "Replays to read", LATEST_CHOICES, index=LATEST_CHOICES.index(saved) if saved in LATEST_CHOICES else 1,
            format_func=latest_label, horizontal=True, key="latest",
            help="Only your newest replays: the scan reads the newest files first and stops as soon as it has them, "
                 "and only these are analysed. Fewer replays = faster, and closer to how you play now. "
                 "All = every replay on this computer.")
        if sett.get("latest") != latest:
            sett["latest"] = latest
            save_settings(sett)
        if st.button("Scan", type="primary", icon=":material/search:"):
            scan(chosen, folders, uploads, latest)
    lib = st.session_state.get("lib")
    if lib is not None and needs_more(lib, latest) and st.session_state.get("scan_args"):
        run_scan(st.session_state.scan_args, latest)     # same sources, further back
        lib = st.session_state.get("lib")
    if lib is not None:
        with st.container(border=True):
            st.subheader("2 · Analyse")
            players = lib.players()
            if not players:
                st.warning("No osu!standard replays found there (relax/autopilot/autoplay replays are skipped).")
            else:
                counts = dict(players)
                names = [n for n, _ in players]
                opts = names + (["*"] if len(names) > 1 else [])
                default = sett.get("player") if sett.get("player") in opts else names[0]
                player = st.selectbox("Player", opts, index=opts.index(default),
                                      format_func=lambda n: "All players" if n == "*" else
                                      f"{n or '(no name)'} ({counts[n]} replays found)")
                limit = latest or None
                refs = lib.eligible(player, limit)
                online = st.toggle("Download missing beatmaps from the internet", value=True,
                                   help="Looks the map up by its MD5 on osu.direct and downloads the .osu from "
                                        "osu.ppy.sh (verified against the replay).")
                if lib.has_unread_maps():
                    with st.spinner("Looking for the beatmaps of these replays…"):
                        lib.missing_maps(refs)
                missing = lib.missing_maps(refs)
                who = "all players" if player == "*" else (player or "(no name)")
                found = sum(counts.values()) if player == "*" else counts.get(player, 0)
                text = (f"The newest {len(refs)} replays of {who} will be analysed" if limit and found > len(refs)
                        else f"All {len(refs)} replays of {who} will be analysed")
                text += f" · {len(missing)} of their beatmaps are not on this computer"
                if online and missing:
                    text += " (they will be downloaded)"
                st.caption(text)
                if lib.scan_limit and limit and player not in ("*", names[0]) and found < limit:
                    st.caption(f"Only the newest files were read. Choose *All* to find older replays of {who}.")
                left = lib.left_out(player, since=refs[-1]["timestamp"] if limit and refs else None)
                if left:
                    st.caption(f"{sum(left.values())} replay(s) left out: " +
                               "; ".join(f"{n}× {reason}" for reason, n in left.most_common(3)) + ".")
                if st.button("Analyse replays", type="primary", icon=":material/insights:"):
                    run_analysis(lib, player, refs, online)
    p = profile()
    if p is not None:
        st.subheader(f"Analysed replays ({len(p.replays)})")
        m = p.replays
        table = pd.DataFrame({
            "Played": pd.to_datetime(m["date"]).dt.strftime("%Y-%m-%d %H:%M"),
            "Map": m["map_name"], "Mods": m["mod_string"].replace("", "NM"), "★": m.get("stars"),
            "Accuracy": m["accuracy"] * 100, "Misses": m["nmiss"], "Combo": m["max_combo"],
            "UR": m["ur"], "Check": m["sim_agreement"] * 100,
        }).sort_values("Played", ascending=False)
        st.dataframe(table, hide_index=True, column_config={
            "★": st.column_config.NumberColumn(format="%.2f"),
            "Accuracy": st.column_config.NumberColumn(format="%.2f%%"),
            "UR": st.column_config.NumberColumn(format="%.0f"),
            "Check": st.column_config.NumberColumn(
                format="%.1f%%", help="How well the re-simulated judgements match the result stored in the "
                                      "replay (100% = identical)."),
        })
        errors = st.session_state.get("errors") or []
        if errors:
            with st.expander(f"{len(errors)} replay(s) skipped"):
                for ref, err in errors[:200]:
                    st.write(f"`{Path(ref['path']).name}` — {err}")


def needs_more(lib: Library, latest: int) -> bool:
    """The last scan stopped earlier than the replay count chosen now asks for."""
    return lib.scan_limit is not None and (not latest or latest > lib.scan_limit)


def scan(chosen, folders: str, uploads, latest: int):
    paths = []
    if uploads:
        up = default_cache_dir() / "uploads"
        up.mkdir(parents=True, exist_ok=True)
        for u in uploads:
            dest = up / Path(u.name).name
            dest.write_bytes(u.getbuffer())
            paths.append(str(dest))
    args = {"installs": list(chosen), "files": paths,
            "folders": [f for f in (line.strip().strip('"') for line in folders.splitlines()) if f]}
    st.session_state.scan_args = args
    run_scan(args, latest)
    sett = settings()
    sett["folders"] = folders
    save_settings(sett)


def run_scan(args: dict, latest: int):
    limit = latest or None
    lib = Library()
    with st.status(f"Looking for your newest {limit} replays…" if limit else "Scanning for replays…") as status:
        def note(msg):
            status.update(label=str(msg))
        for inst in args["installs"]:
            note(f"Scanning {inst.label}…")
            lib.add_install(inst, progress=note, latest=limit)
        for f in args["folders"]:
            path = Path(f).expanduser()
            if path.is_dir():
                note(f"Scanning {path}…")
                lib.add_folder(path, latest=limit)
            else:
                st.warning(f"Folder not found: {f}")
        if args["files"]:
            lib.add_files(args["files"])
        players = lib.players()
        if players and lib.has_unread_maps():
            note("Looking for the beatmaps of these replays…")
            lib.missing_maps(lib.eligible(players[0][0], limit), progress=note)
        n = len(lib.standard_replays())
        status.update(label=(f"Read the newest replays: {n} osu!standard replays found" if limit
                             else f"Found {n} osu!standard replays"), state="complete")
    st.session_state.lib = lib


def run_analysis(lib: Library, player: str, refs: list[dict], online: bool):
    bar = st.progress(0.0, text="Preparing…")
    if online:
        missing = lib.missing_maps(refs)
        if missing:
            lib.fetch_missing(missing, progress=lambda i, n, msg: bar.progress(i / max(n, 1), text=msg))

    def cb(done, total, _msg):
        bar.progress(min(1.0, done / max(total, 1)), text=f"Analysing replays… {done}/{total}")
    analyses, errors = lib.analyze(refs, progress=cb)
    bar.empty()
    if not analyses:
        st.error("None of the replays could be analysed. " + (errors[0][1] if errors else ""))
        return
    with st.spinner("Saving your progress by month…"):
        try:
            progress.update(lib.cache, analyses, lib.load_cached)
        except Exception as exc:  # noqa: BLE001 - the analysis matters more than the history
            st.warning(f"Could not save your progress: {exc}")
    with st.spinner("Building your profile…"):
        prof = build_profile(analyses)
    st.session_state.update(profile=prof, analyses=analyses, errors=errors,
                            player_label="All players" if player == "*" else player)
    sett = settings()
    sett["player"] = player
    save_settings(sett)
    st.success(f"Analysed {len(analyses)} replays" + (f" ({len(errors)} skipped)" if errors else "") +
               ". Open **Overview** in the sidebar.")


# ------------------------------------------------------------------ Overview
def page_overview():
    p = need_profile()
    ov, lv = p.overview, p.levels
    st.title("Overview")
    c = st.columns(6)
    c[0].metric("Replays", ov["replays"], help=f"{ov['maps']} different maps")
    c[1].metric("Play time", fmt(ov["play_minutes"], ".0f", " min"))
    c[2].metric("Comfort level", fmt(lv.get("comfort_stars"), ".1f", "★"),
                help="Star rating you clear with at most ~2 misses per 100 notes.")
    c[3].metric("Unstable rate", fmt(ov["ur"], ".0f"),
                help="10 × the spread of your hit timing in ms. Lower = steadier timing.")
    c[4].metric("Misses / 100 notes", fmt(ov["misses_per_100"], ".1f"))
    c[5].metric("Accuracy", pct(ov["accuracy"]))
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Skills")
        rows = [(v["label"], v.get("score"), v.get("n", 0), v.get("observed"), v.get("expected"))
                for v in p.skills.values()]
        df = pd.DataFrame(rows, columns=["skill", "score", "n", "obs", "exp"])
        colors = [MUTED if isnan(s) else GOOD if s >= 55 else BAD if s <= 45 else INFO for s in df["score"]]
        hover = [f"{r.skill}<br>{r.n:,} notes" + (f"<br>misses: {r.obs:.0f} vs {r.exp:.0f} expected"
                                                  if not isnan(r.obs) and not isnan(r.exp) else "")
                 for r in df.itertuples()]
        fig = go.Figure(go.Bar(x=df["score"].fillna(0), y=df["skill"], orientation="h", marker_color=colors,
                               text=["not enough data" if isnan(s) else f"{s:.0f}" for s in df["score"]],
                               textposition="outside", hovertext=hover, hoverinfo="text"))
        fig.add_vline(x=50, line_dash="dot", line_color=MUTED)
        fig.update_xaxes(range=[0, 112], title="50 = as many misses as expected for the difficulty · higher is better")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(style(fig, 360), config={"displayModeBar": False})
    with right:
        st.subheader("Strengths & weaknesses")
        strong = [p.skills[k]["label"] for k in p.strengths]
        weak = [p.skills[k]["label"] for k in p.weaknesses]
        st.markdown("**Strong:** " + (", ".join(strong) or "not clear yet"))
        st.markdown("**Work on:** " + (", ".join(weak) or "not clear yet"))
        mb = p.miss_breakdown
        if mb:
            st.subheader("Why you miss")
            items = sorted(mb.items(), key=lambda kv: kv[1])
            fig = go.Figure(go.Bar(x=[v for _, v in items], y=[MISS_SHORT.get(k, k) for k, _ in items],
                                   orientation="h", marker_color=ACCENT,
                                   hovertext=[MISS_LABELS.get(k, k) for k, _ in items], hoverinfo="text+x"))
            st.plotly_chart(style(fig, 250), config={"displayModeBar": False})
    tips = make_tips(p, setup_from_settings())
    st.subheader("Top tips")
    cols = st.columns(3)
    for col, t in zip(cols, tips[:3]):
        with col.container(border=True):
            st.markdown(f"**{t.title}**")
            st.caption(t.evidence)
    if isnan(ov.get("sim_agreement")):
        st.caption("Data check: these replays don't store their results, so the re-simulation couldn't be "
                   "cross-checked.")
    else:
        st.caption(f"Data check: re-simulated judgements match the replays exactly on "
                   f"{pct(ov['sim_exact_share'], 0)} of replays ({pct(ov['sim_agreement'])} of all judgements).")


# ------------------------------------------------------------------ Progress
SKILL_COLORS = ["#ff66aa", "#6fb7ff", "#5fd3a0", "#ffb020", "#c792ea", "#ff8c5a", "#4dd0e1", "#a1887f"]


def _delta(last, prev, col: str, spec: str, scale: float = 1.0):
    if prev is None or isnan(last[col]) or isnan(prev[col]):
        return None
    return format((last[col] - prev[col]) * scale, spec)


def page_progress():
    st.title("Progress")
    st.caption("Every analysis is saved here, month by month (progress.sqlite in the osu! coach data folder). The "
               "history stays even if you delete replays later.")
    conn = progress.connect()
    try:
        names = progress.players(conn)
        if not names:
            st.info("Nothing saved yet. Analyse your replays on the **Replays** page — choose **All** there once to "
                    "fill in your older months.", icon=":material/timeline:")
            return
        counts = dict(names)
        opts = [n for n, _ in names]
        pref = settings().get("player")
        player = st.selectbox("Player", opts, index=opts.index(pref) if pref in opts else 0,
                              format_func=lambda n: f"{n or '(no name)'} ({counts[n]} plays saved)")
        m = progress.monthly(conn, player)
        months = list(m["month"])
        last = m.iloc[-1]
        prev = m.iloc[-2] if len(m) > 1 else None
        c = st.columns(5)
        c[0].metric("Comfort ★", fmt(last["comfort_stars"], ".2f"), _delta(last, prev, "comfort_stars", "+.2f"),
                    help="75% of your clean, finished plays (≤ 2 misses per 100 notes) are at or below this.")
        c[1].metric("Hardest clean pass ★", fmt(last["max_stars_passed"], ".2f"),
                    _delta(last, prev, "max_stars_passed", "+.2f"),
                    help="Hardest map finished with at most 5 misses per 100 notes.")
        c[2].metric("Plays", int(last["plays"]), _delta(last, prev, "plays", "+.0f"))
        c[3].metric("New maps", int(last["new_maps"]), _delta(last, prev, "new_maps", "+.0f"),
                    help="Maps played for the first time that month.")
        c[4].metric("Accuracy", pct(last["accuracy"], 2), _delta(last, prev, "accuracy", "+.2f", 100))
        st.caption(f"{last['month']}" + (f" compared with {prev['month']}." if prev is not None else ".")
                   + (" Few plays that month — the numbers are rough." if last["few_plays"] else ""))
        x = m["month"]
        symbols = ["circle-open" if f else "circle" for f in m["few_plays"]]
        fig = go.Figure()
        for col, name, color, width in (("comfort_stars", "comfort", ACCENT, 3), ("avg_stars", "average played", MUTED, 1.5),
                                        ("max_stars_passed", "hardest clean pass", INFO, 1.5),
                                        ("max_stars_fc", "hardest full combo", GOOD, 1.5)):
            fig.add_trace(go.Scatter(x=x, y=m[col], name=name, mode="lines+markers", connectgaps=True,
                                     line=dict(color=color, width=width), marker=dict(symbol=symbols, size=8)))
        fig.update_xaxes(type="category")
        fig.update_yaxes(title="★")
        st.plotly_chart(style(fig, 380, "Star rating by month", legend=True), config={"displayModeBar": False})
        skill_cols = [k for k in SKILL_LABELS if m[f"skill_{k}"].notna().sum() >= 1]
        if skill_cols:
            chosen = st.pills("Skills", skill_cols, selection_mode="multi", default=skill_cols,
                              format_func=lambda k: SKILL_LABELS[k].split(" (")[0], key="progress_skills")
            fig = go.Figure()
            for i, k in enumerate(chosen or []):
                fig.add_trace(go.Scatter(x=x, y=m[f"skill_{k}"], name=SKILL_LABELS[k].split(" (")[0],
                                         mode="lines+markers", connectgaps=True, marker=dict(symbol=symbols, size=8),
                                         line=dict(color=SKILL_COLORS[i % len(SKILL_COLORS)], width=2)))
            fig.add_hline(y=50, line=dict(color=MUTED, dash="dot"))
            fig.update_xaxes(type="category")
            fig.update_yaxes(range=[0, 100], title="score")
            st.plotly_chart(style(fig, 400, "Skills by month", legend=True), config={"displayModeBar": False})
            st.caption("50 = your all-time average at the same difficulty; higher = fewer misses than usual that "
                       "month. Hollow points: fewer than 5 plays that month.")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=x, y=m["plays"], name="plays", marker_color=ACCENT))
        fig.add_trace(go.Bar(x=x, y=m["new_maps"], name="new maps", marker_color=INFO))
        fig.add_trace(go.Scatter(x=x, y=m["minutes"], name="minutes played", yaxis="y2", mode="lines+markers",
                                 line=dict(color=GOOD)))
        fig.update_xaxes(type="category")
        fig.update_layout(barmode="group", yaxis2=dict(overlaying="y", side="right", showgrid=False, title="minutes",
                                                       rangemode="tozero", tickformat=".0f"))
        fig.update_yaxes(rangemode="tozero")
        st.plotly_chart(style(fig, 340, "What you played", legend=True), config={"displayModeBar": False})
        month = st.selectbox("Maps played in", list(reversed(months)), key="progress_month")
        plays = progress.month_plays(conn, player, month)
    finally:
        conn.close()
    if plays.empty:
        return
    local = pd.to_datetime(plays["played_at"], utc=True).dt.tz_convert(dt.datetime.now().astimezone().tzinfo)
    result = np.where(plays["fc"], "full combo", np.where(plays["completed"], "passed", "failed"))
    st.dataframe(pd.DataFrame({
        "Played": local.dt.strftime("%Y-%m-%d %H:%M"),
        "Map": plays["artist"].fillna("") + " – " + plays["title"].fillna("") + " [" + plays["version"].fillna("") + "]",
        "★": plays["stars"], "Mods": plays["mods"].fillna("").replace("", "NM"), "Accuracy": plays["accuracy"] * 100,
        "Misses": plays["nmiss"], "Combo": [f"{c:.0f}/{mc:.0f}" if not isnan(mc) else f"{c:.0f}"
                                            for c, mc in zip(plays["max_combo"], plays["map_max_combo"])],
        "Result": result,
    }), hide_index=True, column_config={"★": st.column_config.NumberColumn(format="%.2f"),
                                        "Accuracy": st.column_config.NumberColumn(format="%.2f%%")})


# ------------------------------------------------------------------ Aim
def page_aim():
    p = need_profile()
    st.title("Aim")
    a, reg, wq = p.aim, p.regression, p.worst_quadrant
    P = played(p)
    c = st.columns(4)
    c[0].metric("Aim misses", pct(a.get("aim_miss_share"), 0), help="Share of your misses where you tapped in time "
                                                                    "but outside the circle.")
    c[1].metric("Jump miss rate", pct(a.get("jump_miss_rate")))
    c[2].metric("Near misses", pct(a.get("near_miss_share"), 0), help="Aim misses that landed within 1.4 radii — "
                                                                      "just outside the circle.")
    c[3].metric("Jump distance error", fmt(a.get("jump_along_pct"), "+.1f", "%"),
                help="Median over/undershoot along the jump direction, as % of the jump length.")
    if wq:
        txt = (f"Weakest quadrant: **{wq['quadrant']}** — {pct(wq['miss_rate'])} misses vs {pct(wq['rest_miss_rate'])} "
               f"elsewhere ({wq['relative_risk']:.1f}×).")
        if wq["significant"]:
            st.warning(txt + " See **Tips & setup** for how to fix it.", icon=":material/target:")
        else:
            st.caption(txt + " The difference is still within noise.")
    left, right = st.columns(2, gap="large")
    with left:
        q = p.quadrants
        z, text = [], []
        for row in (("top-left", "top-right"), ("bottom-left", "bottom-right")):
            z.append([0.0 if isnan(q.loc[k, "miss_rate"]) else q.loc[k, "miss_rate"] * 100 for k in row])
            text.append([f"{pct(q.loc[k, 'miss_rate'])}<br>{int(q.loc[k, 'misses'])} / {int(q.loc[k, 'objects'])}"
                         for k in row])
        fig = go.Figure(go.Heatmap(z=z, x=["left", "right"], y=["top", "bottom"], text=text, texttemplate="%{text}",
                                   colorscale=[[0, "#24242e"], [1, ACCENT]], showscale=False, hoverinfo="skip"))
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(style(fig, 300, "Miss rate by screen quadrant"), config={"displayModeBar": False})
    with right:
        bins_x, bins_y = np.linspace(0, 512, 9), np.linspace(0, 384, 7)
        allh, _, _ = np.histogram2d(P["x"].clip(0, 511.9), P["y"].clip(0, 383.9), bins=[bins_x, bins_y])
        M = P[~P["head_hit"]]
        mh, _, _ = np.histogram2d(M["x"].clip(0, 511.9), M["y"].clip(0, 383.9), bins=[bins_x, bins_y])
        rate = np.where(allh >= 15, mh / np.maximum(allh, 1) * 100, np.nan)
        fig = go.Figure(go.Heatmap(z=rate.T, x=(bins_x[:-1] + bins_x[1:]) / 2, y=(bins_y[:-1] + bins_y[1:]) / 2,
                                   colorscale=[[0, "#24242e"], [1, ACCENT]], showscale=False,
                                   hovertemplate="miss rate %{z:.1f}%<extra></extra>"))
        fig.add_shape(type="line", x0=256, x1=256, y0=0, y1=384, line=dict(color=MUTED, dash="dot"))
        fig.add_shape(type="line", x0=0, x1=512, y0=192, y1=192, line=dict(color=MUTED, dash="dot"))
        fig.update_xaxes(range=[0, 512], showticklabels=False)
        fig.update_yaxes(range=[384, 0], showticklabels=False, scaleanchor="x")
        st.plotly_chart(style(fig, 300, "Where on the playfield you miss"), config={"displayModeBar": False})
    left, right = st.columns(2, gap="large")
    with left:
        click_chart(p)
    with right:
        d = p.directions
        r = [0 if isnan(d.loc[k, "miss_rate"]) else d.loc[k, "miss_rate"] * 100 for k in DIR_ANGLE]
        fig = go.Figure(go.Barpolar(r=r, theta=list(DIR_ANGLE.values()), marker_color=ACCENT, opacity=0.85,
                                    hovertext=[f"moving {k}: {pct(d.loc[k, 'miss_rate'])} misses "
                                               f"({int(d.loc[k, 'objects'])} jumps)" for k in DIR_ANGLE],
                                    hoverinfo="text"))
        fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(showticklabels=False, ticks=""),
                                     angularaxis=dict(direction="counterclockwise", rotation=0,
                                                      tickvals=list(DIR_ANGLE.values()),
                                                      ticktext=list(DIR_ANGLE.keys()))))
        st.plotly_chart(style(fig, 360, "Miss rate by jump direction").update_layout(
            margin=dict(l=40, r=40, t=60, b=40)), config={"displayModeBar": False})
    left, right = st.columns(2, gap="large")
    with left:
        dist = p.distances.reset_index()
        fig = go.Figure(go.Bar(x=dist["dbin"].astype(str), y=dist["miss_rate"] * 100, marker_color=ACCENT,
                               hovertext=[f"{int(n)} notes" for n in dist["objects"]], hoverinfo="text+y"))
        fig.add_trace(go.Scatter(x=dist["dbin"].astype(str), y=dist["along"], yaxis="y2", mode="lines+markers",
                                 line=dict(color=INFO), name="over/undershoot"))
        fig.update_layout(yaxis=dict(title="miss rate %"),
                          yaxis2=dict(title="over(+)/under(−)shoot, radii", overlaying="y", side="right",
                                      zeroline=True, zerolinecolor=MUTED, tickformat=".2f", showgrid=False))
        fig.update_xaxes(title="distance from the previous note (circle diameters)")
        st.plotly_chart(style(fig, 320, "By jump distance"), config={"displayModeBar": False})
    with right:
        st.subheader("Aim calibration")
        if reg:
            c = st.columns(2)
            c[0].metric("Horizontal distance", f"{(reg['scale_x'] - 1) * 100:+.1f}%",
                        help="How far you move compared with the real jump. + = overaim (too far).")
            c[1].metric("Vertical distance", f"{(reg['scale_y'] - 1) * 100:+.1f}%")
            c = st.columns(2)
            c[0].metric("Rotation", f"{reg['rotation_deg']:+.1f}°", help="+ = your movements come out clockwise.")
            c[1].metric("Constant offset", f"{math.hypot(reg['offset_x'], reg['offset_y']):.1f} px",
                        help=f"x {reg['offset_x']:+.1f}, y {reg['offset_y']:+.1f} osu!px")
            st.caption(f"Fitted on {reg['n']:,} jumps: your actual movement vs the movement that was needed. "
                       "This is what the tablet-area / sensitivity tips are based on.")
        else:
            st.caption("Not enough jumps yet (needs 40+).")
        ang = p.angles.reset_index()
        if len(ang):
            st.dataframe(pd.DataFrame({"Angle between jumps": ang["abin"].astype(str), "Notes": ang["objects"],
                                       "Miss rate": (ang["miss_rate"] * 100).round(1)}), hide_index=True)


CLICK_VIEWS = {"screen": "On screen", "movement": "Along the jump"}
MISS_COLOR = "#ffb020"
CLICKS_DRAWN = 4000


def click_chart(p):
    """Every click as a dot (a sample of the hits + all aim misses), on screen or rotated along the jump."""
    view = st.segmented_control("View", list(CLICK_VIEWS), format_func=CLICK_VIEWS.get, default="screen",
                                key="click_view", label_visibility="collapsed") or "screen"
    C = click_points(p.objects, view)
    if len(C) < 30:
        st.caption("Not enough clicks yet.")
        return
    s = click_summary(C)
    # one random sample of all clicks, so the share of aim misses in the picture is the real one
    drawn = C.sample(CLICKS_DRAWN, random_state=0) if len(C) > CLICKS_DRAWN else C
    drawn = drawn[(drawn["x"].abs() < 2.4) & (drawn["y"].abs() < 2.4)]
    hits, misses = drawn[drawn["hit"]], drawn[~drawn["hit"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hits["x"], y=hits["y"], mode="markers", name="hit", hoverinfo="skip",
                             marker=dict(size=3, color=ACCENT, opacity=0.35)))
    fig.add_trace(go.Scatter(x=misses["x"], y=misses["y"], mode="markers", name="aim miss", hoverinfo="skip",
                             marker=dict(size=5, color=MISS_COLOR, opacity=0.9)))
    fig.add_shape(type="circle", x0=-1, y0=-1, x1=1, y1=1, line=dict(color=MUTED, width=2))
    fig.add_shape(type="circle", x0=-0.5, y0=-0.5, x1=0.5, y1=0.5, line=dict(color=MUTED, width=1, dash="dot"))
    mx, my = s["mean_r"]
    fig.add_trace(go.Scatter(x=[mx], y=[my], mode="markers", name="average", hoverinfo="skip",
                             marker=dict(color="#ffffff", size=12, symbol="x", line=dict(color="#24242e", width=1.5))))
    fig.update_xaxes(range=[-2.4, 2.4], zeroline=False, constrain="domain",
                     title="circle radii" + (" · overshoot →" if view == "movement" else ""))
    fig.update_yaxes(range=[2.4, -2.4], zeroline=False, scaleanchor="x", scaleratio=1, constrain="domain")
    title = ("Where your clicks land — on screen" if view == "screen"
             else "Where your clicks land — jumps, turned so you move right")
    fig = style(fig, 430, title, legend=True)
    fig.update_layout(legend=dict(y=-0.2))       # below the axis title
    st.plotly_chart(fig, config={"displayModeBar": False})
    bands = " · ".join(f"{share * 100:.0f}% {label}" if label != "outside"
                       else f"{share * 100:.1f}% outside (aim misses)" for label, share in s["bands"].items())
    if view == "screen":
        (ox, oy), r = s["mean_px"], s["radius"]
        where = f"{abs(ox):.1f} px {'left' if ox < 0 else 'right'} and {abs(oy):.1f} px {'above' if oy < 0 else 'below'}"
        st.caption(f"Each dot is one click — {min(s['n'], CLICKS_DRAWN):,} picked at random from {s['n']:,}, so "
                   f"the share of yellow dots is the real one. Average of all clicks: {where} the "
                   f"centre (± {s['ci_px']:.1f} px), {math.hypot(ox, oy) / r:.0%} of the circle radius ({r:.0f} px). "
                   f"Spread: {s['sd_px'][0]:.0f} px sideways, {s['sd_px'][1]:.0f} px up/down. Clicks by distance "
                   f"from the centre (radii): {bands}. A hit is always inside the circle, so only aim misses land "
                   "outside it.")
    else:
        st.caption(f"Jumps only ({s['n']:,} clicks, {min(s['n'], CLICKS_DRAWN):,} drawn), turned so every jump "
                   "goes right: dots right of the centre "
                   f"overshot, left fell short. Average {s['mean_r'][0]:+.2f} radii along the jump. A constant "
                   "offset (e.g. always a bit left) cancels out in this view — see **On screen** for that. "
                   f"Clicks by distance (radii): {bands}.")


# ------------------------------------------------------------------ Tapping
def page_tapping():
    p = need_profile()
    st.title("Tapping")
    t = p.tapping
    c = st.columns(6)
    c[0].metric("Unstable rate", fmt(t.get("ur"), ".0f"), help="10 × timing spread (ms), lower is better.")
    c[1].metric("UR single notes", fmt(t.get("ur_single"), ".0f"))
    c[2].metric("UR streams", fmt(t.get("ur_streams"), ".0f"))
    c[3].metric("Average timing", fmt(t.get("mean_error"), "+.1f", " ms"), help="− = early, + = late.")
    c[4].metric("300s on single notes", pct(t.get("three_hundred_rate_single"), 0))
    c[5].metric("Alternation in streams", pct(t.get("alternation_in_streams"), 0),
                help="Share of stream notes hit with the other key than the previous note.")
    P = played(p)
    left, right = st.columns(2, gap="large")
    with left:
        errs = P.loc[P["head_hit"], "err_real"].dropna()
        errs = errs[errs.abs() <= 150]
        fig = go.Figure(go.Histogram(x=errs, xbins=dict(start=-150, end=150, size=3), marker_color=ACCENT))
        fig.add_vline(x=0, line_color=MUTED)
        if len(errs):
            fig.add_vline(x=float(errs.mean()), line_color=INFO, line_dash="dot")
        fig.update_xaxes(title="hit error (ms, real time) · early ← → late")
        st.plotly_chart(style(fig, 320, "Hit timing"), config={"displayModeBar": False})
    with right:
        sp = p.stream_profile
        if sp is None or sp.empty:
            st.subheader("Stream speed")
            st.caption("Not enough streams (7+ notes in a row) in your replays yet.")
        else:
            fig = go.Figure(go.Bar(x=sp["bpm_bin"], y=sp["miss_rate"] * 100, marker_color=ACCENT,
                                   hovertext=[f"{int(n)} notes" for n in sp["objects"]], hoverinfo="text+y"))
            fig.add_trace(go.Scatter(x=sp["bpm_bin"], y=sp["ur"], yaxis="y2", mode="lines+markers",
                                     line=dict(color=INFO)))
            fig.update_layout(yaxis=dict(title="miss rate %"), yaxis2=dict(title="UR", overlaying="y", side="right"))
            fig.update_xaxes(title="stream speed (BPM, 1/4 notes)")
            if t.get("comfort_bpm"):
                fig.add_vline(x=t["comfort_bpm"] + 5, line_color=GOOD, line_dash="dot")
            if t.get("limit_bpm"):
                fig.add_vline(x=t["limit_bpm"] + 5, line_color=BAD, line_dash="dot")
            st.plotly_chart(style(fig, 320, "Stream speed"), config={"displayModeBar": False})
            st.caption(f"Clean up to ≈ {fmt(t.get('comfort_bpm'), 'd')} BPM · breaks down from ≈ "
                       f"{fmt(t.get('limit_bpm'), 'd')} BPM (green / red lines).")
    left, right = st.columns(2, gap="large")
    with left:
        R = P[(P["run_len"] >= 8) & P["head_hit"] & (P["run_pos"] < 32)].dropna(subset=["err_real"])
        if len(R) > 60:
            g = R.groupby("run_pos")["err_real"].agg(["mean", "size"]).query("size >= 10")
            fig = go.Figure(go.Scatter(x=g.index + 1, y=g["mean"], mode="lines+markers", line=dict(color=ACCENT)))
            fig.add_hline(y=0, line_color=MUTED)
            fig.update_xaxes(title="note number inside the stream")
            fig.update_yaxes(title="average timing (ms)")
            st.plotly_chart(style(fig, 300, "Do you fall behind in long streams?"), config={"displayModeBar": False})
        else:
            st.caption("Long streams (8+ notes): not enough data yet.")
    with right:
        shares = t.get("key_share") or {}
        if shares:
            keys = sorted(shares)
            fig = go.Figure(go.Bar(x=keys, y=[shares[k] * 100 for k in keys], marker_color=ACCENT))
            fig.update_yaxes(title="% of presses")
            title = "Keys used (K = keyboard, M = mouse/pen buttons"
            title += ", L/R = lazer left/right)" if {"L", "R"} & set(keys) else ")"
            st.plotly_chart(style(fig, 300, title), config={"displayModeBar": False})
            if {"L", "R"} & set(keys):
                st.caption("lazer replays only store left/right, not whether a key or a mouse/pen button was used.")
        Pr = p.presses
        if Pr is not None and len(Pr):
            rates = dict(zip(p.replays["key"], p.replays["rate"]))
            dur = (Pr["duration"] / Pr["replay_key"].map(rates).fillna(1.0)).dropna()
            st.caption(f"Typical key hold: {fmt(dur.median(), '.0f')} ms · in streams "
                       f"{fmt(t.get('press_ms_streams'), '.0f')} ms · chatter {fmt(t.get('chatter_per_1000'), '.1f')} "
                       "per 1000 presses")


# ------------------------------------------------------------------ Sliders & reading
def page_sliders_reading():
    p = need_profile()
    st.title("Sliders & reading")
    sl, rd, cs = p.sliders, p.reading, p.consistency
    c = st.columns(4)
    c[0].metric("Sliders played", f"{sl.get('sliders', 0):,}")
    c[1].metric("Slider head misses", pct(sl.get("head_miss_rate")))
    c[2].metric("Slider breaks", pct(sl.get("break_rate")), help="Sliders hit at the head but broken later "
                                                                 "(left the follow circle or released the key).")
    c[3].metric("Missed slider ends", pct(sl.get("end_miss_rate")))
    left, right = st.columns(2, gap="large")
    with left:
        if p.slider_breaks:
            names = {"follow": "Left the follow circle", "released": "Released the key", "key_swap": "Switched keys"}
            items = sorted(p.slider_breaks.items(), key=lambda kv: kv[1])
            fig = go.Figure(go.Bar(x=[v for _, v in items], y=[names.get(k, k) for k, _ in items], orientation="h",
                                   marker_color=ACCENT))
            st.plotly_chart(style(fig, 240, "Why sliders break"), config={"displayModeBar": False})
        else:
            st.caption("No slider breaks — nice.")
    with right:
        ar = rd.get("ar_table")
        if ar is not None and len(ar):
            ar = ar.reset_index()
            fig = go.Figure(go.Bar(x=ar["ar_bin"], y=ar["miss_rate"] * 100, marker_color=INFO,
                                   hovertext=[f"{int(n)} notes" for n in ar["objects"]], hoverinfo="text+y"))
            fig.update_xaxes(title="approach rate (AR, with mods)")
            fig.update_yaxes(title="miss rate %")
            st.plotly_chart(style(fig, 240, "Misses by approach rate"), config={"displayModeBar": False})
    c = st.columns(4)
    c[0].metric("Dense parts", pct(rd.get("dense_miss_rate")),
                help=f"Miss rate when ≥{fmt(rd.get('dense_threshold'), '.0f')} notes are on screen.")
    c[1].metric("Sparse parts", pct(rd.get("sparse_miss_rate")))
    c[2].metric("Misses after a miss", fmt(cs.get("miss_after_miss_ratio"), ".1f", "×"),
                help="How much more you miss right after a miss than the difficulty explains (typical ≈ 2×).")
    c[3].metric("Misses in the last 20%", pct(cs.get("end_miss_share"), 0),
                help=f"Share of misses in the last fifth of maps ({pct(cs.get('end_object_share'), 0)} of the notes).")


# ------------------------------------------------------------------ Tips
SETUP_FIELDS = ["device", "handedness", "client", "area_w_mm", "area_h_mm", "screen_w_px", "screen_h_px",
                "mouse_dpi", "ingame_sens", "keyboard", "actuation_mm", "rt_press_mm", "rt_release_mm"]


KEY_DEVICES = {"standard": "Keyboard", "rapid_trigger": "Rapid-trigger keyboard (Wooting etc.)",
               "sayo": "SayoDevice keypad"}
SAYO_LAYOUT = [  # rows as in the SayoDevice configurator: (label, Setup field, kind)
    [("Stroke", "sayo_stroke_mm", "mm"), ("Trigger", "sayo_trigger_mm", "mm"), ("Release", "sayo_release_mm", "mm")],
    [("RT Mode", "sayo_rt", "toggle"), ("RT Trigger", "sayo_rt_trigger_mm", "mm"),
     ("RT Release", "sayo_rt_release_mm", "mm")],
    [("Full Stroke", "sayo_full_stroke", "toggle"), ("RT Upper Bound", "sayo_rt_upper_mm", "mm"),
     ("RT Lower Bound", "sayo_rt_lower_mm", "mm")],
]
SAYO_HELP = {
    "Stroke": "Full travel of your switches (4.0 mm for most magnetic switches).",
    "Trigger": "Fixed press depth (actuation point).",
    "Release": "Fixed reset depth — must be above (smaller than) Trigger.",
    "RT Mode": "Rapid trigger on/off.",
    "RT Trigger": "Inside the RT zone: press again after moving down this far.",
    "RT Release": "Inside the RT zone: release after moving up this far.",
    "Full Stroke": "Rapid trigger over the whole stroke (ignores the bounds).",
    "RT Upper Bound": "Depth where rapid trigger starts working.",
    "RT Lower Bound": "Depth where rapid trigger stops working (keep it a bit above the full stroke).",
}


def setup_editor(sett: dict, s: Setup):
    """Player setup: aim device, keys (keyboard / rapid trigger / SayoDevice) and their settings."""
    c = st.columns(2)
    device = c[0].radio("Aim with", ["tablet", "mouse"], index=["tablet", "mouse"].index(s.device), horizontal=True,
                        key="setup_device")
    keys = c[1].radio("Keys", list(KEY_DEVICES), format_func=KEY_DEVICES.get, horizontal=True,
                      index=list(KEY_DEVICES).index(s.keyboard if s.keyboard in KEY_DEVICES else "standard"),
                      key="setup_keys")
    with st.form("setup"):
        c1, c2, c3 = st.columns(3)
        hand = c1.radio("Pen / mouse hand", ["right", "left"], index=["right", "left"].index(s.handedness),
                        horizontal=True)
        client = c1.radio("osu! client", ["stable", "lazer"], index=["stable", "lazer"].index(s.client),
                          horizontal=True)
        sw = c1.number_input("Screen width (px)", 640, 7680, int(s.screen_w_px), step=1)
        sh = c1.number_input("Screen height (px)", 480, 4320, int(s.screen_h_px), step=1)
        upd = {}
        if device == "tablet":
            upd["area_w_mm"] = c2.number_input("Tablet area width (mm)", 0.0, 500.0, float(s.area_w_mm or 0.0),
                                               step=1.0, help="0 = unknown") or None
            upd["area_h_mm"] = c2.number_input("Tablet area height (mm)", 0.0, 500.0, float(s.area_h_mm or 0.0),
                                               step=1.0) or None
            upd["area_x_mm"] = c3.number_input(
                "Area X (mm)", 0.0, 500.0, s.area_x_mm, step=0.1, format="%.2f", placeholder="unknown",
                help="Where the area sits on the tablet: OpenTabletDriver → Output → X (the centre of the area).")
            upd["area_y_mm"] = c3.number_input("Area Y (mm)", 0.0, 500.0, s.area_y_mm, step=0.1, format="%.2f",
                                               placeholder="unknown", help="OpenTabletDriver → Output → Y.")
        else:
            upd["mouse_dpi"] = c2.number_input("Mouse DPI", 0, 50000, int(s.mouse_dpi or 0), step=50,
                                               help="0 = unknown") or None
            upd["ingame_sens"] = c2.number_input("osu! sensitivity", 0.0, 10.0, float(s.ingame_sens or 1.0),
                                                 step=0.05)
        if keys == "rapid_trigger":
            upd["actuation_mm"] = c3.number_input("Actuation point (mm)", 0.0, 4.0, float(s.actuation_mm or 0.0),
                                                  step=0.05) or None
            rt = c3.number_input("Rapid-trigger sensitivity (mm)", 0.0, 2.0, float(s.rt_release_mm or 0.0),
                                 step=0.05) or None
            upd.update(rt_press_mm=rt, rt_release_mm=rt)
        elif keys == "sayo":
            st.markdown("**SayoDevice** — the values from its configurator (sayodevice.com → Key stroke); leave "
                        "empty what you don't know")
            for row in SAYO_LAYOUT:
                cols = st.columns(3)
                for col, (label, field, kind) in zip(cols, row):
                    cur = getattr(s, field)
                    if kind == "toggle":
                        default = True if cur is None and field == "sayo_rt" else bool(cur)
                        upd[field] = col.toggle(label, value=default, help=SAYO_HELP[label])
                    else:
                        upd[field] = col.number_input(f"{label} (mm)", 0.0, 6.0, cur, step=0.05, format="%.3f",
                                                      placeholder="unknown", help=SAYO_HELP[label])
        if st.form_submit_button("Save setup", type="primary"):
            sett.update(device=device, keyboard=keys, handedness=hand, client=client, screen_w_px=int(sw),
                        screen_h_px=int(sh), setup_saved=True, **upd)
            save_settings(sett)
            st.rerun()


def tablet_area_box(a: dict):
    def mm(v):
        return "–" if v is None else f"{v:g}"
    rows = [("Width", "w"), ("Height", "h"), ("X (centre)", "x"), ("Y (centre)", "y")]
    with st.container(border=True):
        st.markdown("**Tablet area to try** — OpenTabletDriver values; X / Y = the centre of the area")
        st.dataframe(pd.DataFrame({"": [r[0] for r in rows], "Now (mm)": [mm(a["now"][k]) for _, k in rows],
                                   "Try (mm)": [mm(a[k]) for _, k in rows]}), hide_index=True)
        why = "; ".join(a["why"])
        st.caption(why[0].upper() + why[1:] + "." + ("" if a["now"]["x"] is not None and a["now"]["y"] is not None
                                                     else " Enter X / Y in your setup to get the position too."))


def sayo_table(r: dict):
    def show(v):
        return ("on" if v else "off") if isinstance(v, bool) else f"{v:.2f} mm"
    names = list(r["now"])
    table = pd.DataFrame({"Setting": names, "Now": [show(r["now"][k]) for k in names],
                          "Try": [show(r["new"][k]) for k in names]})
    changed = [r["new"][k] != r["now"][k] for k in names]
    if any(changed):
        table["Change"] = ["←" if c else "" for c in changed]
    st.dataframe(table, hide_index=True)


def page_tips():
    p = need_profile()
    st.title("Tips")
    sett = settings()
    with st.expander("Your setup — makes the tips concrete (tablet area, sensitivity, keyboard / SayoDevice)",
                     expanded=not sett.get("setup_saved"), icon=":material/tune:"):
        setup_editor(sett, setup_from_settings())
    s = setup_from_settings()
    area = suggest_tablet_area(p, s)
    if area:
        tablet_area_box(area)
    tips = make_tips(p, s)
    if not tips:
        st.success("No clear problems found in these replays. Keep playing and re-analyse later.")
    for t in tips:
        label, color = SEVERITY.get(t.severity, ("", "gray"))
        with st.container(border=True):
            head = st.columns([5, 1])
            head[0].markdown(f"**{t.title}**  \n<span style='color:{MUTED}'>{t.category}</span>",
                             unsafe_allow_html=True)
            with head[1]:
                st.badge(label, color=color)
            st.write(t.evidence)
            if t.category == "Keys / SayoDevice":
                sayo_table(sayo_settings(p, s))
            for a in t.actions:
                st.markdown(f"- {a}")
            if t.settings and t.category != "Keys / SayoDevice":
                st.caption("Suggested values: " + " · ".join(f"`{k}` = {v}" for k, v in t.settings.items()
                                                                if v is not None))
    st.subheader("Practice plan")
    st.markdown("\n".join(f"{i}. {step}" for i, step in enumerate(practice_plan(p), 1)))


# ------------------------------------------------------------------ Maps
def page_maps():
    p = need_profile()
    pool = pool_cached()
    st.title("Map suggestions")
    if pool.empty:
        st.error("The bundled map pool is missing.")
        return
    t = targets_from_profile(p)
    st.caption(f"Picked from {len(pool):,} popular ranked maps around your level ({t.comfort:.1f}★). Maps you "
               "already played are left out. For a full staged playlist use **Improve a skill**.")
    for sk, df in recommendations(pool, p, per_skill=5):
        if sk == "general":
            title, why = "Level up", "slightly above your comfort level"
        elif sk == "quadrant":
            title, why = skill_label(sk, t), "jumps that land in your weakest quadrant"
        else:
            sc = p.skills.get(sk, {}).get("score")
            title, why = skill_label(sk, t), f"one of your weakest skills (score {fmt(sc, '.0f')})"
        st.subheader(title)
        st.caption(why)
        maps_table(df)


# ------------------------------------------------------------------ Improve a skill
def page_improve():
    st.title("Improve a skill")
    pool = pool_cached()
    if pool.empty:
        st.error("The bundled map pool is missing.")
        return
    p = profile()
    sett = settings()
    if p is not None:
        t = targets_from_profile(p)
    else:
        st.info("No replays analysed yet — set your level by hand, or analyse replays for a personal playlist.")
        comfort = st.number_input("Star rating you can pass comfortably", 1.0, 8.0,
                                  float(sett.get("manual_comfort", 2.5)), step=0.1)
        t = Targets(comfort=comfort)
    options = SKILLS + (["quadrant"] if t.quadrant else [])
    default = (p.weaknesses[0] if p is not None and p.weaknesses else "aim")

    def label(sk):
        sc = p.skills.get(sk, {}).get("score") if p is not None else None
        return skill_label(sk, t) + (f"  ·  your score {sc:.0f}" if not isnan(sc) else "")
    c = st.columns([3, 2])
    skill = c[0].selectbox("Skill", options, index=options.index(default) if default in options else 0,
                           format_func=label)
    n = c[1].slider("Maps", 6, 30, 15, step=3)
    pl = build_playlist(pool, skill, t, n=n)
    name = collection_name(skill, t)
    info = f"Your level ≈ **{t.comfort:.1f}★**"
    if skill in ("speed", "stamina") and t.stream_bpm:
        info += f" · stream target ≈ **{t.stream_bpm:.0f} BPM**"
    st.markdown(info + f" · collection name: `{name}`")
    if pl.empty:
        st.warning("No maps found for this skill at your level.")
        return
    for stage in pl["stage"].unique():
        part = pl[pl["stage"] == stage]
        st.markdown(f"#### {stage}")
        st.caption(part["goal"].iloc[0])
        maps_table(part)
    st.subheader("Get the playlist into osu!")
    hashes = list(pl["md5"])
    text = "\n".join(f"[{r.stage}] {r.stars:.2f}* {r.artist} - {r.title} [{r.version}]  {r.url}"
                     for r in pl.itertuples())
    order = ["osu!lazer", "osu!stable"] if preferred_client() == "lazer" else ["osu!stable", "osu!lazer"]
    tabs = dict(zip(order, st.tabs(order)))
    with tabs["osu!lazer"]:
        lazer_import_ui(pl, name, hashes)
    with tabs["osu!stable"]:
        stable_import_ui(pl, name, hashes, skill)
    st.download_button("Map list with links (.txt)", data=f"{name}\n\n{text}\n", file_name="playlist.txt",
                       mime="text/plain", icon=":material/list:")


def lazer_import_ui(pl: pd.DataFrame, name: str, hashes: list[str]):
    st.markdown("lazer can't open a collection file by itself, but its **import from a previous osu! version** "
                "takes maps *and* collections from any folder that looks like an osu!stable install. osu! coach "
                "makes that folder for you in one click.")
    lib = st.session_state.get("lib")
    rows = list(zip(pl["md5"], pl["beatmapset_id"]))
    have = lib.installed["lazer"] if lib is not None else set()
    sets = lazer_import.sets_to_download(rows, have)
    n_sets = len(set(int(s) for s in pl["beatmapset_id"]))
    dest = lazer_import.default_pack_dir(name)
    if lib is not None and lib.has_unread_maps("lazer"):
        # a "Latest N" scan didn't read all of lazer's files: checked when the folder is made
        count = f"Up to {len(sets)} of {n_sets} beatmap sets will be downloaded (maps you already have are skipped)"
    else:
        count = (f"{len(sets)} of {n_sets} beatmap sets will be downloaded"
                 + (" (you already have the others)" if len(sets) < n_sets else ""))
    st.caption(f"{count} · folder: `{dest}`")
    c = st.columns(2)
    if c[0].button("Make lazer import folder", type="primary", icon=":material/create_new_folder:"):
        bar = st.progress(0.0, text="Preparing…")
        if lib is not None and lib.has_unread_maps("lazer"):
            bar.progress(0.0, text="Checking which of these maps you already have…")
            lib.find_maps(set(hashes))
            sets = lazer_import.sets_to_download(rows, lib.installed["lazer"])
        res = lazer_import.build_pack(dest, {name: hashes}, sets,
                                      progress=lambda i, n, msg: bar.progress(i / max(n, 1), text=msg))
        bar.empty()
        msg = f"Ready: `{res['path']}` with {len(res['maps'])} map set(s) and the collection."
        if res["failed"]:
            msg += f" Couldn't download set(s) {', '.join(map(str, res['failed']))}: use the links in the map list."
        st.success(msg, icon=":material/folder_open:")
        lazer_import.reveal(res["path"])
    c[1].download_button("Folder without maps (.zip)", data=lazer_import.pack_zip({name: hashes}, name),
                         file_name=f"{lazer_import.safe_name(name)}.zip", mime="application/zip",
                         icon=":material/folder_zip:",
                         help="Just the collection, e.g. for lazer on another computer: unzip it and import the "
                              "folder the same way. Get the maps from the links.")
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(lazer_import.INSTRUCTIONS, 1))
    st.markdown(f"**Then, in lazer:**\n\n{steps}")


def stable_import_ui(pl: pd.DataFrame, name: str, hashes: list[str], skill: str):
    c = st.columns(2)
    c[0].download_button("collection.db", data=collection_bytes({name: hashes}), file_name="collection.db",
                         mime="application/octet-stream", icon=":material/download:",
                         help="A collection file with this playlist, e.g. for Collection Manager.")
    stable = [i for i in installs_cached() if i.kind == "stable"]
    if stable and c[1].button("Add to my osu!stable collections", icon=":material/library_add:"):
        if locate.is_osu_running():
            st.error("Close osu! first — it rewrites collection.db when it exits.")
        else:
            res = merge_into(stable[0].root / "collection.db", {name: hashes})
            st.success(f"Added “{name}” to {res['path']} (backup: {res['backup'] or 'none needed'}).")
    default_dest = stable[0].songs if stable and stable[0].songs else Path.home() / "osu-coach-maps" / skill
    dest = st.text_input("Download the maps (.osz) to", value=str(default_dest),
                         help="osu!stable picks up .osz files in its Songs folder on the next start (or F5 in song "
                              "select).")
    if st.button("Download maps", icon=":material/cloud_download:"):
        sets = list(dict.fromkeys(int(s) for s in pl["beatmapset_id"]))
        bar = st.progress(0.0)
        ok, failed = 0, []
        for i, sid in enumerate(sets, 1):
            bar.progress(i / len(sets), text=f"Downloading {i}/{len(sets)} (set {sid})")
            if sources.download_osz(sid, Path(dest).expanduser()):
                ok += 1
            else:
                failed.append(sid)
        bar.empty()
        st.success(f"Downloaded {ok}/{len(sets)} beatmap sets to {dest}." +
                   (f" Failed: {', '.join(map(str, failed))}" if failed else ""))
    st.caption("Put the .osz files in the Songs folder (or drag them onto the osu! window), then use *Add to my "
               "osu!stable collections* with osu! closed — your old collection.db is backed up first.")


# ------------------------------------------------------------------ main
with st.sidebar:
    st.markdown("## osu! coach")
    page = st.radio("Page", PAGES, key="page", label_visibility="collapsed")
    sidebar_status = st.empty()

{
    "Replays": page_replays, "Overview": page_overview, "Aim": page_aim, "Tapping": page_tapping,
    "Sliders & reading": page_sliders_reading, "Tips & setup": page_tips, "Map suggestions": page_maps,
    "Progress": page_progress,
    "Improve a skill": page_improve,
}[page]()

# filled in last, so it is already up to date in the run that finished an analysis
if profile() is not None:
    _ov = profile().overview
    sidebar_status.caption(f"{st.session_state.get('player_label', '')} · {_ov['replays']} replays · "
                           f"{_ov['objects']:,} notes")
else:
    sidebar_status.caption("Start on the Replays page.")
