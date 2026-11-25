import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { keysVerdict, lateInMap, timingVerdict } from "./tappingWords";

const keys = (shares: [string, number][], chatter = 0): Schemas["KeyUsage"] => ({
  shares: shares.map(([key, share]) => ({ key, share })),
  hold_ms: 80,
  press_ms_streams: 50,
  chatter_per_1000: chatter,
});

describe("timingVerdict", () => {
  it("calls a few ms centred, more early or late", () => {
    expect(timingVerdict(-1)?.tone).toBe("good");
    expect(timingVerdict(5)?.text).toMatch(/a little late: 5.0 ms/);
    expect(timingVerdict(-12)?.tone).toBe("bad");
    expect(timingVerdict(null)).toBeNull();
  });
});

describe("keysVerdict", () => {
  it("puts chatter first, then leaning on one finger, then streams not alternated", () => {
    expect(keysVerdict(keys([["K1", 0.5], ["K2", 0.5]], 6), 0.95)?.text).toMatch(/double-press/);
    expect(keysVerdict(keys([["K1", 0.5], ["K2", 0.5]], 2), 0.95)?.tone).toBe("good"); // normal bounce
    expect(keysVerdict(keys([["K1", 0.75], ["K2", 0.25]]), 0.95)?.text).toMatch(/left key takes 75%/);
    expect(keysVerdict(keys([["K1", 0.5], ["K2", 0.5]]), 0.6)?.text).toMatch(/alternate 60% of stream notes/);
  });

  it("adds up the left and the right keys of osu!stable and lazer", () => {
    const fine = keysVerdict(keys([["K1", 0.23], ["K2", 0.26], ["L", 0.24], ["R", 0.26], ["M1", 0.01]]), 0.97);
    expect(fine?.tone).toBe("good");
    expect(fine?.text).toBe("You use both fingers evenly: left 48% · right 52%, 97% of stream notes alternated.");
  });
});

describe("lateInMap", () => {
  const along = (points: [number, number][]): Schemas["StreamsOverTime"] => ({
    bands: [],
    band_width: 20,
    notes: 0,
    session: { step: 1, lines: [] },
    map: { step: 0.5, lines: [{ key: "overall", points: points.map(([miss_rate, n], i) => ({ x: i / 2, miss_rate, ur: null, n })) }] },
  });

  it("says so when streams fall apart in the last third of maps", () => {
    expect(lateInMap(along([[1, 200], [1, 200], [1.2, 200], [4, 200], [5, 200], [6, 200]]))).toMatch(/Late in maps/);
  });

  it("says nothing without a clear difference or with too few notes", () => {
    expect(lateInMap(along([[2, 200], [2, 200], [2, 200], [2.2, 200], [2.1, 200], [2.3, 200]]))).toBeNull();
    expect(lateInMap(along([[1, 10], [1, 10], [1, 10], [9, 10], [9, 10], [9, 10]]))).toBeNull();
  });
});
