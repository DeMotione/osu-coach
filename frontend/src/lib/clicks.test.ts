import { describe, expect, it } from "vitest";

import { clickFilter, starBounds } from "./clicks";

const plays = [
  { stars: 4.23, played_at: "2022-06-08T12:00:00Z" },
  { stars: 6.71, played_at: "2022-06-23T12:00:00Z" },
  { stars: null, played_at: null },
];

describe("starBounds", () => {
  it("runs from the easiest to the hardest play, out to a tenth", () => {
    expect(starBounds(plays)).toEqual([4.2, 6.8]);
    expect(starBounds([{ stars: null, played_at: null }])).toBeNull();
  });
});

describe("clickFilter", () => {
  it("leaves out a slider end at its bound", () => {
    expect(clickFilter([4.2, 6.8], [4.2, 6.8], null)).toEqual({});
    expect(clickFilter([5, 6.8], [4.2, 6.8], null)).toEqual({ stars_min: 5 });
    expect(clickFilter(null, [4.2, 6.8], null)).toEqual({});
  });

  it("adds the days as a time range", () => {
    const f = clickFilter(null, null, { from: "2022-06-08", to: "2022-06-23" });
    expect(Object.keys(f).sort()).toEqual(["since", "until"]);
  });
});
