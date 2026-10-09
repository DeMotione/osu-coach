"""osu! coach — Streamlit UI.  Start with:  osu-coach ui
(or: streamlit run osu_coach/webapp/app.py)
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from osu_coach import lazer_import, locate, sources
from osu_coach.advice import Setup, make_tips, practice_plan
from osu_coach.collection_db import dumps as collection_bytes
from osu_coach.collection_db import merge_into
from osu_coach.library import Library, load_settings, save_settings
from osu_coach.pool import (SKILLS, Targets, build_playlist, collection_name, load_pool, recommendations,
                            skill_label, targets_from_profile)
from osu_coach.profile import MISS_LABELS, build_profile

ACCENT, GOOD, BAD, MUTED, INFO = "#ff66aa", "#5fd3a0", "#ff5c7a", "#8b8fa3", "#6fb7ff"
PAGES = ["Replays", "Overview", "Aim", "Tapping", "Sliders & reading", "Tips & setup", "Map suggestions",
         "Improve a skill"]
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


def style(fig: go.Figure, height: int = 320, title: str | None = None) -> go.Figure:
    fig.update_layout(template="plotly_dark", height=height, title=title, showlegend=False,
                      margin=dict(l=10, r=10, t=44 if title else 10, b=10), font=dict(size=13),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
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
        if st.button("Scan", type="primary", icon=":material/search:"):
            scan(chosen, folders, uploads)
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
                                      format_func=lambda n: "All players" if n == "*" else f"{n} ({counts[n]} replays)")
                refs_all = lib.eligible(player)
                limit = len(refs_all)
                if len(refs_all) > 1:
                    limit = st.slider("Newest replays to analyse", 1, len(refs_all), min(len(refs_all), 300))
                online = st.toggle("Download missing beatmaps from the internet", value=True,
                                   help="Looks the map up by its MD5 on osu.direct and downloads the .osu from "
                                        "osu.ppy.sh (verified against the replay).")
                refs = refs_all[:limit]
                missing = lib.missing_maps(refs)
                st.caption(f"{len(refs)} replays selected · {len(missing)} of their beatmaps are not on this computer")
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


def scan(chosen, folders: str, uploads):
    lib = Library()
    with st.status("Scanning for replays…") as status:
        for inst in chosen:
            status.update(label=f"Scanning {inst.label}…")
            lib.add_install(inst, progress=lambda m: status.update(label=str(m)))
        for line in folders.splitlines():
            f = line.strip().strip('"')
            if not f:
                continue
            path = Path(f).expanduser()
            if path.is_dir():
                status.update(label=f"Scanning {path}…")
                lib.add_folder(path)
            else:
                st.warning(f"Folder not found: {f}")
        if uploads:
            up = lib.cache / "uploads"
            up.mkdir(parents=True, exist_ok=True)
            paths = []
            for u in uploads:
                dest = up / Path(u.name).name
                dest.write_bytes(u.getbuffer())
                paths.append(dest)
            lib.add_files(paths)
        status.update(label=f"Found {len(lib.standard_replays())} osu!standard replays", state="complete")
    st.session_state.lib = lib
    sett = settings()
    sett["folders"] = folders
    save_settings(sett)


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
        H = P[(P["head_hit"] | (P["miss_reason"] == "aim")) & (P["dist_norm"] >= 1)].dropna(subset=["along", "cross"])
        H = H[(H["along"].abs() < 3) & (H["cross"].abs() < 3)]
        if len(H) > 30:
            fig = go.Figure(go.Histogram2dContour(x=H["along"], y=H["cross"], ncontours=14, showscale=False,
                                                  colorscale=[[0, "rgba(0,0,0,0)"], [0.2, "#3b2433"], [1, ACCENT]],
                                                  contours=dict(coloring="heatmap", showlines=False)))
            fig.add_shape(type="circle", x0=-1, y0=-1, x1=1, y1=1, line=dict(color="#e8e8f0", width=1.5))
            fig.add_trace(go.Scatter(x=[H["along"].mean()], y=[H["cross"].mean()], mode="markers",
                                     marker=dict(color="#ffffff", size=9, symbol="x"), hoverinfo="skip"))
            fig.add_annotation(x=1.9, y=-2.2, text="movement →", showarrow=False, font=dict(color=MUTED))
            fig.update_xaxes(range=[-2.4, 2.4], zeroline=False, title="overshoot → (circle radii)", constrain="domain")
            fig.update_yaxes(range=[2.4, -2.4], zeroline=False, scaleanchor="x", scaleratio=1, constrain="domain")
            st.plotly_chart(style(fig, 340, "Where your clicks land (jumps, rotated so you move right)"),
                            config={"displayModeBar": False})
            st.caption("The white circle is the hit circle; × is your average click. A cloud shifted right means "
                       "overaim, left means underaim.")
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
            st.plotly_chart(style(fig, 300, "Keys used (K = keyboard, M = mouse/pen buttons)"),
                            config={"displayModeBar": False})
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


def page_tips():
    p = need_profile()
    st.title("Tips")
    sett = settings()
    s = setup_from_settings()
    with st.expander("Your setup — makes the tips concrete (tablet area, sensitivity, rapid trigger)",
                     expanded=not sett.get("setup_saved"), icon=":material/tune:"):
        with st.form("setup"):
            c1, c2, c3 = st.columns(3)
            device = c1.radio("Aim with", ["tablet", "mouse"], index=["tablet", "mouse"].index(s.device),
                              horizontal=True)
            hand = c1.radio("Pen / mouse hand", ["right", "left"], index=["right", "left"].index(s.handedness),
                            horizontal=True)
            client = c1.radio("osu! client", ["stable", "lazer"], index=["stable", "lazer"].index(s.client),
                              horizontal=True)
            aw = c2.number_input("Tablet area width (mm)", 0.0, 500.0, float(s.area_w_mm or 0.0), step=1.0,
                                 help="0 = unknown")
            ah = c2.number_input("Tablet area height (mm)", 0.0, 500.0, float(s.area_h_mm or 0.0), step=1.0)
            sw = c2.number_input("Screen width (px)", 640, 7680, int(s.screen_w_px), step=1)
            sh = c2.number_input("Screen height (px)", 480, 4320, int(s.screen_h_px), step=1)
            dpi = c3.number_input("Mouse DPI", 0, 50000, int(s.mouse_dpi or 0), step=50, help="0 = unknown")
            sens = c3.number_input("osu! sensitivity", 0.0, 10.0, float(s.ingame_sens or 1.0), step=0.05)
            kb = c3.selectbox("Keyboard", ["standard", "rapid_trigger"],
                              index=["standard", "rapid_trigger"].index(s.keyboard),
                              format_func=lambda k: "Rapid trigger (Hall effect)" if k == "rapid_trigger"
                              else "Normal keyboard / keypad")
            act = c3.number_input("Actuation point (mm)", 0.0, 4.0, float(s.actuation_mm or 0.0), step=0.05)
            rt = c3.number_input("Rapid-trigger sensitivity (mm)", 0.0, 2.0, float(s.rt_release_mm or 0.0),
                                 step=0.05)
            if st.form_submit_button("Save setup", type="primary"):
                sett.update(device=device, handedness=hand, client=client, area_w_mm=aw or None,
                            area_h_mm=ah or None, screen_w_px=int(sw), screen_h_px=int(sh), mouse_dpi=dpi or None,
                            ingame_sens=sens, keyboard=kb, actuation_mm=act or None, rt_press_mm=rt or None,
                            rt_release_mm=rt or None, setup_saved=True)
                save_settings(sett)
                st.rerun()
    tips = make_tips(p, setup_from_settings())
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
            for a in t.actions:
                st.markdown(f"- {a}")
            if t.settings:
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
    have = getattr(lib, "installed", {}).get("lazer", set()) if lib is not None else set()
    sets = lazer_import.sets_to_download(zip(pl["md5"], pl["beatmapset_id"]), have)
    n_sets = len(set(int(s) for s in pl["beatmapset_id"]))
    dest = lazer_import.default_pack_dir(name)
    st.caption(f"{len(sets)} of {n_sets} beatmap sets will be downloaded"
               + (" (you already have the others)" if len(sets) < n_sets else "") + f" · folder: `{dest}`")
    c = st.columns(2)
    if c[0].button("Make lazer import folder", type="primary", icon=":material/create_new_folder:"):
        bar = st.progress(0.0, text="Preparing…")
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
    "Improve a skill": page_improve,
}[page]()

# filled in last, so it is already up to date in the run that finished an analysis
if profile() is not None:
    _ov = profile().overview
    sidebar_status.caption(f"{st.session_state.get('player_label', '')} · {_ov['replays']} replays · "
                           f"{_ov['objects']:,} notes")
else:
    sidebar_status.caption("Start on the Replays page.")
