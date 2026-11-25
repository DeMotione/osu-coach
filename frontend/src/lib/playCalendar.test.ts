import { describe, expect, it } from "vitest";

import { isoDay } from "./format";
import { playLevel, playStats } from "./playCalendar";

describe("play calendar", () => {
  it("shades a day by how much was played", () => {
    expect([0, 1, 3, 7, 12].map(playLevel)).toEqual([0, 1, 2, 3, 4]);
  });

  it("counts the days played, the last month's, the longest break and the days since the last play", () => {
    const today = new Date(2026, 10, 18);
    const plays = new Map([
      [isoDay(-200, today), 3],
      [isoDay(-150, today), 1], // 49 days without a play before it
      [isoDay(-10, today), 4],
      [isoDay(-2, today), 2],
    ]);
    expect(playStats(plays, today)).toEqual({ lastYear: 4, lastMonth: 2, longestBreak: 139, daysSince: 2 });
  });
});
