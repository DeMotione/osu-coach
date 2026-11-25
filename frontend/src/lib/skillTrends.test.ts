import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { meaningful, skillTrends } from "./skillTrends";

const row = (key: string, aim: number | null, speed: number | null = null): Schemas["PeriodRow"] => ({
  key, plays: 6, maps: 6, new_maps: 6, minutes: 30, comfort_stars: null, avg_stars: null, max_stars_passed: null, max_stars_fc: null,
  accuracy: null, misses_per_100: null, ur: null, stream_bpm: null, few_plays: false, skills: {},
  star_levels: {
    ...(aim === null ? {} : { aim: { stars: aim, low: null, high: null } }),
    ...(speed === null ? {} : { speed: { stars: speed, low: null, high: null } }),
  },
});

describe("skillTrends", () => {
  it("gives each skill with a level its timeline, latest value and change since the first", () => {
    const trends = skillTrends([row("2026-W44", 6.8), row("2026-W45", 7.1, 6.2)], "week",
      [{ key: "aim", label: "Jumps" }, { key: "speed", label: "Tapping speed" }, { key: "reading", label: "Reading" }], true);
    expect(trends.map((t) => t.key)).toEqual(["aim", "speed"]); // no level of reading: left out
    expect(trends[0].last).toBeCloseTo(7.1);
    expect(trends[0].change).toBeCloseTo(0.3);
    expect(trends[1].change).toBeNull(); // one week so far
  });

  it("calls a tenth of a star (or 2 points) a change", () => {
    expect(meaningful(0.12, true)).toBe(true);
    expect(meaningful(0.05, true)).toBe(false);
    expect(meaningful(-3, false)).toBe(true);
    expect(meaningful(null, true)).toBe(false);
  });
});
