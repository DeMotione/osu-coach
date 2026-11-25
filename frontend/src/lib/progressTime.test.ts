import { describe, expect, it } from "vitest";

import { ends, periodLabel, periodStart, timeline } from "./progressTime";

describe("periodStart", () => {
  it("reads months, ISO weeks and days", () => {
    expect(periodStart("2026-11")).toEqual(new Date(2026, 10, 1));
    expect(periodStart("2026-11-18")).toEqual(new Date(2026, 10, 18));
    expect(periodStart("2026-W01")).toEqual(new Date(2025, 11, 29)); // the week with 4 January 2026 starts on 29 Dec
    expect(periodStart("2026-W47")).toEqual(new Date(2026, 10, 16));
    expect(periodStart("soon")).toBeNull();
  });
});

describe("timeline", () => {
  it("breaks the line where months without plays lie between two months", () => {
    const rows = [{ key: "2021-07", v: 1 }, { key: "2021-08", v: 2 }, { key: "2024-11", v: 3 }, { key: "2024-12", v: null }];
    const pts = timeline(rows, "month", (r) => r.v);
    expect(pts.map((p) => p[1])).toEqual([1, 2, null, 3]);
    expect(pts[0][0]).toBe(new Date(2021, 6, 1).getTime());
    expect(ends(pts)).toEqual({ first: 1, last: 3 });
  });

  it("joins periods one after the other", () => {
    const pts = timeline([{ key: "2026-W46", v: 1 }, { key: "2026-W47", v: 2 }], "week", (r) => r.v);
    expect(pts.map((p) => p[1])).toEqual([1, 2]);
    expect(ends([[0, 5]])).toBeNull();
  });
});

describe("periodLabel", () => {
  it("names a period as people say it", () => {
    expect(periodLabel("2026-10")).toBe("Oct 2026");
    expect(periodLabel("2026-W40")).toBe("the week of 28 Sep");
    expect(periodLabel("2026-11-18")).toBe("18 Nov");
  });
});
