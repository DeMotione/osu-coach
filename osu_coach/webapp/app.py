"""osu! coach — Streamlit UI.  Start with:  osu-coach ui
(or: streamlit run osu_coach/webapp/app.py)
"""
from __future__ import annotations

import datetime as dt
import math
import os
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from osu_coach import check, lazer_import, locate, progress, selection, sources
from osu_coach.advice import Setup, aim_calibration, make_tips, practice_plan, sayo_settings, suggest_tablet_area
from osu_coach.collection_db import dumps as collection_bytes
from osu_coach.collection_db import merge_into
from osu_coach.beatmap import read_metadata
from osu_coach.library import (EXCLUDE_MODS, Library, analysable, default_cache_dir, load_settings, save_settings,
                               skip_reason)
from osu_coach.pool import (SKILLS, Targets, build_playlist, collection_name, load_pool, recommendations,
                            skill_label, stream_length_maps, targets_from_profile)
from osu_coach.profile import (LEVEL_BAND, MISS_LABELS, SKILL_HELP, SKILL_LABELS, build_profile, click_points,
                               click_summary, weight_table)

ACCENT, GOOD, BAD, MUTED, INFO = "#ff66aa", "#5fd3a0", "#ff5c7a", "#8b8fa3", "#6fb7ff"
CHECK_PAGE = "Detailed Map Analysis"   # one play on its own (check.py)
PAGES = ["Replays", CHECK_PAGE, "Overview", "Progress", "Aim", "Tapping", "Sliders & Reading", "Tips & Setup",
         "Map Suggestion", "Skill Development"]
MISS_SHORT = {"aim": "Aim", "speed_aim": "Speed-aim (streams)", "early": "Too early", "late": "Too late",
              "no_tap": "No tap", "lost": "Lost track", "notelock": "Notelock"}
DIR_ANGLE = {"right": 0, "up-right": 45, "up": 90, "up-left": 135, "left": 180, "down-left": 225, "down": 270,
             "down-right": 315}
SEVERITY = {3: ("High impact", "red"), 2: ("Medium impact", "orange"), 1: ("Nice to know", "gray")}

st.set_page_config(page_title="osu! coach", page_icon=":material/sports_esports:", layout="wide")
# no link icon next to headings: it only adds a #fragment to the URL; the sidebar's collapse button is always
# shown (Streamlit hides it until the mouse is over the sidebar)
st.html("<style>[data-testid='stHeaderActionElements'], .stMarkdown h1 a, .stMarkdown h2 a, .stMarkdown h3 a,"
        ".stMarkdown h4 a {display: none !important;}"
        "[data-testid='stSidebarCollapseButton'] {visibility: visible !important;}</style>")


# ------------------------------------------------------------------ helpers
def settings() -> dict:
    if "settings" not in st.session_state:
        st.session_state.settings = load_settings()
    return st.session_state.settings


def profile():
    """The profile of the analysed replays with the current choices (All / Best replays, level override),
    rebuilt when they change. (Tests may set ``profile`` directly.)"""
    ss = st.session_state
    analyses = ss.get("analyses")
    if not analyses:
        return ss.get("profile")
    sett = settings()
    rs, lvl = sett.get("replay_set", "all"), sett.get("level_override")
    sig = (rs, lvl, tuple(a.key for a in analyses))
    if ss.get("profile_sig") != sig:
        chosen = selection.select(analyses, rs)
        ss.profile = build_profile(chosen, level=lvl) if chosen else None
        ss.profile_sig = sig
    return ss.profile


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


def page_title(text: str, sub: str | None = None):
    """Page title + a short line on what the page shows."""
    st.title(text, anchor=False)
    if sub:
        st.caption(sub)


def section(text: str, sub: str | None = None):
    """Section title + a short line on how to read it."""
    st.subheader(text, anchor=False)
    if sub:
        st.caption(sub)


PLOT_CONFIG = {"displayModeBar": False, "scrollZoom": False, "doubleClick": False}


def static(fig: go.Figure) -> go.Figure:
    """No click-and-drag zoom or pan: every axis fixed (hover still works)."""
    fig.update_layout(dragmode=False)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def plot(fig: go.Figure):
    st.plotly_chart(static(fig), config=PLOT_CONFIG)


def chart(fig: go.Figure, how: str | None = None):
    """A chart and, under it, how to read it."""
    plot(fig)
    if how:
        st.caption(how)


# charts follow Streamlit's light / dark theme (no fixed plotly template): transparent backgrounds,
# colours that read on both
HEAT_LOW = "rgba(128, 128, 160, 0.12)"


