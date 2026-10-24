import { describe, expect, it } from "vitest";

import { stageMaps } from "./playlist";

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
