import { describe, expect, it } from "vitest";

import { dayLabel, monthGrid, monthLabel, pickDay, rangeLabel, shiftMonth, utcRange } from "./dateRange";

describe("monthGrid", () => {
  it("shows six weeks, Monday first, with the days around the month", () => {
    const june = monthGrid(2022, 5);
    expect(june).toHaveLength(42);
    expect(june[0]).toBe("2022-05-30"); // 1 June 2022 is a Wednesday
    expect(june[2]).toBe("2022-06-01");
    expect(june[41]).toBe("2022-07-10");
  });

  it("starts on the 1st when the month starts on a Monday", () => {
    expect(monthGrid(2026, 5)[0]).toBe("2026-06-01");
  });
});

describe("pickDay", () => {
  it("picks the first day, then the last", () => {
    const first = pickDay(null, "2022-06-08");
    expect(first).toEqual({ from: "2022-06-08", to: null });
    expect(pickDay(first, "2022-06-23")).toEqual({ from: "2022-06-08", to: "2022-06-23" });
  });

  it("swaps the days when the second is earlier, and starts again once both are picked", () => {
    expect(pickDay({ from: "2022-06-08", to: null }, "2022-06-01")).toEqual({ from: "2022-06-01", to: "2022-06-08" });
    expect(pickDay({ from: "2022-06-08", to: "2022-06-23" }, "2022-06-10")).toEqual({ from: "2022-06-10", to: null });
  });
});

describe("labels and months", () => {
  it("names days, ranges and months", () => {
    expect(dayLabel("2022-06-08")).toBe("Wed, 08 Jun");
    expect(rangeLabel({ from: "2022-06-08", to: "2022-06-23" })).toBe("08 Jun 2022 – 23 Jun 2022");
    expect(rangeLabel({ from: "2022-06-08", to: "2022-06-08" })).toBe("08 Jun 2022");
    expect(monthLabel(2022, 5)).toBe("June, 2022");
  });

  it("moves across years", () => {
    expect(shiftMonth(2022, 0, -1)).toEqual([2021, 11]);
    expect(shiftMonth(2022, 11, 1)).toEqual([2023, 0]);
  });
});

describe("utcRange", () => {
  it("runs from the start of the first day to the start of the day after the last, on this computer's clock", () => {
    const { since, until } = utcRange({ from: "2022-06-08", to: "2022-06-23" });
    expect(new Date(since).getTime()).toBe(new Date(2022, 5, 8).getTime());
    expect(new Date(until).getTime()).toBe(new Date(2022, 5, 24).getTime());
  });

  it("is that one day with only the first day picked", () => {
    const { since, until } = utcRange({ from: "2022-06-08", to: null });
    expect(new Date(until).getTime() - new Date(since).getTime()).toBe(24 * 3600 * 1000);
  });
});