def style(fig: go.Figure, height: int = 320, title: str | None = None, legend: bool = False) -> go.Figure:
    fig.update_layout(height=height, title=title, showlegend=legend,
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


def weights(df: pd.DataFrame) -> np.ndarray:
    """Difficulty weight of every row (its replay's weight), 1 if there are none."""
    return df["w"].to_numpy(float) if "w" in df else np.ones(len(df))


DIFFICULTY_HELP = "Star rating (with the mods of the play, e.g. DT)."


def maps_table(df: pd.DataFrame, extra: list[str] | None = None):
    """Map list with the same columns everywhere: Map, Difficulty, BPM, AR, Length, Detail description, Link."""
    if df is None or df.empty:
        st.caption("No maps found for this.")
        return
    t = pd.DataFrame({
        "Map": df["artist"].astype(str) + " – " + df["title"].astype(str) + " [" + df["version"].astype(str) + "]",
        "Difficulty": df["stars"].round(2), "BPM": df["bpm"].round(0), "AR": df["ar"],
        "Length": [f"{int(s // 60)}:{int(s % 60):02d}" if not isnan(s) else "–" for s in df["drain_length"]],
        "Detail description": df["why"],
    })
    for col in extra or []:
        t[col.capitalize()] = df[col]
    t["Link"] = df["url"]
    st.dataframe(t, hide_index=True, column_config={
        "Link": st.column_config.LinkColumn("Link", display_text="open ↗", width="small"),
        "Difficulty": st.column_config.NumberColumn(format="%.2f ★", width="small", help=DIFFICULTY_HELP),
        "Detail description": st.column_config.TextColumn(
            help="Why this map was picked: the patterns it has for the skill."),
        "BPM": st.column_config.NumberColumn(format="%d", width="small"),
        "AR": st.column_config.NumberColumn(format="%.1f", width="small"),
        "Length": st.column_config.TextColumn(width="small"),
        "Map": st.column_config.TextColumn(width="medium"),
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
SOURCE_MODES = {"library": "My replays (osu! installs and folders)", "files": "Only these files"}


def latest_label(n: int) -> str:
    return f"Latest {n}" if n else "All"


def remember(key: str, value) -> bool:
    """Save a choice in the settings (remembered across starts); True if it changed."""
    sett = settings()
    if sett.get(key) == value:
        return False
    sett[key] = value
    save_settings(sett)
    return True


def date_choice_ui(sett: dict):
    """Date filter (remembered): returns (choice, start, end)."""
    saved = sett.get("date_range", "all")
    choice = st.radio(
        "Played", selection.DATE_CHOICES, index=selection.DATE_CHOICES.index(saved)
        if saved in selection.DATE_CHOICES else 0, format_func=selection.DATE_LABELS.get, horizontal=True,
        key="date_range", help="Only replays played in this time: your recent form. Last session = your newest "
                               "replay and the ones before it with less than an hour between plays.")
    remember("date_range", choice)
    start = end = None
    if choice == "custom":
        today = dt.date.today()
        try:
            start = dt.date.fromisoformat(sett.get("date_from") or "")
        except ValueError:
            start = today - dt.timedelta(days=30)
        try:
            end = dt.date.fromisoformat(sett.get("date_to") or "")
        except ValueError:
            end = today
        rng = st.date_input("From – to (both days included)", value=(start, end), key="date_custom")
        if isinstance(rng, (tuple, list)) and len(rng) == 2:
            start, end = rng
            remember("date_from", start.isoformat())
            remember("date_to", end.isoformat())
    return choice, start, end


def replay_set_ui(key: str = "replay_set") -> str:
    """The All replays / Best replays switch (remembered)."""
    saved = settings().get("replay_set", "all")
    rs = st.segmented_control("Replays to use", selection.REPLAY_SETS, format_func=selection.REPLAY_SET_LABELS.get,
                              default=saved if saved in selection.REPLAY_SETS else "all", key=key) or "all"
    st.caption(selection.BEST_DEFINITION + " All replays = every play, including fails and retries.")
    if remember("replay_set", rs):
        st.rerun()
    return rs


def page_replays():
    page_title("Your replays", "osu! coach reads your replay files (.osr), replays every note against the beatmap and "
                               "measures how you aim and tap. Everything runs on this computer.")
    sett = settings()
    installs = installs_cached()
    with st.container(border=True):
        section("1 · Find replays", "Where the replays come from: your osu! installs and folders, or only the "
                                    "files you drop here.")
        saved_mode = sett.get("source_mode", "library")
        mode = st.radio("Analyse", list(SOURCE_MODES), format_func=SOURCE_MODES.get, horizontal=True,
                        index=list(SOURCE_MODES).index(saved_mode) if saved_mode in SOURCE_MODES else 0,
                        key="source_mode")
        remember("source_mode", mode)
        chosen, folders, latest = [], "", 0
        date = ("all", None, None)
        if mode == "files":
            uploads = st.file_uploader("Replay files to analyse — only these, the rest of your library is ignored",
                                       type=["osr", "osu"], accept_multiple_files=True, key="only_files",
                                       help="Drag and drop .osr files (and their .osu maps if they aren't on this "
                                            "computer). Missing maps are downloaded.")
        else:
            if installs:
                for inst in installs:
                    if st.checkbox(inst.label, value=True, key=f"inst::{inst.root}"):
                        chosen.append(inst)
            else:
                st.write("No osu! installation was found automatically on this computer. Add a folder below or "
                         "drop replay files.")
            folders = st.text_area(
                "Extra folders (one per line)", value=sett.get("folders") or os.environ.get("OSU_COACH_DEMO", ""),
                height=80, help="Folders are searched recursively for .osr replays and .osu beatmaps. "
                                "osu!stable keeps your replays in <osu!>/Data/r; in lazer use the Export button on "
                                "the results screen (files land in <lazer data>/exports).")
            uploads = st.file_uploader("…or add replay files", type=["osr", "osu"], accept_multiple_files=True)
            saved = sett.get("latest", 500)
            latest = st.radio(
                "Replays to read", LATEST_CHOICES, index=LATEST_CHOICES.index(saved) if saved in LATEST_CHOICES else 1,
                format_func=latest_label, horizontal=True, key="latest",
                help="Only your newest replays: the scan reads the newest files first and stops as soon as it has "
                     "them, and only these are analysed. Fewer replays = faster, and closer to how you play now. "
                     "All = every replay on this computer.")
            remember("latest", latest)
            date = date_choice_ui(sett)
        if st.button("Scan", type="primary", icon=":material/search:"):
            if mode == "files" and not uploads:
                st.warning("Drop the replay files to analyse first.")
            else:
                scan(chosen, folders, uploads, latest, only=mode == "files")
    lib = st.session_state.get("lib")
    if lib is not None and needs_more(lib, latest) and st.session_state.get("scan_args") \
            and not st.session_state.scan_args.get("only"):
        run_scan(st.session_state.scan_args, latest)     # same sources, further back
        lib = st.session_state.get("lib")
    if lib is not None:
        only = bool(st.session_state.get("scan_args", {}).get("only"))
        with st.container(border=True):
            section("2 · Analyse", "Which of the found replays go into the analysis. The time filter and *Replays "
                                   "to read* pick them before anything is analysed; *Best replays* keeps your best "
                                   "play per map afterwards.")
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
                limit = None if only else (latest or None)
                every = lib.eligible(player)
                choice, start, end = ("all", None, None) if only else date
                since, until = selection.date_window(choice, [r.get("timestamp") for r in every], start, end)
                refs = selection.filter_refs(every, since, until)[:limit]
                replay_set_ui()
                online = st.toggle("Download missing beatmaps from the internet", value=True,
                                   help="Looks the map up by its MD5 on osu.direct and downloads the .osu from "
                                        "osu.ppy.sh (verified against the replay).")
                if lib.has_unread_maps():
                    with st.spinner("Looking for the beatmaps of these replays…"):
                        lib.missing_maps(refs)
                missing = lib.missing_maps(refs)
                who = "all players" if player == "*" else (player or "(no name)")
                found = sum(counts.values()) if player == "*" else counts.get(player, 0)
                when = "" if choice == "all" else f" played {selection.DATE_LABELS[choice].lower()}"
                if choice == "custom" and start and end:
                    when = f" played {start:%Y-%m-%d} – {end:%Y-%m-%d}"
                text = (f"The newest {len(refs)} replays of {who}{when} will be analysed" if limit and found > len(refs)
                        else f"{len(refs)} replays of {who}{when} will be analysed")
                text += f" · {len(missing)} of their beatmaps are not on this computer"
                if online and missing:
                    text += " (they will be downloaded)"
                st.caption(text)
                if not refs and choice != "all":
                    st.warning("No replays in that time range — choose a longer one.")
                if lib.scan_limit and limit and player not in ("*", names[0]) and found < limit:
                    st.caption(f"Only the newest files were read. Choose *All* to find older replays of {who}.")
                left = lib.left_out(player, since=refs[-1]["timestamp"] if limit and refs else None)
                if left:
                    st.caption(f"{sum(left.values())} replay(s) left out: " +
                               "; ".join(f"{n}× {reason}" for reason, n in left.most_common(3)) + ".")
                if st.button("Analyse replays", type="primary", icon=":material/insights:", disabled=not refs):
                    run_analysis(lib, player, refs, online)
    p = profile()
    if p is not None:
        rs = settings().get("replay_set", "all")
        section(f"Analysed replays ({len(p.replays)})",
                ("Best replays only — the" if rs == "best" else "The") + " plays your numbers come from, newest first. "
                "Weight = how much a play counts: 100% within ±0.5★ of your level, less the further its difficulty "
                "is from it. Click a row, then **Detailed map analysis** to see that play on its own.")
        m = p.replays
        table = pd.DataFrame({
            "Played": pd.to_datetime(m["date"]).dt.strftime("%Y-%m-%d %H:%M"),
            "Map": m["map_name"], "Mods": m["mod_string"].replace("", "NM"), "Difficulty": m.get("stars"),
            "Weight": m["weight"] * 100 if "weight" in m else 100.0,
            "Accuracy": m["accuracy"] * 100, "Misses": m["nmiss"], "Combo": m["max_combo"],
            "UR": m["ur"], "Check": m["sim_agreement"] * 100, "path": m["source_path"],
        }).sort_values("Played", ascending=False)
        paths = list(table.pop("path"))
        picked = st.dataframe(table, hide_index=True, on_select="rerun", selection_mode="single-row",
                              key="analysed_table", column_config={
            "Difficulty": st.column_config.NumberColumn(format="%.2f ★", help=DIFFICULTY_HELP),
            "Weight": st.column_config.ProgressColumn(
                format="%.0f%%", min_value=0, max_value=100,
                help="How much this play counts in the statistics (difficulty weighting, see Overview)."),
            "Accuracy": st.column_config.NumberColumn(format="%.2f%%"),
            "UR": st.column_config.NumberColumn(format="%.0f"),
            "Check": st.column_config.NumberColumn(
                format="%.1f%%", help="How well the re-simulated judgements match the result stored in the "
                                      "replay (100% = identical)."),
        })
        rows = picked.selection.rows if picked is not None else []
        if rows:
            st.button("Detailed map analysis", icon=":material/manage_search:", type="primary", on_click=open_check,
                      args=(paths[rows[0]],))
        errors = st.session_state.get("errors") or []
        if errors:
            with st.expander(f"{len(errors)} replay(s) skipped"):
                for ref, err in errors[:200]:
                    st.write(f"`{Path(ref['path']).name}` — {err}")
    elif st.session_state.get("analyses") and settings().get("replay_set") == "best":
        st.warning("None of the analysed replays is a passed play, so *Best replays* is empty — switch to *All "
                   "replays*.")


def needs_more(lib: Library, latest: int) -> bool:
    """The last scan stopped earlier than the replay count chosen now asks for."""
    return lib.scan_limit is not None and (not latest or latest > lib.scan_limit)


def scan(chosen, folders: str, uploads, latest: int, only: bool = False):
    paths = []
    if uploads:
        up = default_cache_dir() / "uploads"
        up.mkdir(parents=True, exist_ok=True)
        for u in uploads:
            dest = up / Path(u.name).name
            dest.write_bytes(u.getbuffer())
            paths.append(str(dest))
    args = {"installs": [] if only else list(chosen), "files": paths, "only": only,
            "map_installs": list(installs_cached()) if only else [],     # only for the beatmaps of those files
            "folders": [] if only else [f for f in (line.strip().strip('"') for line in folders.splitlines()) if f]}
    st.session_state.scan_args = args
    run_scan(args, 0 if only else latest)
    if not only:
        remember("folders", folders)


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
        for inst in args.get("map_installs", []):
            lib.add_map_source(inst)
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
    st.session_state.update(analyses=analyses, errors=errors, profile_sig=None, profile=None,
                            player_label="All players" if player == "*" else player)
    with st.spinner("Building your profile…"):
        prof = profile()
    remember("player", player)
    if prof is None:
        st.warning("None of these replays is a passed play, so *Best replays* is empty — switch to *All replays*.")
        return
    best = settings().get("replay_set") == "best"
    st.success(f"Analysed {len(analyses)} replays" + (f" ({len(errors)} skipped)" if errors else "") +
               (f"; {len(prof.replays)} of them are best replays" if best else "") +
               ". Open **Overview** in the sidebar.")


# ------------------------------------------------------------------ Detailed Map Analysis (one replay)
CHECK_LATEST = 100   # replays listed when nothing was scanned yet
CHECK_LIST = 300
REASON_COLORS = {"aim": "#ffb020", "early": INFO, "late": "#c792ea", "no_tap": BAD, "lost": MUTED,
                 "notelock": "#4dd0e1", "spinner": "#a1887f", "follow": "#ff8c5a", "released": "#ff8c5a",
                 "key_swap": "#ff8c5a"}
RESULT_COLORS = {300: GOOD, 100: INFO, 50: "#ffb020"}


def open_check(path: str):
    st.session_state.update(page=CHECK_PAGE, check_path=path)


def same_file(a, b) -> bool:
    try:
        return Path(a) == Path(b)
    except TypeError:
        return False


@st.cache_data(show_spinner=False, max_entries=5000)
def map_title(path: str | None) -> str:
    return check.map_label(read_metadata(path)) if path else check.NO_MAP


def check_library() -> Library | None:
    """The scan of the Replays page, else a quick one of the newest replays on this computer."""
    lib = st.session_state.get("lib")
    if lib is not None:
        return lib
    if st.session_state.get("check_lib") is None:
        installs = installs_cached()
        if not installs:
            return None
        with st.spinner("Looking for your newest replays…"):
            lib = Library()
            for inst in installs:
                lib.add_install(inst, latest=CHECK_LATEST)
        st.session_state.check_lib = lib
    return st.session_state.check_lib


def replay_label(r: dict, lib: Library) -> str:
    mods = "".join(r.get("lazer_mods") or []) or r.get("mod_string") or "NM"
    acc = r.get("accuracy")
    return (f"{check.local_time(r['timestamp'])} · {r.get('player') or '(no name)'} · "
            f"{map_title(lib.maps.get(r['beatmap_md5']))} · {mods}" + (f" · {acc:.2%}" if acc is not None else ""))


def page_check():
    page_title(CHECK_PAGE, "One play on its own: every miss and combo break with its time in the map (osu! editor "
                               "format mm:ss:mmm), where they cluster, your timing, and how the play compares with "
                               "your other plays.")
    lib = check_library()
    up = st.file_uploader("Check a replay file", type=["osr"], key="check_upload",
                          help="Any .osr — e.g. exported from lazer's results screen, or someone else's replay.")
    if up is not None and st.session_state.get("check_upload_id") != up.file_id:
        dest = default_cache_dir() / "uploads" / Path(up.name).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(up.getbuffer())
        if lib is None:
            lib = st.session_state.check_lib = Library()
        if not any(same_file(r["path"], dest) for r in lib.replays):
            lib.add_files([dest])
        st.session_state.update(check_upload_id=up.file_id, check_path=str(dest))
    if lib is None:
        st.info("No osu! installation was found automatically. Drop a replay file above, or scan a folder on the "
                "**Replays** page.", icon=":material/info:")
        return
    refs = lib.eligible("*")[:CHECK_LIST]
    want = st.session_state.get("check_path")
    if want and not any(same_file(r["path"], want) for r in refs):
        h = next((r for r in lib.replays if same_file(r["path"], want)), None) or locate.replay_header(Path(want))
        if h:
            refs = [h] + refs
    if not refs:
        st.info("No osu!standard replays found. Drop a replay file above, or scan on the **Replays** page.",
                icon=":material/info:")
        return
    focus = st.session_state.get("check_md5")
    if want and st.session_state.get("check_md5_for") != want:   # a replay just dropped in / opened: its map
        hw = next((r for r in refs if same_file(r["path"], want)), None)
        if hw:
            focus = st.session_state.check_md5 = hw.get("beatmap_md5")
            st.session_state.check_md5_for = want
            st.session_state.check_only_map = True     # show this map's plays first
    only = st.toggle("Only plays of this map", key="check_only_map", disabled=not focus,
                     help="List only your replays of the map shown below (all of them, not just the newest).")
    if only and focus:
        mine = [r for r in lib.eligible("*") if r.get("beatmap_md5") == focus]
        refs = [r for r in refs if r.get("beatmap_md5") == focus]
        refs += [r for r in mine if not any(same_file(r["path"], x["path"]) for x in refs)]
        refs.sort(key=lambda r: str(r.get("timestamp") or ""), reverse=True)
    if lib.has_unread_maps():
        with st.spinner("Looking for the maps of these replays…"):
            lib.missing_maps(refs)
    start = next((i for i, r in enumerate(refs) if want and same_file(r["path"], want)), 0)
    i = st.selectbox("Replay", range(len(refs)), index=start, format_func=lambda k: replay_label(refs[k], lib),
                     help="Newest first. Pick a row on the Replays page and press 'Detailed map analysis' to open "
                          "it here.")
    ref = refs[i]
    st.session_state.check_md5 = ref.get("beatmap_md5")
    if not analysable(ref):
        reason = (skip_reason(ref) or ("relax / autopilot / autoplay replays aren't checked"
                                       if ref.get("mods", 0) & EXCLUDE_MODS else "only osu!standard is supported"))
        st.warning(f"This replay can't be checked: {reason}.")
        return
    online = st.toggle("Download the map if it's missing", value=True, key="check_online")
    with st.spinner("Checking the replay…"):
        missing = lib.missing_maps([ref])
        if missing and online:
            lib.fetch_missing(missing)
        analyses, errors = lib.analyze([ref], workers=1)
    if not analyses:
        st.error(f"Can't check this replay: {errors[0][1] if errors else 'unknown error'}")
        return
    a = analyses[0]
    # every other replay of this map on the computer (same player), for the comparison
    same = [r for r in lib.replays if r.get("beatmap_md5") == ref.get("beatmap_md5") and analysable(r)
            and (r.get("player") or "") == (ref.get("player") or "") and not same_file(r["path"], ref["path"])]
    others = []
    if same:
        with st.spinner(f"Reading your other {len(same[:MAP_PLAYS_MAX])} plays of this map…"):
            others, _ = lib.analyze(same[:MAP_PLAYS_MAX])
    conn = progress.connect(lib.cache)
    try:
        cmp = check.compare(conn, a, others)
        progress.record(conn, [a] + list(others))
    finally:
        conn.close()
    show_check(a, cmp)


def show_check(a, cmp: dict):
    ev = check.events(a)
    s = check.summary(a, ev)
    m = a.meta
    st.subheader(s["map"], anchor=False)
    link = f" · [beatmap page](https://osu.ppy.sh/b/{m['beatmap_id']})" if m.get("beatmap_id") else ""
    rate = s["rate"] or 1.0
    st.caption(f"{s['player'] or '(no name)'} · played {check.local_time(s['date'])} · osu!{s['client']} · "
               f"{check.mods_label(s['mods'], rate)} · mapped by {m.get('creator') or '?'}{link}")
    c = st.columns(5)
    c[0].metric("Accuracy", pct(s["accuracy"], 2))
    c[1].metric("Combo", f"{s['combo']}/{s['map_combo']:.0f}" if not isnan(s["map_combo"]) else str(s["combo"]))
    c[2].metric("Misses", s["misses"], help="Judged misses, as on the results screen.")
    c[3].metric("Slider breaks", s["slider_breaks"])
    c[4].metric("Difficulty", fmt(s["stars"], ".2f", "★"),
                help=f"Star rating with {check.mods_label(s['mods'], rate)}")
    # the map as it was played: speed and difficulty settings with the mods (DT/HT/custom rate, HR/EZ, DA)
    c = st.columns(8)
    c[0].metric("BPM", fmt(s["bpm"], ".0f"), help="Main BPM of the map at the speed of this play.")
    c[1].metric("UR", fmt(s["ur"], ".0f"), help="Unstable rate of this play: 10 × the spread of your hit timing (ms).")
    c[2].metric("Speed", f"×{rate:g}", help="1.5 = DT/NC, 0.75 = HT; lazer can set any rate.")
    for col, name in zip(c[3:7], ("ar", "od", "cs", "hp")):
        col.metric(name.upper(), fmt(m.get(name), ".1f"), help="With the mods of this play (HR, EZ, DT, Difficulty "
                                                                 "Adjust, …).")
    length = s.get("length_s")
    c[7].metric("Length", "–" if isnan(length) else f"{int(length // 60)}:{int(length % 60):02d}",
                help="Drain time at the speed of this play.")
    st.markdown("\n".join(f"- {v}" for v in s["verdict"]) + ("" if s["completed"] else "\n- **Failed play.**"
                if not any(v.startswith("Failed") for v in s["verdict"]) else ""))
    if not s["sim_exact"]:
        st.caption(f"The re-simulation differs a little from the result stored in the replay "
                   f"({(s['sim_agreement'] or 0):.1%} agreement), so times may be slightly off.")
    section("Misses and combo breaks", "One row per miss or combo break, in map order. Time = where it is in the map "
                                       "(type it into the osu! editor to jump there); Reason = why it was missed.")
    if ev.empty:
        st.success("No misses and no combo breaks in this play.")
    else:
        st.dataframe(pd.DataFrame({
            "Time": ev["timestamp"], "What": ev["what"],
            "Reason": [check.REASON_WORDS.get(r, r) for r in ev["reason"]], "Detail description": ev["detail"],
            "Pattern": [check.pattern_label(p, b) for p, b in zip(ev["pattern"], ev["stream_bpm"])],
        }), hide_index=True, column_config={"Time": st.column_config.TextColumn(
            help="Map time as the osu! editor shows it (mm:ss:mmm).")})
        practice_box(a, ev)
    timing_chart(a, ev)
    map_plays_box(a, s, cmp)
    prof = single_profile(a)
    if prof is not None:
        left, _ = st.columns(2, gap="large")
        with left:
            click_chart(prof)


def practice_box(a, ev):
    secs = check.practice_sections(a, ev)
    if not secs:
        return
    section("Where they cluster — parts to practise",
            "Each part starts a measure before the first miss and ends just after the last one, on the notes of the "
            "map, so you can cut it out exactly.")
    st.markdown("\n".join(
        f"- `{check.timestamp(x['start'])}`–`{check.timestamp(x['end'])}` · **{x['seconds']:.1f} s, {x['notes']} "
        f"notes** — {x['count']}: "
        + ", ".join(f"{n} {check.REASON_WORDS.get(k, k)}" for k, n in sorted(x["reasons"].items(),
                                                                             key=lambda kv: -kv[1]))
        + (f" · {check.pattern_label(x['pattern'], x['bpm'])}" if x["pattern"] else "")
        + f" (misses {check.timestamp(x['first_event'])}–{check.timestamp(x['last_event'])})"
        for x in secs[:5]))
    st.caption("How to practise a part: open the map in the editor and use File → Create a new difficulty (stable copies "
               "the current notes into it — delete everything outside the two times; lazer: copy the notes between the "
               "times first, then paste them into the new difficulty). Type the times into the timeline to jump there. "
               "Play the part with the same mods and speed as here until it is clean, then play the whole map again "
               "and open the new replay on this page: the table below shows whether it helped.")


MAP_PLAYS_MAX = 50   # other replays of the map read for the comparison


def map_plays_box(a, s: dict, cmp: dict):
    plays = cmp.get("plays")
    section("All your plays of this map",
            "Every play of this map in your history and on this computer, newest first. Only plays with the same "
            "speed and settings (DT/HT/custom rate, AR/OD/CS/HP, HD/FL) are compared: a DT ×1.5 play at 285 BPM and "
            "a ×1.26 play at 240 BPM are different challenges.")
    if plays is None or len(plays) <= 1:
        st.markdown("**First play of this map** in your saved history.")
        return
    settings = cmp.get("settings") or "normal speed"
    if cmp["map_plays"]:
        best = "**your best play with these settings**" if cmp["map_best"] else "not your best with these settings"
        line = (f"**Same settings** ({settings}): {cmp['map_plays']} other play(s); best {cmp['map_best_misses']} "
                f"misses ({cmp['map_best_accuracy']:.2%}) — this is {best}.")
        if not isnan(s["ur"]) and not isnan(cmp.get("ur_median", math.nan)):
            line += f" UR {s['ur']:.0f} vs {cmp['ur_median']:.0f} usually."
        st.markdown(line)
    else:
        st.markdown(f"**First play with these settings** ({settings}).")
    if cmp.get("other_settings"):
        st.caption(f"{cmp['other_settings']} play(s) with other settings are listed but not compared.")
    t = pd.DataFrame({
        "": ["▶ this play" if x else ("same settings" if ss else "") for x, ss in zip(plays["this"],
                                                                                  plays["same_settings"])],
        "Played": [check.local_time(d.to_pydatetime()) if not pd.isna(d) else "–" for d in plays["date"]],
        "Mods": [check.mods_label(mo, r) for mo, r in zip(plays["mods"], plays["rate"])],
        "Settings": [check.settings_label(r) or "–" for r in plays.to_dict("records")],
        "BPM": pd.to_numeric(plays["bpm"], errors="coerce").round(0),
        "Difficulty": pd.to_numeric(plays["stars"], errors="coerce").round(2),
        "Accuracy": pd.to_numeric(plays["accuracy"], errors="coerce") * 100,
        "Misses": pd.to_numeric(plays["nmiss"], errors="coerce"),
        "Combo": pd.to_numeric(plays["max_combo"], errors="coerce"),
        "UR": pd.to_numeric(plays["ur"], errors="coerce").round(0),
        "Passed": [bool(x) if not pd.isna(x) else None for x in plays["completed"]],
    })
    picked = st.dataframe(t, hide_index=True, on_select="rerun", selection_mode="single-row", key="map_plays_table",
                          column_config={
                              "Accuracy": st.column_config.NumberColumn(format="%.2f%%"),
                              "Difficulty": st.column_config.NumberColumn(format="%.2f ★", help=DIFFICULTY_HELP),
                              "BPM": st.column_config.NumberColumn(format="%d"),
                              "UR": st.column_config.NumberColumn(format="%d"),
                              "Misses": st.column_config.NumberColumn(format="%d"),
                              "Combo": st.column_config.NumberColumn(format="%d")})
    rows = picked.selection.rows if picked is not None else []
    if rows:
        r = plays.iloc[rows[0]]
        path = r["path"] if isinstance(r["path"], str) else ""
        if r["this"]:
            st.caption("That's the play shown above.")
        elif path and Path(path).exists():
            st.button("Open this play", icon=":material/manage_search:", type="primary", on_click=open_check,
                      args=(path,))
        else:
            st.caption("The replay file of that play is no longer on this computer (only its numbers were saved).")


def single_profile(a):
    try:
        return build_profile([a])
    except Exception:  # noqa: BLE001 - a very short play may be too little for a profile
        return None


def timing_chart(a, ev):
    o = a.objects
    H = o[o["played"] & o["head_hit"] & (o["kind"] != "spinner")].dropna(subset=["err_real"])
    if len(H) < 5:
        return
    t = pd.to_datetime(H["time"], unit="ms")
    fig = go.Figure()
    for res, color in RESULT_COLORS.items():
        sel = H["head_result"] == res
        if sel.any():
            fig.add_trace(go.Scattergl(x=t[sel], y=H.loc[sel, "err_real"], mode="markers", name=str(res),
                                       marker=dict(size=4, color=color, opacity=0.6), hoverinfo="skip"))
    trend = H["err_real"].rolling(25, center=True, min_periods=5).mean()
    fig.add_trace(go.Scatter(x=t, y=trend, mode="lines", name="running average", line=dict(color=ACCENT, width=2.5),
                             hoverinfo="skip"))
    top = float(H["err_real"].abs().quantile(0.99) or 50) * 1.15
    if not ev.empty:
        for reason, g in ev.groupby("reason"):
            fig.add_trace(go.Scatter(
                x=pd.to_datetime(g["time"], unit="ms"), y=[top] * len(g), mode="markers",
                name=check.REASON_WORDS.get(reason, reason), marker=dict(symbol="x", size=9,
                                                                         color=REASON_COLORS.get(reason, BAD)),
                hovertext=[f"{ts} {w}" for ts, w in zip(g["timestamp"], g["what"])], hoverinfo="text"))
    od = a.meta.get("od")
    if od is not None and not isnan(od):
        w300 = 80 - 6 * od
        for y in (w300, -w300):
            fig.add_hline(y=y, line=dict(color=MUTED, dash="dot", width=1))
    fig.update_xaxes(tickformat="%M:%S")
    fig.update_yaxes(title="hit error, ms (− early, + late)", range=[-top * 1.08, top * 1.08])
    plot(style(fig, 360, "Timing through the map — misses and breaks marked on top", legend=True))
    st.caption("Map time along the bottom. Each dot is one hit; the pink line is your running average (above 0 = "
               "late). Dotted lines: the 300 window.")


# ------------------------------------------------------------------ Overview
def level_box(p):
    """The detected level, the weighting band, and a manual override (remembered)."""
    lv = p.levels
    level = lv.get("level_stars")
    with st.container(border=True):
        c = st.columns([3, 2], gap="large")
        with c[0]:
            if isnan(level):
                st.markdown("**Your level: unknown** — no star ratings in these replays, so every play counts fully.")
                return
            how = ("set by you" if lv.get("level_override") else
                   f"detected from your {lv.get('level_recent_n', 0)} most recent replays (last 30 days)")
            st.markdown(f"**Your level: {level:.2f}★** — {how}")
            fade = ", ".join(f"{d:g}★ off: {w:.0%}" if w >= 0.005 else f"{d:g}★ off: ~0%" for d, w in
                             weight_table(level)[1:])
            band = lv.get("level_band", LEVEL_BAND)
            weighted = p.overview.get("weighted_replays", len(p.replays))
            st.caption(f"Replays from {level - band:.1f} to {level + band:.1f}★ count fully; the further a play's "
                       f"star rating (with mods, e.g. DT) is from your level, the less it counts ({fade}). So a "
                       "warm-up on an easy map or a 9★ map for fun doesn't distort your numbers. Every page uses "
                       f"these weights: your {len(p.replays)} replays count as {weighted:.1f}.")
        with c[1]:
            saved = settings().get("level_override")
            manual = st.toggle("Set my level by hand", value=saved is not None, key="level_manual",
                               help="If the detected level is off (e.g. you only played easy maps lately).")
            if manual:
                value = st.number_input("My level (★)", 1.0, 12.0, float(saved if saved is not None else
                                                                        round(lv.get("level_detected") or level, 1)),
                                        step=0.1, format="%.1f", key="level_value")
                changed = remember("level_override", float(value))
            else:
                changed = remember("level_override", None)
                if not isnan(lv.get("level_detected", math.nan)):
                    st.caption(f"Detected: {lv['level_detected']:.2f}★")
            if changed and st.session_state.get("analyses"):
                st.rerun()


def _num(v, spec: str = ".0f") -> str | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else format(v, spec)


def _dur(W) -> str:
    W = float(W)
    return f"{W:.0f} s" if W < 60 else f"{W / 60:.0f} min"


def skill_facts(key: str, v: dict) -> list[str]:
    """The player's own numbers behind a skill score, for its hover text."""
    facts = []
    n = v.get("n") or 0
    if key == "accuracy":
        r, ur = _num(v.get("three_hundred_rate"), ".0%"), _num(v.get("ur"))
        facts.append(f"{n:,} single notes" + (f", {r} hit as 300s" if r else "") + (f", UR {ur}" if ur else ""))
    elif key == "sliders":
        br, val, ref = _num(v.get("break_rate"), ".1%"), _num(v.get("value")), _num(v.get("ref"))
        held = _num(v.get("top_held"), ".0%")
        facts.append(f"{n:,} sliders" + (f", {br} broken" if br else ""))
        if val:
            facts.append(f"your best {v.get('plays', 0)} maps: hardest sliders worth {val}"
                         + (f" (typical for your level: {ref})" if ref else "")
                         + (f", {held} of them held" if held else ""))
    elif key == "consistency":
        r = _num(v.get("miss_after_miss_ratio"), ".2f")
        facts.append(f"{n:,} notes" + (f", miss-after-miss ratio {r}" if r else ""))
    elif key == "reading":
        ar, hit = _num(v.get("lowest_ar"), ".1f"), _num(v.get("bpm_hit"), ".0%")
        facts.append(f"{v.get('maps', 0)} passed maps" + (f", lowest AR {ar}" if ar else ""))
        if v.get("bpm_maps"):
            facts.append(f"{v['bpm_maps']} maps with BPM changes" + (f", {hit} of the notes after them as 300s"
                                                                     if hit else ""))
    elif key == "aim":
        val, ref = _num(v.get("value"), ".1f"), _num(v.get("ref"), ".1f")
        inten, combo = _num(v.get("intensity"), ".0f"), _num(v.get("combo"), ".0%")
        facts.append(f"{n:,} jumps on {v.get('maps', 0)} passed maps")
        if val:
            facts.append(f"cursor speed of your hardest jumps {inten} circles/s, combo held {combo} of the map; "
                         f"value {val} (typical for your level {ref})")
    elif key == "speed":
        bpm, best, ref = _num(v.get("bpm")), _num(v.get("best_bpm")), _num(v.get("ref_bpm"))
        clean = _num(v.get("clean_share"), ".0%")
        if bpm:
            facts.append(f"clean burst / stream speed {bpm} BPM (typical for your level {ref}), fastest map {best}")
        facts.append(f"{n:,} bursts and streams" + (f", {clean} clean" if clean else ""))
    elif key == "stamina":
        curve = v.get("curve") or {}
        if curve:
            facts.append("tempo you kept up: " + ", ".join(
                f"{_dur(W)} {bpm:.0f} BPM" for W, bpm in curve.items()))
        bs, stead = v.get("best_stream") or {}, _num(v.get("steadiness"), ".0%")
        if bs or stead:
            facts.append((f"hardest stream {bs['notes']} notes at {bs['bpm']:.0f} BPM" if bs else "")
                         + (", " if bs and stead else "") + (f"steadiness {stead}" if stead else ""))
    else:
        o, x = _num(v.get("observed")), _num(v.get("expected"))
        facts.append(f"{n:,} notes" + (f", {o} misses vs {x} expected" if o and x else ""))
    return facts


def score_text(v: dict) -> str:
    """A skill's score as shown, or why there is none."""
    s = _num(v.get("score"))
    if s:
        return s
    return "too few misses to tell" if v.get("too_few_misses") else "not enough data"


def skill_hover(key: str, v: dict, width: int = 64) -> str:
    """Hover text of a skill bar on Overview: score, what the skill measures, how the score is worked out,
    the player's own numbers and what raises it."""
    def wrap(text: str) -> str:
        return "<br>".join(textwrap.wrap(text, width))
    lines = [f"<b>{v.get('label', SKILL_LABELS.get(key, key))}: {score_text(v)}</b>"]
    if v.get("too_few_misses"):
        lines += [wrap("You barely miss on these notes, so there is nothing to compare: this score counts misses "
                       "against what the difficulty predicts. That is a good sign, not a gap.")]
    help_ = SKILL_HELP.get(key)
    if help_:
        what, how, practise = help_
        lines += [wrap(what), "", wrap(how)]
    lines += ["", wrap("You: " + "; ".join(skill_facts(key, v)))]
    if help_:
        lines += ["", wrap("To raise it: " + practise)]
    return "<br>".join(lines)


def page_overview():
    p = need_profile()
    ov, lv = p.overview, p.levels
    page_title("Overview", "Your main numbers at a glance. Every number is weighted by difficulty: plays close to your "
                           "level count fully, plays far below or above it hardly count (see *Your level*).")
    level_box(p)
    c = st.columns(6)
    c[0].metric("Replays", ov["replays"], help=f"{ov['maps']} different maps; they count as "
                                               f"{ov.get('weighted_replays', ov['replays']):.1f} after the weighting")
    c[1].metric("Play time", fmt(ov["play_minutes"], ".0f", " min"))
    c[2].metric("Comfort level", fmt(lv.get("comfort_stars"), ".1f", "★"),
                help="75% of your finished plays with at most 2 misses per 100 notes are at or below this star "
                     "rating (all analysed replays).")
    c[3].metric("Unstable rate", fmt(ov["ur"], ".0f"),
                help="10 × the spread of your hit timing in ms. Lower = steadier timing.")
    c[4].metric("Misses / 100 notes", fmt(ov["misses_per_100"], ".1f"))
    c[5].metric("Accuracy", pct(ov["accuracy"]))
    left, right = st.columns([3, 2], gap="large")
    with left:
        section("Skills", "One bar per skill, 0–100; 50 = typical for your level (flow aim and consistency: you miss "
                          "as often as your own miss model expects for those notes). Like osu! pp, the "
                          "hardest plays of each skill count most: 100%, then 1/(replays analysed) less per place. "
                          "Green ≥ 55, red ≤ 45, grey = not enough data, or too few misses to tell.")
        rows = [(k, v["label"], v.get("score"), v.get("n", 0), v.get("observed"), v.get("expected"))
                for k, v in p.skills.items()]
        df = pd.DataFrame(rows, columns=["key", "skill", "score", "n", "obs", "exp"])
        colors = [MUTED if isnan(s) else GOOD if s >= 55 else BAD if s <= 45 else INFO for s in df["score"]]
        hover = [skill_hover(k, p.skills[k]) for k in df["key"]]
        fig = go.Figure(go.Bar(x=df["score"].fillna(0), y=df["skill"], orientation="h", marker_color=colors,
                               text=[score_text(p.skills[k]) for k in df["key"]],
                               textposition="outside", hovertext=hover, hoverinfo="text"))
        fig.add_vline(x=50, line_dash="dot", line_color=MUTED)
        fig.update_xaxes(range=[0, 112], title="50 = typical for your level · higher is better")
        fig.update_yaxes(autorange="reversed")
        # hovering anywhere on a skill's row (also an empty "not enough data" row) shows its explanation
        fig.update_layout(hovermode="y", hoverlabel=dict(align="left"))
        plot(style(fig, 420))
        stam = p.skills.get("stamina") or {}
        if stam.get("score") is not None and stam.get("curve"):
            ref = stam.get("ref_curve") or {}
            rows = " · ".join(f"{_dur(W)}: **{bpm:.0f}** BPM (typical {ref.get(W, float('nan')):.0f})"
                              for W, bpm in stam["curve"].items())
            st.caption("**Stamina** is not a miss count: it is how long you keep a high tempo. For 10 s, 30 s, "
                       "1, 2 and 5 minutes: the fastest tempo (notes per second as stream BPM) you kept up while "
                       "still pressing 90%+ of the notes — once your fingers give in and you start undertapping, "
                       "it stops counting; overstreaming never counts against you. Each duration: all your "
                       "maps weighted like osu! pp (hardest 100%, then 1 / replays less each), against what is typical "
                       "for your level; 10% faster ≈ +10 points. Your tempo: "
                       + rows + ".")
        sl = p.skills.get("sliders") or {}
        if sl.get("score") is not None:
            st.caption("**Slider control** counts how hard the sliders are that you follow to the end: speed, "
                       "length, shape (curves, corners, S-bends), speed changes and how soon the next note "
                       "follows. Per map your 30 hardest sliders count, and breaking some of them costs a lot; "
                       "many short, slow sliders don't add up to a few hard ones.")
    with right:
        section("Strengths & weaknesses", "Your three best skills (score ≥ 55) and up to three to work on (≤ 45).")
        strong = [p.skills[k]["label"] for k in p.strengths]
        weak = [p.skills[k]["label"] for k in p.weaknesses]
        st.markdown("**Strong:** " + (", ".join(strong) or "not clear yet"))
        st.markdown("**Work on:** " + (", ".join(weak) or "not clear yet"))
        mb = p.miss_breakdown
        if mb:
            section("Why you miss", "Share of your misses by cause (weighted by difficulty). Aim = jumps and single "
                                    "notes; speed-aim = tapped in time but the cursor couldn't keep up in a stream, "
                                    "burst or very fast jump; the others are tapping / reading misses. Hover a bar for "
                                    "the exact meaning.")
            total = sum(mb.values()) or 1
            raw = getattr(p, "miss_breakdown_raw", {}) or {}
            items = sorted(mb.items(), key=lambda kv: kv[1])
            fig = go.Figure(go.Bar(x=[v / total * 100 for _, v in items], y=[MISS_SHORT.get(k, k) for k, _ in items],
                                   orientation="h", marker_color=ACCENT,
                                   text=[f"{v / total:.0%}" for _, v in items], textposition="outside",
                                   hovertext=[f"{MISS_LABELS.get(k, k)}<br>{raw.get(k, 0)} misses (unweighted)"
                                              for k, _ in items], hoverinfo="text"))
            fig.update_xaxes(title="% of misses", range=[0, max(v for _, v in items) / total * 118])
            plot(style(fig, 270))
            split = (p.aim or {}).get("split") or {}
            a, f = split.get("aim"), split.get("speed_aim")
            if a and f and a["expected"] > 0 and f["expected"] > 0:
                st.caption(f"Against what the difficulty predicts: on fast patterns you miss "
                           f"{f['all_misses'] / f['expected']:.1f}× the expected, on normal-speed jumps and notes "
                           f"{a['all_misses'] / a['expected']:.1f}× (1.0× = as expected for your level).")
    tips = make_tips(p, setup_from_settings())
    section("Top tips", "The three most important tips; all of them are on **Tips & Setup**.")
    cols = st.columns(3)
    top = [t for t in tips if not t.title.endswith("fits")]      # "keep your setup" isn't a top tip
    for col, t in zip(cols, top[:3]):
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
    page_title("Progress", "Every analysis is saved here, month by month (progress.sqlite in the osu! coach data folder). "
                           "The history stays even if you delete replays later. These numbers are not weighted by "
                           "difficulty, so months stay comparable.")
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
        chart(style(fig, 380, "Star rating by month", legend=True),
              "One point per month. Comfort = the star rating 75% of your clean plays stay under; hardest clean "
              "pass / full combo = the hardest map finished with ≤ 5 misses per 100 notes / without a miss. Hollow "
              "points: fewer than 5 plays that month.")
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
            chart(style(fig, 400, "Skills by month", legend=True),
                  "50 = your all-time average at the same difficulty; higher = fewer misses than usual that month. "
                  "Pick skills with the buttons above. Hollow points: fewer than 5 plays that month.")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=x, y=m["plays"], name="plays", marker_color=ACCENT))
        fig.add_trace(go.Bar(x=x, y=m["new_maps"], name="new maps", marker_color=INFO))
        fig.add_trace(go.Scatter(x=x, y=m["minutes"], name="minutes played", yaxis="y2", mode="lines+markers",
                                 line=dict(color=GOOD)))
        fig.update_xaxes(type="category")
        fig.update_layout(barmode="group", yaxis2=dict(overlaying="y", side="right", showgrid=False, title="minutes",
                                                       rangemode="tozero", tickformat=".0f"))
        fig.update_yaxes(rangemode="tozero")
        chart(style(fig, 340, "What you played", legend=True),
              "Bars: plays and maps played for the first time each month (left axis); line: minutes played "
              "(right axis).")
        section("Plays of one month", "Every play saved for the month you pick: result, accuracy and misses.")
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
        "Mods": plays["mods"].fillna("").replace("", "NM"), "Difficulty": plays["stars"],
        "Accuracy": plays["accuracy"] * 100,
        "Misses": plays["nmiss"], "Combo": [f"{c:.0f}/{mc:.0f}" if not isnan(mc) else f"{c:.0f}"
                                            for c, mc in zip(plays["max_combo"], plays["map_max_combo"])],
        "Result": result,
    }), hide_index=True, column_config={"Difficulty": st.column_config.NumberColumn(format="%.2f ★",
                                                                                     help=DIFFICULTY_HELP),
                                        "Accuracy": st.column_config.NumberColumn(format="%.2f%%")})


