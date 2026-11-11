import { useCallback, useState } from "react";

import type { Schemas } from "../api/client";
import type { RecommendationOptions } from "../components/RecommendationControls";

/** How many maps of a playlist stage are shown (and exported) at a time. */
export const STAGE_SIZE = 5;

/** The ``round``-th group of ``size`` maps of a ranked list, starting over after the last one (that group may be
 * shorter); ``first`` is the 0-based index of its first map. */
export function stageMaps<T>(maps: T[], round: number, size = STAGE_SIZE): { maps: T[]; first: number } {
  if (!maps.length) return { maps: [], first: 0 };
  const groups = Math.ceil(maps.length / size);
  const first = (((round % groups) + groups) % groups) * size;
  return { maps: maps.slice(first, first + size), first };
}

/** How many of a stage's most recent groups Back can return to, the one on screen included. */
export const HISTORY = 20;

/** The groups a stage has shown: ``at`` is the one on screen, ``latest`` the newest one Other maps brought up. */
export interface Rounds {
  at: number;
  latest: number;
}

export const FIRST_ROUND: Rounds = { at: 0, latest: 0 };

export const canGoBack = (r: Rounds) => r.at > Math.max(0, r.latest - HISTORY + 1);
export const canGoForward = (r: Rounds) => r.at < r.latest;

/** Back and Forward step through the last ``HISTORY`` groups; Other maps always brings up a new one after the newest. */
export function moveRound(r: Rounds, to: "back" | "forward" | "other"): Rounds {
  if (to === "back") return canGoBack(r) ? { ...r, at: r.at - 1 } : r;
  if (to === "forward") return canGoForward(r) ? { ...r, at: r.at + 1 } : r;
  return { at: r.latest + 1, latest: r.latest + 1 };
}

const NONE: Record<string, Rounds> = {};

/** Each stage's ``Rounds`` by its name, all back to the first group when ``of`` changes (a new playlist), or to the
 * ``saved`` ones when they belong to the new ``of`` (a playlist left and come back to). ``by`` is what to keep. */
export function useRounds(of: unknown, saved?: { of: unknown; by: Record<string, Rounds> }) {
  const start = (o: unknown) => ({ of: o, by: saved && o !== null && saved.of === o ? saved.by : {} });
  const [state, setState] = useState<{ of: unknown; by: Record<string, Rounds> }>(() => start(of));
  if (state.of !== of) setState(start(of));
  const by = state.of === of ? state.by : NONE;
  const rounds = useCallback((stage: string) => by[stage] ?? FIRST_ROUND, [by]);
  const move = useCallback(
    (stage: string, to: "back" | "forward" | "other") =>
      setState((s) => ({ ...s, by: { ...s.by, [stage]: moveRound(s.by[stage] ?? FIRST_ROUND, to) } })),
    [],
  );
  return { rounds, move, by };
}

/** The figures the practice-target controls start from: the skill shown first, the measured ratings, comfort. */
export interface PlaylistControls {
  skill: string;
  measured: Record<string, number>;
  comfort: number;
}

/** The Playlist for a skill tab as it was left, so another tab or page and back shows the same playlist (#107): the
 * selection applied, the figures its controls started from, the search behind a playlist with mods, the playlist
 * itself (its maps stay until Show maps asks for new ones), the group of five each stage shows for the playlist
 * ``maps`` names, and ``done``: its maps checked as completed. Kept also when osu! coach is started again; the
 * checked maps leave the playlist then. */
export interface SavedPlaylist {
  options: RecommendationOptions;
  controls: PlaylistControls | null;
  job: string | null;
  playlist: Schemas["Playlist"] | null;
  maps: string | null;
  rounds: Record<string, Rounds>;
  done: string[];
}

const SAVED = "osu-coach:skill-playlist";
/** Set in the session storage once this session has taken the checked maps out of the saved playlist. */
const SESSION = "osu-coach:skill-playlist-session";
export const NO_PLAYLIST: SavedPlaylist = {
  options: {}, controls: null, job: null, playlist: null, maps: null, rounds: {}, done: [],
};

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isRounds = (v: unknown): v is Rounds => isRecord(v) && Number.isInteger(v.at) && Number.isInteger(v.latest);
const roundsOf = (v: unknown): Record<string, Rounds> =>
  Object.fromEntries(isRecord(v) ? Object.entries(v).filter((e): e is [string, Rounds] => isRounds(e[1])) : []);

function load(name: string, storage: Pick<Storage, "getItem">): unknown {
  try {
    return JSON.parse(storage.getItem(name) ?? "null");
  } catch {
    return null; // storage blocked or garbled: start as new
  }
}

