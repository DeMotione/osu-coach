import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import {
  canGoBack, canGoForward, FIRST_ROUND, HISTORY, loadPlaylist, loadSuggestions, moveRound, NO_PLAYLIST, NO_SUGGESTIONS,
  playlistKey, type Rounds, savePlaylist, saveSuggestions, stageMaps, useRounds,
} from "./playlist";

describe("stageMaps", () => {
  const maps = Array.from({ length: 12 }, (_, i) => i);

  it("shows five maps at a time, best first", () => {
    expect(stageMaps(maps, 0)).toEqual({ maps: [0, 1, 2, 3, 4], first: 0 });
    expect(stageMaps(maps, 1)).toEqual({ maps: [5, 6, 7, 8, 9], first: 5 });
  });

  it("ends with the rest and then starts over", () => {
    expect(stageMaps(maps, 2)).toEqual({ maps: [10, 11], first: 10 });
    expect(stageMaps(maps, 3)).toEqual({ maps: [0, 1, 2, 3, 4], first: 0 });
  });

  it("handles short and empty lists", () => {
    expect(stageMaps([1, 2], 4)).toEqual({ maps: [1, 2], first: 0 });
    expect(stageMaps([], 1)).toEqual({ maps: [], first: 0 });
  });
});

describe("moveRound", () => {
  const go = (...moves: ("back" | "forward" | "other")[]) => moves.reduce<Rounds>(moveRound, FIRST_ROUND);

  it("starts with only Other maps", () => {
    expect(canGoBack(FIRST_ROUND)).toBe(false);
    expect(canGoForward(FIRST_ROUND)).toBe(false);
  });

  it("goes back and forward through the groups shown, Forward only behind the newest", () => {
    const r = go("other", "other", "back");
    expect(r).toEqual({ at: 1, latest: 2 });
    expect(canGoBack(r) && canGoForward(r)).toBe(true);
    expect(go("other", "other", "back", "forward")).toEqual({ at: 2, latest: 2 });
    expect(canGoForward(go("other", "other", "back", "forward"))).toBe(false);
  });

  it("brings up a new group after the newest from anywhere in the history", () => {
    expect(go("other", "other", "back", "back", "other")).toEqual({ at: 3, latest: 3 });
  });

  it("keeps the last 20 groups", () => {
    let r = go(...Array<"other">(HISTORY + 5).fill("other"));
    for (let i = 0; i < 40; i++) r = moveRound(r, "back");
    expect(r).toEqual({ at: 6, latest: HISTORY + 5 });
    expect(r.latest - r.at + 1).toBe(HISTORY);
    expect(canGoBack(r)).toBe(false);
  });
});

describe("the playlist kept while away (#107)", () => {
  const memory = () => {
    const items = new Map<string, string>();
    return { getItem: (k: string) => items.get(k) ?? null, setItem: (k: string, v: string) => void items.set(k, v), items };
  };
  const pl = (skill: string, md5s: string[]) => ({ skill, stages: [{ stage: "Comfort", maps: md5s.map((md5) => ({ md5 })) }] });

  it("comes back as it was saved", () => {
    const storage = memory();
    const saved = {
      options: { skill: "stamina", assessed: "stamina", allow_hr: true },
      controls: { skill: "flow_aim", measured: { stamina: 54.6 }, comfort: 6.27 },
      job: "j1",
      playlist: pl("stamina", ["a", "b"]) as unknown as Schemas["Playlist"],
      maps: "stamina:abc:12",
      rounds: { Comfort: { at: 1, latest: 2 } },
    };
    savePlaylist(saved, storage);
    expect(loadPlaylist(storage)).toEqual(saved);
  });

  it("starts with the default playlist when nothing or something garbled is kept", () => {
    const storage = memory();
    expect(loadPlaylist(storage)).toEqual(NO_PLAYLIST);
    storage.items.set("osu-coach:skill-playlist", "{not json");
    expect(loadPlaylist(storage)).toEqual(NO_PLAYLIST);
    storage.items.set("osu-coach:skill-playlist", JSON.stringify({ options: {}, rounds: { Comfort: { at: "x" } }, controls: 3 }));
    expect(loadPlaylist(storage)).toEqual(NO_PLAYLIST);
  });

  it("keeps the selection without the maps when the playlist is too big for the storage", () => {
    const items = new Map<string, string>();
    const full = { getItem: (k: string) => items.get(k) ?? null, setItem: (k: string, v: string) => {
      if (v.length > 200) throw new DOMException("full", "QuotaExceededError");
      items.set(k, v);
    } };
    const big = pl("stamina", Array.from({ length: 50 }, (_, i) => `map${i}`)) as unknown as Schemas["Playlist"];
    savePlaylist({ ...NO_PLAYLIST, options: { skill: "stamina" }, playlist: big }, full);
    expect(loadPlaylist(full)).toEqual({ ...NO_PLAYLIST, options: { skill: "stamina" } });
  });

  it("keeps Skill Development's settings and groups", () => {
    const storage = memory();
    expect(loadSuggestions(storage)).toEqual(NO_SUGGESTIONS);
    const saved = { options: { kappa: 0.8, min_relevance: 0.4 }, applied: 2, rounds: { speed: { at: 1, latest: 1 } } };
    saveSuggestions(saved, storage);
    expect(loadSuggestions(storage)).toEqual(saved);
    storage.items.set("osu-coach:skill-development", JSON.stringify({ options: { kappa: "x" }, applied: 1, rounds: {} }));
    expect(loadSuggestions(storage)).toEqual({ options: {}, applied: 1, rounds: {} });
  });

  it("names a playlist by its maps", () => {
    expect(playlistKey(pl("stamina", ["a", "b"]))).toBe(playlistKey(pl("stamina", ["a", "b"])));
    expect(playlistKey(pl("stamina", ["a", "b"]))).not.toBe(playlistKey(pl("stamina", ["b", "a"])));
    expect(playlistKey(pl("stamina", ["a"]))).not.toBe(playlistKey(pl("speed", ["a"])));
    expect(playlistKey(undefined)).toBeNull();
  });

  it("shows the kept groups again only for the same playlist", () => {
    const kept = { of: "K", by: { Comfort: { at: 1, latest: 1 } } };
    const { result, rerender } = renderHook(({ of }: { of: string | null }) => useRounds(of, kept), { initialProps: { of: null as string | null } });
    expect(result.current.rounds("Comfort")).toEqual(FIRST_ROUND); // still loading
    rerender({ of: "K" });
    expect(result.current.rounds("Comfort")).toEqual({ at: 1, latest: 1 });
    rerender({ of: "other" });
    expect(result.current.rounds("Comfort")).toEqual(FIRST_ROUND);
    act(() => result.current.move("Comfort", "other"));
    expect(result.current.by).toEqual({ Comfort: { at: 1, latest: 1 } });
  });
});