# ------------------------------------------------------------------ Aim
def page_aim():
    p = need_profile()
    page_title("Aim", "Where and how your aim misses: by screen area, jump direction and distance, where your clicks "
                      "land, and how your movement compares with the jumps (aim calibration).")
    a, reg, wq = p.aim, p.regression, p.worst_quadrant
    P = played(p)
    c = st.columns(4)
    c[0].metric("Aim misses", pct(a.get("aim_miss_share"), 0),
                help="Share of your misses where you tapped in time but outside the circle, on jumps and single "
                     f"notes. Another {pct(a.get('speed_aim_miss_share'), 0)} are speed-aim misses (in streams, "
                     "bursts and very fast jumps).")
    c[1].metric("Jump miss rate", pct(a.get("jump_miss_rate")))
    c[2].metric("Near misses", pct(a.get("near_miss_share"), 0), help="Aim misses that landed within 1.4 radii — "
                                                                      "just outside the circle.")
    c[3].metric("Jump distance error", fmt(a.get("jump_along_pct"), "+.1f", "%"),
                help="Median over/undershoot along the jump direction, as % of the jump length.")
    if wq:
        txt = (f"Weakest quadrant: **{wq['quadrant']}** — {pct(wq['miss_rate'])} misses vs {pct(wq['rest_miss_rate'])} "
               f"elsewhere ({wq['relative_risk']:.1f}×).")
        if wq["significant"]:
            st.warning(txt + " See **Tips & Setup** for how to fix it.", icon=":material/target:")
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
                                   colorscale=[[0, HEAT_LOW], [1, ACCENT]], showscale=False, hoverinfo="skip"))
        fig.update_yaxes(autorange="reversed")
        chart(style(fig, 300, "Miss rate by screen quadrant"),
              "The playfield cut into four. Each cell: share of the notes there you missed, and misses / notes. "
              "Darker pink = more misses.")
    with right:
        bins_x, bins_y = np.linspace(0, 512, 9), np.linspace(0, 384, 7)
        allh, _, _ = np.histogram2d(P["x"].clip(0, 511.9), P["y"].clip(0, 383.9), bins=[bins_x, bins_y],
                                    weights=weights(P))
        M = P[~P["head_hit"]]
        mh, _, _ = np.histogram2d(M["x"].clip(0, 511.9), M["y"].clip(0, 383.9), bins=[bins_x, bins_y],
                                  weights=weights(M))
        rate = np.where(allh >= 15, mh / np.maximum(allh, 1) * 100, np.nan)
        fig = go.Figure(go.Heatmap(z=rate.T, x=(bins_x[:-1] + bins_x[1:]) / 2, y=(bins_y[:-1] + bins_y[1:]) / 2,
                                   colorscale=[[0, HEAT_LOW], [1, ACCENT]], showscale=False,
                                   hovertemplate="miss rate %{z:.1f}%<extra></extra>"))
        fig.add_shape(type="line", x0=256, x1=256, y0=0, y1=384, line=dict(color=MUTED, dash="dot"))
        fig.add_shape(type="line", x0=0, x1=512, y0=192, y1=192, line=dict(color=MUTED, dash="dot"))
        fig.update_xaxes(range=[0, 512], showticklabels=False)
        fig.update_yaxes(range=[384, 0], showticklabels=False, scaleanchor="x")
        chart(style(fig, 300, "Where on the playfield you miss"),
              "A finer grid of the playfield as you see it: the pinker a cell, the more of its notes you missed. "
              "Empty cells: too few notes there.")
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
        chart(style(fig, 360, "Miss rate by jump direction").update_layout(margin=dict(l=40, r=40, t=60, b=40)),
              "Each wedge is a direction the cursor moves in to reach the note (jumps of 1+ circle). The longer "
              "the wedge, the more of those jumps you missed.")
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
        chart(style(fig, 320, "By jump distance"),
              "Bars: miss rate by how far the note is from the previous one (in circle diameters). Line: how far "
              "past (+) or short of (−) the note you click, in circle radii.")
    with right:
        section("Aim calibration", "Your actual cursor movement compared with the movement each jump needed. 0% = "
                                   "exact; + = you move too far. This drives the tablet area / sensitivity tip on "
                                   "Tips & Setup.")
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
            section("By angle between jumps", "Sharp = back-and-forth jumps, wide = jumps that keep going in one "
                                              "direction. Notes are weighted by difficulty.")
            st.dataframe(pd.DataFrame({"Angle between jumps": ang["abin"].astype(str),
                                       "Notes": ang["objects"].round(0), "Miss rate": (ang["miss_rate"] * 100).round(1)}),
                         hide_index=True, column_config={
                             "Notes": st.column_config.NumberColumn(format="%d"),
                             "Miss rate": st.column_config.NumberColumn(format="%.1f%%")})


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
    # plays far from your level are drawn less often, like they count less (weighted sample without replacement:
    # the N largest u^(1/w))
    if len(C) > CLICKS_DRAWN:
        w = C["w"].to_numpy(float) if "w" in C else np.ones(len(C))
        keys = np.log(np.random.default_rng(0).random(len(C))) / np.maximum(w, 1e-12)
        drawn = C.iloc[np.sort(np.argsort(keys)[-CLICKS_DRAWN:])]
    else:
        drawn = C
    drawn = drawn[(drawn["x"].abs() < 2.4) & (drawn["y"].abs() < 2.4)]
    hits, misses = drawn[drawn["hit"]], drawn[~drawn["hit"]]
    few = len(drawn) <= 300                      # one short play: bigger, stronger dots
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hits["x"], y=hits["y"], mode="markers", name="hit", hoverinfo="skip",
                             marker=dict(size=7 if few else 3, color=ACCENT, opacity=0.75 if few else 0.35)))
    fig.add_trace(go.Scatter(x=misses["x"], y=misses["y"], mode="markers", name="aim miss", hoverinfo="skip",
                             marker=dict(size=8 if few else 5, color=MISS_COLOR, opacity=0.9)))
    fig.add_shape(type="circle", x0=-1, y0=-1, x1=1, y1=1, line=dict(color=MUTED, width=2))
    fig.add_shape(type="circle", x0=-0.5, y0=-0.5, x1=0.5, y1=0.5, line=dict(color=MUTED, width=1, dash="dot"))
    mx, my = s["mean_r"]
    fig.add_trace(go.Scatter(x=[mx], y=[my], mode="markers", name="average", hoverinfo="skip",
                             marker=dict(color=INFO, size=13, symbol="x", line=dict(color="#24242e", width=1))))
    fig.update_xaxes(range=[-2.4, 2.4], zeroline=False, constrain="domain",
                     title="circle radii" + (" · overshoot →" if view == "movement" else ""))
    fig.update_yaxes(range=[2.4, -2.4], zeroline=False, scaleanchor="x", scaleratio=1, constrain="domain")
    title = ("Where your clicks land — on screen" if view == "screen"
             else "Where your clicks land — jumps, turned so you move right")
    fig = style(fig, 430, title, legend=True)
    fig.update_layout(legend=dict(y=-0.2))       # below the axis title
    plot(fig)
    bands = " · ".join(f"{share * 100:.0f}% {label}" if label != "outside"
                       else f"{share * 100:.1f}% outside (aim misses)" for label, share in s["bands"].items())
    if view == "screen":
        (ox, oy), r = s["mean_px"], s["radius"]
        where = f"{abs(ox):.1f} px {'left' if ox < 0 else 'right'} and {abs(oy):.1f} px {'above' if oy < 0 else 'below'}"
        drawn_txt = (f"{s['n']:,} clicks" if s["n"] <= CLICKS_DRAWN else
                     f"{CLICKS_DRAWN:,} picked at random from {s['n']:,}, so the share of yellow dots is the real one")
        st.caption(f"Each dot is one click ({drawn_txt}). Average of all clicks: {where} the "
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
GROUP_COLORS = {"16–31 notes": GOOD, "32–63 notes": INFO, "64+ notes": ACCENT}


def fall_behind_chart(p):
    """Precision (average absolute timing error) by note number inside long streams, per stream length;
    where it starts to fall apart, the comfortable stream length and maps to practise it."""
    fb = getattr(p, "fall_behind", None) or {}
    curves = fb.get("curves")
    if curves is None or len(curves) < 3 or "abs_err" not in curves:
        section("Stamina in long streams", "Streams of 16+ notes: not enough of them in these replays yet.")
        return
    section("Stamina in long streams", "How precise your taps stay from the first note of a long stream to the last. "
                                       "Tired fingers scatter: the error grows as the stream goes on.")
    left, right = st.columns([3, 2], gap="large")
    with left:
        fig = go.Figure()
        for label, g in curves.groupby("group", sort=False):
            fig.add_trace(go.Scatter(
                x=g["pos"], y=g["abs_err"], mode="lines+markers", name=label,
                line=dict(color=GROUP_COLORS.get(label, ACCENT), width=2.5), marker=dict(size=6),
                hovertext=[f"{label}, notes {int(x)}–{int(x) + 3}: {a:.1f} ms off on average ({e:+.1f} ms early/late), "
                           f"{m:.1%} missed, {int(n)} hits" for x, a, e, m, n in
                           zip(g["pos"], g["abs_err"], g["err"], g["miss_rate"], g["n"])], hoverinfo="text"))
        start = fb.get("start_note")
        if start:
            fig.add_vline(x=start, line_color=BAD, line_dash="dot")
        fig.update_xaxes(title="note number inside the stream", rangemode="tozero")
        fig.update_yaxes(title="average error (ms, early or late)", rangemode="tozero")
        chart(style(fig, 360, "Precision through long streams", legend=True),
              "Each line is one stream length; each point = the notes 1–4, 5–8, … of those streams. Height = how far "
              "off your taps were on average, early or late alike (+10 and −10 both count as 10 ms — the plain "
              "average would cancel them out to ~0). Flat = your stamina holds; a line that climbs = your taps "
              "scatter more the longer the stream goes. Only streams up to your clean stream speed + 10 BPM count."
              + (" Red line: where it starts." if start else ""))
    with right:
        bpm = fb.get("bpm")
        at = f" at ~{bpm:.0f} BPM" if bpm else ""
        if start:
            secs = f" (≈ {fb['start_seconds']:.1f} s{at})" if fb.get("start_seconds") is not None else at
            st.markdown(f"**Your stamina gives in after about {start} notes**{secs}: your taps are "
                        f"{fb['base_ms']:.0f} ms off on average before that and ≈ {fb['base_ms'] + fb['growth_ms']:.0f} "
                        f"ms by note {int(fb['curve']['pos'].max())}.")
        else:
            st.markdown(f"**Your precision holds** through the streams measured — up to "
                        f"{fb.get('comfort_notes')} notes{at} ({fb.get('streams', 0)} streams of 16+ notes). "
                        "No point where it clearly gets worse.")
        lo, hi = fb.get("practice_notes") or (None, None)
        comfort = fb.get("comfort_notes")
        if comfort and lo:
            st.markdown(f"- **Comfortable:** streams up to **{comfort} notes** — warm up with these.\n"
                        f"- **Stamina practice:** streams of **{lo}–{hi} notes**, where your stamina "
                        f"{'starts to get in the way' if start else 'hasn’t been tested yet'}. Play them a little "
                        "below your top speed and lengthen them step by step.")
        if comfort and lo:
            stream_length_suggestions(p, comfort, lo, hi)


def stream_length_suggestions(p, comfort: int, lo: int, hi: int):
    pool = pool_cached()
    if pool.empty:
        return
    t = targets_from_profile(p)
    easy = stream_length_maps(pool, t, max(9, int(comfort * 0.6)), comfort, n=5)
    push = stream_length_maps(pool, t, lo, hi, n=5)
    tabs = st.tabs([f"Maps: comfortable ({max(9, int(comfort * 0.6))}–{comfort} notes)",
                    f"Maps: stamina practice ({lo}–{hi} notes)"])
    with tabs[0]:
        maps_table(easy)
    with tabs[1]:
        maps_table(push)


def page_tapping():
    p = need_profile()
    page_title("Tapping", "How you tap: timing spread and bias, how fast you can stream, whether you fall behind in "
                          "long streams, and how you use your keys.")
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
        H = P[P["head_hit"]].dropna(subset=["err_real"])
        H = H[H["err_real"].abs() <= 150]
        edges = np.arange(-150, 153, 3)
        fig = go.Figure()
        for res, name in ((300, "300"), (100, "100"), (50, "50")):
            sel = H["head_result"] == res
            counts, _ = np.histogram(H.loc[sel, "err_real"], bins=edges, weights=weights(H[sel]))
            fig.add_trace(go.Bar(x=(edges[:-1] + edges[1:]) / 2, y=counts, name=name, marker_color=RESULT_COLORS[res],
                                 marker_line_width=0, hovertemplate=f"{name}: %{{y:.0f}} hits at %{{x:+.0f}} ms"
                                                                    "<extra></extra>"))
        fig.update_layout(bargap=0, barmode="stack")
        fig.add_vline(x=0, line_color=MUTED)
        if len(H):
            fig.add_vline(x=float(np.average(H["err_real"], weights=weights(H))), line_color=ACCENT, line_dash="dot")
        fig.update_xaxes(title="hit error (ms, real time) · early ← → late")
        fig.update_yaxes(title="hits (weighted)")
        shares = {r: float(weights(H[H["head_result"] == r]).sum()) for r in (300, 100, 50)}
        tot = sum(shares.values()) or 1.0
        if st.toggle("Log scale", key="timing_log", help="Makes the few 100s and 50s at the edges easier to see."):
            fig.update_yaxes(type="log", title="hits (weighted, log scale)")
        chart(style(fig, 340, "Hit timing", legend=True),
              "How early or late each hit was, coloured by what it scored: green = 300, blue = 100, orange = 50 "
              f"({shares[300] / tot:.0%} / {shares[100] / tot:.0%} / {shares[50] / tot:.1%} of hits). A narrow "
              "green peak = steady timing (low UR); the dotted line is your average — left of 0 = you tap early, "
              "right = late. The edges between the colours move with OD and speed mods, so they overlap a little.")
    with right:
        sp = p.stream_profile
        if sp is None or sp.empty:
            section("Stream speed", "Not enough streams (7+ notes in a row) in your replays yet.")
        else:
            tap = sp["tap_miss_rate"] if "tap_miss_rate" in sp else sp["miss_rate"]
            aim = sp["speed_aim_rate"] if "speed_aim_rate" in sp else 0 * sp["miss_rate"]
            hover = [f"{n:.0f} notes (weighted)" for n in sp["objects"]]
            fig = go.Figure()
            fig.add_trace(go.Bar(x=sp["bpm_bin"], y=tap * 100, marker_color=ACCENT, name="tapping misses",
                                 hovertext=hover, hoverinfo="text+y"))
            fig.add_trace(go.Bar(x=sp["bpm_bin"], y=aim * 100, marker_color=MISS_COLOR, name="speed-aim misses",
                                 hovertext=hover, hoverinfo="text+y"))
            plays = sp["ur_plays"] if "ur_plays" in sp else pd.Series(0, index=sp.index)
            fig.add_trace(go.Scatter(
                x=sp["bpm_bin"], y=sp["ur"], yaxis="y2", mode="lines+markers", name="UR (typical play)",
                line=dict(color=INFO, width=2.5),
                marker=dict(size=[12 if wk else 7 for wk in (sp["weak"] if "weak" in sp else [False] * len(sp))],
                            color=[BAD if wk else INFO for wk in (sp["weak"] if "weak" in sp else [False] * len(sp))]),
                hovertext=[f"{b}–{b + 9} BPM: UR {u:.0f} (median of {int(n)} plays)" if n else
                           f"{b}–{b + 9} BPM: UR {u:.0f} (all hits together)" for b, u, n in
                           zip(sp["bpm_bin"], sp["ur"], plays)], hoverinfo="text"))
            if "ur_best" in sp and sp["ur_best"].notna().any():
                fig.add_trace(go.Scatter(x=sp["bpm_bin"], y=sp["ur_best"], yaxis="y2", mode="markers",
                                         name="UR (best play)", marker=dict(color=INFO, symbol="triangle-down", size=8,
                                                                            opacity=0.6),
                                         hovertemplate="best play: UR %{y:.0f}<extra></extra>"))
            if "ur_trend" in sp and sp["ur_trend"].notna().any():
                fig.add_trace(go.Scatter(x=sp["bpm_bin"], y=sp["ur_trend"], yaxis="y2", mode="lines",
                                         name="UR trend", line=dict(color=MUTED, dash="dash"), hoverinfo="skip"))
            fig.update_layout(barmode="stack", yaxis=dict(title="miss rate %"),
                              yaxis2=dict(title="UR", overlaying="y", side="right", showgrid=False))
            fig.update_xaxes(title="stream speed (BPM, 1/4 notes)")
            if t.get("comfort_bpm"):
                fig.add_vline(x=t["comfort_bpm"] + 5, line_color=GOOD, line_dash="dot")
            if t.get("limit_bpm"):
                fig.add_vline(x=t["limit_bpm"] + 5, line_color=BAD, line_dash="dot")
            fig = style(fig, 360, "Stream speed", legend=True)
            fig.update_layout(legend=dict(y=-0.3), margin=dict(b=40))
            limit = (f"tapping breaks down from ≈ {t['limit_bpm']} BPM (red line)" if t.get("limit_bpm")
                     else "no clear breakdown speed in these replays")
            weak = [int(b) for b in sp.loc[sp["weak"].astype(bool), "bpm_bin"]] if "weak" in sp else []
            weak_txt = (" **Weak spots** (UR clearly above the trend, big red dots): "
                        + ", ".join(f"{b}–{b + 9}" for b in weak) + " BPM — practise streams at exactly those speeds."
                        if weak else " No BPM sticks out above the trend.")
            chart(fig, f"Streams of 7+ notes by speed. Pink = misses of the fingers (no tap, too early / late), "
                       f"yellow = the cursor fell behind (speed-aim). Your stream speed is judged on the pink part "
                       f"only: clean up to ≈ {fmt(t.get('comfort_bpm'), 'd')} BPM (green line) · {limit}. Blue "
                       "line: UR at that speed, measured in each play on its own and the middle play taken (all "
                       "plays thrown together give a higher, misleading UR); triangles = your best play there. The "
                       "dashed line is the UR you'd expect from your other speeds — it rises with BPM." + weak_txt)
    fall_behind_chart(p)
    left, right = st.columns(2, gap="large")
    with left:
        shares = t.get("key_share") or {}
        if shares:
            keys = sorted(shares)
            fig = go.Figure(go.Bar(x=keys, y=[shares[k] * 100 for k in keys], marker_color=ACCENT))
            fig.update_yaxes(title="% of presses")
            chart(style(fig, 300, "Keys used"),
                  "Share of your key presses per key: K = keyboard, M = mouse/pen buttons"
                  + (", L/R = lazer left/right" if {"L", "R"} & set(keys) else "")
                  + ". Even bars = you use both fingers.")
            if {"L", "R"} & set(keys):
                st.caption("lazer replays only store left/right, not whether a key or a mouse/pen button was used.")
        Pr = p.presses
        if Pr is not None and len(Pr):
            rates = dict(zip(p.replays["key"], p.replays["rate"]))
            dur = (Pr["duration"] / Pr["replay_key"].map(rates).fillna(1.0)).dropna()
            st.caption(f"Typical key hold: {fmt(dur.median(), '.0f')} ms · in streams "
                       f"{fmt(t.get('press_ms_streams'), '.0f')} ms · chatter {fmt(t.get('chatter_per_1000'), '.1f')} "
                       "per 1000 presses")


# ------------------------------------------------------------------ Sliders & Reading
def page_sliders_reading():
    p = need_profile()
    page_title("Sliders & Reading", "Slider control (heads, breaks, ends) and reading: how approach rate and dense parts "
                                    "change your misses, and how you handle misses and the end of maps.")
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
            chart(style(fig, 240, "Why sliders break"),
                  "Sliders you hit at the head but broke later, by reason (weighted count).")
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
            chart(style(fig, 240, "Misses by approach rate"),
                  "Miss rate by AR (with mods; DT raises it). Higher AR maps are usually harder too — the Reading "
                  "tips compare with what the difficulty predicts.")
    section("Reading and consistency", "Miss rates in dense parts (many notes on screen) vs the rest, and whether "
                                       "misses cause more misses or pile up at the end of maps.")
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
    st.markdown("**Tablet area to try** — OpenTabletDriver values; X / Y = the centre of the area")
    st.dataframe(pd.DataFrame({"Setting": [r[0] for r in rows], "Now (mm)": [mm(a["now"][k]) for _, k in rows],
                               "Try (mm)": [mm(a[k]) for _, k in rows]}), hide_index=True)
    why = "; ".join(a["why"])
    st.caption(why[0].upper() + why[1:] + "." + ("" if a["now"]["x"] is not None and a["now"]["y"] is not None
                                                 else " Enter X / Y in your setup to get the position too."))


def calibration_box(p, s: Setup):
    """The aim calibration of the Aim page turned into a setup change (tablet area or sensitivity)."""
    c = aim_calibration(p, s)
    with st.container(border=True):
        section("Aim calibration → your setup", "From the Aim page: how far you move compared with the jumps. Over "
                                                 "4% too far or too short means the tablet area / sensitivity should "
                                                 "change; within ±4% keep it.")
        if not c:
            st.caption("Not enough jumps yet (needs 40+).")
            return
        cols = st.columns(3)
        cols[0].metric("Movement vs jumps", f"{(c['scale'] - 1) * 100:+.1f}%",
                       help="+ = you move too far (overaim), − = not far enough (underaim).")
        change = ("keep" if not c["step"] else f"{c['step'] * 100:+.0f}% area" if c["device"] == "tablet"
                  else f"{(1 / c['scale'] - 1) * 100:+.0f}% sensitivity")
        cols[1].metric("Change", change, help="Tablet: + = larger area (less sensitive). Mouse: − = lower "
                                              "sensitivity.")
        if c["now"]:
            cols[2].metric("Try", c["try"], help=f"Now: {c['now']}")
        st.markdown("\n".join(f"- {line}" for line in c["lines"]))
        area = suggest_tablet_area(p, s)
        if area:
            tablet_area_box(area)


def sayo_table(r: dict):
    def show(v):
        return ("on" if v else "off") if isinstance(v, bool) else f"{v:.2f} mm"
    names = list(r["now"])
    table = pd.DataFrame({"Setting": names, "Now": [show(r["now"][k]) for k in names],
                          "Try": [show(r["new"][k]) + ("  ← change" if r["new"][k] != r["now"][k] else "")
                                  for k in names]})
    st.dataframe(table, hide_index=True)


def page_tips():
    p = need_profile()
    page_title("Tips & Setup", "Concrete tips from your numbers, most important first — each with the evidence it is based "
                               "on — and setup changes to try (tablet area / sensitivity, keys).")
    sett = settings()
    with st.expander("Your setup — makes the tips concrete (tablet area, sensitivity, keyboard / SayoDevice)",
                     expanded=not sett.get("setup_saved"), icon=":material/tune:"):
        setup_editor(sett, setup_from_settings())
    s = setup_from_settings()
    calibration_box(p, s)
    tips = make_tips(p, s)
    section("Tips", "Red = biggest impact, orange = medium, grey = nice to know.")
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
    section("Practice plan", "A simple daily routine built around your weakest skills.")
    st.markdown("\n".join(f"{i}. {step}" for i, step in enumerate(practice_plan(p), 1)))


# ------------------------------------------------------------------ Maps
def page_maps():
    p = need_profile()
    pool = pool_cached()
    t = targets_from_profile(p)
    page_title("Map Suggestion", f"Maps to practise your weakest skills, picked from {len(pool):,} popular ranked maps "
                                 f"around your level ({t.comfort:.1f}★). Maps you already played are left out. Each "
                                 "table: Difficulty = star rating, Detail description = why the map fits. For a full "
                                 "staged playlist of one skill use **Skill Development**.")
    if pool.empty:
        st.error("The bundled map pool is missing.")
        return
    recs = recommendations(pool, p, per_skill=5)
    for sk, df in recs:
        if sk == "general":
            name, why = "Level up", "Slightly above your level, popular maps."
        elif sk == "quadrant":
            name, why = skill_label(sk, t), "Jumps that land in your weakest quadrant."
        else:
            sc = p.skills.get(sk, {}).get("score")
            name, why = skill_label(sk, t), f"One of your weakest skills (score {fmt(sc, '.0f')} of 100)."
        section(name, why)
        maps_table(df)
    if not recs:
        return
    pl = pd.concat([df.assign(stage=skill_label(sk, t)) for sk, df in recs], ignore_index=True)
    name = f"osu-coach: Map Suggestion ({t.comfort:.1f}★)"
    section("Get all these maps into osu!", f"All {len(pl)} suggested maps at once, as the collection “{name}”.")
    playlist_export(pl, name, "suggestions")


# ------------------------------------------------------------------ Skill Development
def page_improve():
    page_title("Skill Development", "A staged playlist (warm-up / core / push) for one skill at your level, and one "
                                    "click to get it into osu!.")
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
        section(stage, part["goal"].iloc[0])
        maps_table(part)
    section("Get the playlist into osu!", "lazer: one folder to import maps and collection; stable: add the "
                                          "collection and download the maps.")
    playlist_export(pl, name, skill)


def playlist_export(pl: pd.DataFrame, name: str, folder: str):
    """lazer import folder / stable collection + .osz downloads / map list, for any list of pool maps."""
    hashes = list(pl["md5"])
    text = "\n".join(f"[{r.stage}] {r.stars:.2f}* {r.artist} - {r.title} [{r.version}]  {r.url}"
                     for r in pl.itertuples())
    order = ["osu!lazer", "osu!stable"] if preferred_client() == "lazer" else ["osu!stable", "osu!lazer"]
    tabs = dict(zip(order, st.tabs(order)))
    with tabs["osu!lazer"]:
        lazer_import_ui(pl, name, hashes, key=folder)
    with tabs["osu!stable"]:
        stable_import_ui(pl, name, hashes, folder)
    st.download_button("Map list with links (.txt)", data=f"{name}\n\n{text}\n", file_name="playlist.txt",
                       mime="text/plain", icon=":material/list:", key=f"maplist::{folder}")


def lazer_import_ui(pl: pd.DataFrame, name: str, hashes: list[str], key: str = ""):
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
    if c[0].button("Make lazer import folder", type="primary", icon=":material/create_new_folder:",
                   key=f"lazer_pack::{key}"):
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
                         icon=":material/folder_zip:", key=f"lazer_zip::{key}",
                         help="Just the collection, e.g. for lazer on another computer: unzip it and import the "
                              "folder the same way. Get the maps from the links.")
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(lazer_import.INSTRUCTIONS, 1))
    st.markdown(f"**Then, in lazer:**\n\n{steps}")


