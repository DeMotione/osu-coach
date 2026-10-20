import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { circle, merge, niceMax, responsive } from "./base";
import { mmss, playTimingChart, rangeStats } from "./check";
import { MISS_SHORT, missCauses, readinessBars, readinessHover } from "./overview";
import { chartTheme, heat, scoreColor, C } from "./palette";
import { timingChart } from "./tapping";

const t = chartTheme(true);

type AnyOption = Record<string, unknown> & { series?: Record<string, unknown>[] };

describe("helpers", () => {
  it("merges nested options", () => {
    expect(merge({ a: { b: 1, c: 2 }, d: [1] }, { a: { c: 3 }, d: [2] })).toEqual({ a: { b: 1, c: 3 }, d: [2] });
  });

  it("rounds axis maxima", () => {
    expect(niceMax(37, 10, 1.18)).toBe(50);
    expect(niceMax(95, 10, 1.18, 100)).toBe(100);
    expect(niceMax(0.2)).toBe(10);
  });

  it("draws a closed circle", () => {
    const pts = circle(1, 8);
    expect(pts).toHaveLength(9);
    expect(pts[0][0]).toBeCloseTo(pts[8][0]);
    expect(pts.every(([x, y]) => Math.abs(Math.hypot(x, y) - 1) < 1e-9)).toBe(true);
  });

  it("colours scores like the old app: green ≥ 55, red ≤ 45", () => {
    expect(scoreColor(55)).toBe(C.good);
    expect(scoreColor(45)).toBe(C.bad);
    expect(scoreColor(50)).toBe(C.info);
    expect(scoreColor(null)).toBe(C.muted);
    expect(heat(0, t)).not.toBe(heat(1, t));
  });

  it("wraps options with narrow-screen overrides", () => {
    const o = responsive({ a: 1 }, { b: 2 }) as { baseOption: unknown; media: { query: { maxWidth: number } }[] };
    expect(o.baseOption).toEqual({ a: 1 });
    expect(o.media[0].query.maxWidth).toBeGreaterThan(0);
  });
});

describe("overview charts", () => {
  it("sorts miss causes so the biggest is on top", () => {
    const o = missCauses(
      [
        { cause: "aim", share: 0.6, misses: 60 },
        { cause: "late", share: 0.1, misses: 10 },
        { cause: "no_tap", share: 0.3, misses: 30 },
      ],
      {},
      t,
    ) as AnyOption;
    expect((o.yAxis as { data: string[] }).data).toEqual([MISS_SHORT.late, MISS_SHORT.no_tap, MISS_SHORT.aim]);
  });
});

describe("timing", () => {
  const h: Schemas["TimingHistogram"] = {
    centers: [-1.5, 1.5],
    n300: [10, 0],
    n100: [0, 2],
    n50: [0, 0],
    total: 12,
    share300: 0.83,
    share100: 0.17,
    share50: 0,
    mean: 0.5,
  };

  it("drops empty bars on the log scale (log 0 is undefined)", () => {
    const o = timingChart(h, "log", 15, t) as AnyOption;
    expect(o.series![0].data).toEqual([10, null]);
    expect((o.yAxis as { type: string }).type).toBe("log");
  });

  it("cuts the peak when zoomed in", () => {
    const o = timingChart(h, "zoom", 50, t) as AnyOption;
    expect((o.yAxis as { max: number }).max).toBe(5);
  });

  const tm: Schemas["PlayTiming"] = {
    time: [1000, 2000, 3000, 4000],
    error: [-10, 10, 20, 0],
    result: [300, 300, 100, 300],
    trend: [null, 5, 5, null],
    window_300: 26,
    top: 22,
    length_ms: 61000,
    marks: [{ time: 2500, what: "miss", label: "00:02:500 miss: aim" }],
  };

  it("summarises the zoomed part of a play", () => {
    expect(rangeStats(tm, 0, 61000)).toEqual({ n: 4, mean: 5, ur: expect.closeTo(129.1, 1), marks: 1 });
    expect(rangeStats(tm, 1500, 2600)).toEqual({ n: 1, mean: 10, ur: null, marks: 1 });
  });

  it("shows map time as mm:ss and round error limits", () => {
    expect(mmss(75400)).toBe("01:15");
    const o = playTimingChart(tm, t) as AnyOption;
    expect((o.yAxis as { max: number }).max).toBe(30);
    expect((o.xAxis as { max: number }).max).toBe(61000);
  });
});

describe("readiness bars", () => {
  const skills: Schemas["SkillLevel"][] = [
    { key: "aim", label: "Aim", level: 6.57, facts: ["the hardest jump sections you cleared, on 38 plays"] },
    { key: "sliders", label: "Slider control", level: 9, facts: ["slider speed"] },
    { key: "flow_aim", label: "Flow aim", level: 5, facts: ["spaced streams"] },
    { key: "reading", label: "Reading", level: null, facts: ["not measured"] },
  ];

  it("shows each skill's readiness for the target, out of reach at twice the strain", () => {
    const o = (readinessBars(skills, 8, t) as { baseOption: AnyOption }).baseOption;
    const bars = o.series![0] as { data: { value: number }[]; label: { formatter: (p: unknown) => string } };
    expect(bars.data.map((d) => d.value)).toEqual([52, 100, 0, 0]);
    const label = (i: number) => bars.label.formatter({ dataIndex: i });
    expect([0, 1, 2, 3].map(label)).toEqual(["52%", "100%", "out of reach", "–"]);
  });

  it("explains the level in the hover, with what the skill is and what raises it", () => {
    const help = { key: "aim", label: "Jump aim", what: "W <b>", how: "H", practise: "P" };
    const html = readinessHover(skills[0], 8, help);
    expect(html).toContain("52% ready for 8★");
    expect(html).toContain("8★ feels 48% harder; out of reach from 9.3★");
    expect(html).toContain("W &lt;b&gt;");
    expect(html).toContain("To raise it: P");
    expect(readinessHover(skills[1], 8)).toContain("8★ is within it");
    expect(readinessHover(skills[3], 8)).toContain("not enough data");
  });
});
