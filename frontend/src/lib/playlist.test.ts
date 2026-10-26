import { describe, expect, it } from "vitest";

import { canGoBack, canGoForward, FIRST_ROUND, HISTORY, moveRound, type Rounds, stageMaps } from "./playlist";

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
