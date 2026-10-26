import { useCallback, useState } from "react";

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

/** Each stage's ``Rounds`` by its name, all back to the first group when ``of`` changes (a new playlist). */
export function useRounds(of: unknown) {
  const [state, setState] = useState<{ of: unknown; by: Record<string, Rounds> }>({ of, by: {} });
  if (state.of !== of) setState({ of, by: {} });
  const by = state.of === of ? state.by : NONE;
  const rounds = useCallback((stage: string) => by[stage] ?? FIRST_ROUND, [by]);
  const move = useCallback(
    (stage: string, to: "back" | "forward" | "other") =>
      setState((s) => ({ ...s, by: { ...s.by, [stage]: moveRound(s.by[stage] ?? FIRST_ROUND, to) } })),
    [],
  );
  return { rounds, move };
}