def stable_import_ui(pl: pd.DataFrame, name: str, hashes: list[str], skill: str):
    c = st.columns(2)
    c[0].download_button("collection.db", data=collection_bytes({name: hashes}), file_name="collection.db",
                         mime="application/octet-stream", icon=":material/download:", key=f"coll::{skill}",
                         help="A collection file with this playlist, e.g. for Collection Manager.")
    stable = [i for i in installs_cached() if i.kind == "stable"]
    if stable and c[1].button("Add to my osu!stable collections", icon=":material/library_add:", key=f"merge::{skill}"):
        if locate.is_osu_running():
            st.error("Close osu! first — it rewrites collection.db when it exits.")
        else:
            res = merge_into(stable[0].root / "collection.db", {name: hashes})
            st.success(f"Added “{name}” to {res['path']} (backup: {res['backup'] or 'none needed'}).")
    default_dest = stable[0].songs if stable and stable[0].songs else Path.home() / "osu-coach-maps" / skill
    dest = st.text_input("Download the maps (.osz) to", value=str(default_dest), key=f"osz_dest::{skill}",
                         help="osu!stable picks up .osz files in its Songs folder on the next start (or F5 in song "
                              "select).")
    if st.button(f"Download all {pl['beatmapset_id'].nunique()} maps", icon=":material/cloud_download:",
                 key=f"osz::{skill}"):
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
    "Sliders & Reading": page_sliders_reading, "Tips & Setup": page_tips, "Map Suggestion": page_maps,
    "Progress": page_progress, CHECK_PAGE: page_check,
    "Skill Development": page_improve,
}[page]()

# filled in last, so it is already up to date in the run that finished an analysis
if profile() is not None:
    _p = profile()
    _ov, _lv = _p.overview, _p.levels
    _set = "best replays" if st.session_state.get("analyses") and settings().get("replay_set") == "best" else "replays"
    sidebar_status.caption(f"{st.session_state.get('player_label', '')} · {_ov['replays']} {_set} · "
                           f"{_ov['objects']:,} notes · level {fmt(_lv.get('level_stars'), '.2f', '★')}")
else:
    sidebar_status.caption("Start on the Replays page.")
