import { useCallback, useState } from "react";

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
 * selection applied, the figures its controls started from, the search behind a playlist with mods, and the group
 * of five each stage shows for the playlist ``maps`` names. Kept for the app window's session. */
export interface SavedPlaylist {
  options: RecommendationOptions;
  controls: PlaylistControls | null;
  job: string | null;
  maps: string | null;
  rounds: Record<string, Rounds>;
}

const SAVED = "osu-coach:skill-playlist";
export const NO_PLAYLIST: SavedPlaylist = { options: {}, controls: null, job: null, maps: null, rounds: {} };

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isRounds = (v: unknown): v is Rounds => isRecord(v) && Number.isInteger(v.at) && Number.isInteger(v.latest);

export function loadPlaylist(storage: Pick<Storage, "getItem"> = sessionStorage): SavedPlaylist {
  try {
    const v: unknown = JSON.parse(storage.getItem(SAVED) ?? "null");
    if (!isRecord(v) || !isRecord(v.options)) return NO_PLAYLIST;
    const c = v.controls;
    const controls = isRecord(c) && typeof c.skill === "string" && typeof c.comfort === "number" && isRecord(c.measured)
      ? { skill: c.skill, comfort: c.comfort, measured: c.measured as Record<string, number> }
      : null;
    const rounds = isRecord(v.rounds) ? Object.entries(v.rounds).filter((e): e is [string, Rounds] => isRounds(e[1])) : [];
    return {
      options: v.options as RecommendationOptions,
      controls,
      job: typeof v.job === "string" ? v.job : null,
      maps: typeof v.maps === "string" ? v.maps : null,
      rounds: Object.fromEntries(rounds),
    };
  } catch {
    return NO_PLAYLIST; // storage blocked or garbled: the default playlist
  }
}

export function savePlaylist(saved: SavedPlaylist, storage: Pick<Storage, "setItem"> = sessionStorage) {
  try {
    storage.setItem(SAVED, JSON.stringify(saved));
  } catch {
    /* a convenience only */
  }
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