/** Keeps ``value``; one too big for the storage is kept ``smaller`` instead, never left at an older value. */
function keep(name: string, value: unknown, smaller: unknown, storage: Pick<Storage, "setItem">) {
  try {
    storage.setItem(name, JSON.stringify(value));
  } catch {
    try {
      storage.setItem(name, JSON.stringify(smaller));
    } catch {
      /* a convenience only */
    }
  }
}

type Session = Pick<Storage, "getItem" | "setItem">;

/** The playlist as it was left. In a new session (osu! coach started again) the maps checked as completed leave it
 * (unless played maps were asked for), and the rest stays where it was. */
export function loadPlaylist(storage: Pick<Storage, "getItem"> = localStorage, session: Session = sessionStorage): SavedPlaylist {
  const saved = readPlaylist(storage);
  let started: boolean;
  try {
    started = session.getItem(SESSION) !== null;
    session.setItem(SESSION, "1");
  } catch {
    started = true; // no session storage: keep the checks rather than lose maps on every visit
  }
  if (started || !saved.done.length || !saved.playlist || saved.options.exclude_played === false) return saved;
  const done = new Set(saved.done);
  const playlist = { ...saved.playlist, stages: saved.playlist.stages.map((st) => ({ ...st, maps: st.maps.filter((m) => !done.has(m.md5)) })) };
  return { ...saved, playlist, maps: playlistKey(playlist), done: [] };
}

function readPlaylist(storage: Pick<Storage, "getItem">): SavedPlaylist {
  const v = load(SAVED, storage);
  if (!isRecord(v) || !isRecord(v.options)) return NO_PLAYLIST;
  const c = v.controls;
  const controls = isRecord(c) && typeof c.skill === "string" && typeof c.comfort === "number" && isRecord(c.measured)
    ? { skill: c.skill, comfort: c.comfort, measured: c.measured as Record<string, number> }
    : null;
  const p = v.playlist;
  const playlist = isRecord(p) && typeof p.skill === "string" && Array.isArray(p.stages) ? (p as unknown as Schemas["Playlist"]) : null;
  return {
    options: v.options as RecommendationOptions,
    controls,
    job: typeof v.job === "string" ? v.job : null,
    playlist,
    maps: typeof v.maps === "string" ? v.maps : null,
    rounds: roundsOf(v.rounds),
    done: Array.isArray(v.done) ? v.done.filter((d): d is string => typeof d === "string") : [],
  };
}

export function savePlaylist(saved: SavedPlaylist, storage: Pick<Storage, "setItem"> = localStorage) {
  // without its maps, the selection still comes back and the playlist is made again from it
  keep(SAVED, saved, { ...saved, playlist: null }, storage);
}

/** Skill Development as it was left (#107): the settings applied, how many times they were (a new apply starts each
 * skill's maps again with the best ones) and the group of five each skill shows. */
export interface SavedSuggestions {
  options: { kappa?: number; min_relevance?: number };
  applied: number;
  rounds: Record<string, Rounds>;
}

const SAVED_SUGGESTIONS = "osu-coach:skill-development";
export const NO_SUGGESTIONS: SavedSuggestions = { options: {}, applied: 0, rounds: {} };

export function loadSuggestions(storage: Pick<Storage, "getItem"> = sessionStorage): SavedSuggestions {
  const v = load(SAVED_SUGGESTIONS, storage);
  if (!isRecord(v) || !isRecord(v.options) || !Number.isInteger(v.applied)) return NO_SUGGESTIONS;
  const { kappa, min_relevance } = v.options;
  return {
    options: {
      ...(typeof kappa === "number" ? { kappa } : {}),
      ...(typeof min_relevance === "number" ? { min_relevance } : {}),
    },
    applied: v.applied as number,
    rounds: roundsOf(v.rounds),
  };
}

export function saveSuggestions(saved: SavedSuggestions, storage: Pick<Storage, "setItem"> = sessionStorage) {
  keep(SAVED_SUGGESTIONS, saved, NO_SUGGESTIONS, storage);
}

/** Names a playlist by its maps, so the groups shown come back only for the same maps (null: no playlist yet). */
export function playlistKey(
  pl: { skill: string; stages: { stage: string; maps: { md5: string; configuration_id?: string | null }[] }[] } | null | undefined,
): string | null {
  if (!pl) return null;
  const text = [pl.skill, ...pl.stages.map((st) => `${st.stage}:${st.maps.map((m) => m.configuration_id ?? m.md5).join(",")}`)].join("|");
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = (Math.imul(h, 33) ^ text.charCodeAt(i)) >>> 0;
  return `${pl.skill}:${h.toString(36)}:${text.length}`;
}
