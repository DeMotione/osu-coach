import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { circle, merge, niceMax, responsive } from "./base";
import { mmss, playTimingChart, rangeStats } from "./check";
import { MISS_SHORT, compareBars, compareHover, missCauses, skillBars, skillHover } from "./overview";
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

const skill = (key: string, score: number | null): Schemas["SkillScore"] => ({
  key,
  label: `${key} label`,
  score,
  score_text: score === null ? "not enough data" : score.toFixed(0),
  low_data: false,
  too_few_misses: score === null,
  n: 100,
  facts: ["100 notes"],
});

describe("overview charts", () => {
  it("explains a skill with what it measures, the player's numbers and what raises it", () => {
    const html = skillHover(skill("aim", null), { key: "aim", label: "Jump aim", what: "W <b>", how: "H", practise: "P" });
    expect(html).toContain("not enough data");
    expect(html).toContain("W &lt;b&gt;");
    expect(html).toContain("You: 100 notes");
    expect(html).toContain("To raise it: P");
  });

  it("draws one bar per skill, empty ones at 0", () => {
    const o = (skillBars([skill("aim", 61), skill("flow_aim", null)], [], t) as { baseOption: AnyOption }).baseOption;
    const data = (o.series![0].data as { value: number }[]).map((d) => d.value);
    expect(data).toEqual([61, 0]);
  });

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

describe("comparison bars", () => {
  const skills = [skill("aim", 67), skill("sliders", 28), skill("stamina", null)];
  const levels: Schemas["SkillLevel"][] = [
    { key: "aim", label: "Jump aim", level: 13, bound: "at_least", tested: 9.1 },
    { key: "sliders", label: "Sliders", level: 6.12, bound: null, tested: 7 },
    { key: "stamina", label: "Stamina", level: null, bound: null, tested: null },
  ];
  const at = (stars: number): Schemas["CompareTarget"] => ({
    stars,
    comfort: false,
    skills: levels.map((l) => {
      const gap = l.level === null ? null : Math.round((l.level - stars) * 100) / 100;
      return { key: l.key, gap, score: gap === null ? null : Math.max(0, Math.min(100, 50 + 10 * gap)) };
    }),
    effective: 6.2,
    limiting: "sliders",
    pass_chance: 0.2,
  });

  it("puts each skill level against the picked star rating", () => {
    const values = (stars: number) => {
      const o = (compareBars(skills, levels, at(stars), t) as { baseOption: AnyOption }).baseOption;
      return (o.series![0].data as { value: number }[]).map((d) => Math.round(d.value));
    };
    expect(values(6.12)).toEqual([100, 50, 0]);
    expect(values(8.3)).toEqual([97, 28, 0]);
  });

  it("labels the gaps in stars, a lower bound with ≥ and unmeasured skills with –", () => {
    const o = (compareBars(skills, levels, at(8.3), t) as { baseOption: AnyOption }).baseOption;
    const label = (o.series![0] as { label: { formatter: (p: unknown) => string } }).label.formatter;
    expect([0, 1, 2].map((i) => label({ dataIndex: i }))).toEqual(["≥ +4.7★", "−2.2★", "–"]);
  });

  it("explains where the number comes from", () => {
    const help = { key: "sliders", label: "Sliders", what: "W <b>", how: "H", practise: "P" };
    const html = compareHover(skills[1], levels[1], at(8.3), help);
    expect(html).toContain("sliders label at 8.3★: 28 (−2.2★)");
    expect(html).toContain("Your level: 6.1★");
    expect(html).toContain("2.2★ short of what typical 8.3★ maps demand");
    expect(html).toContain("W &lt;b&gt;");
    expect(compareHover(skills[0], levels[0], at(8.3))).toContain("so it may be higher");
    expect(compareHover(skills[0], levels[0], at(5))).toContain("8.0★ above what typical 5★ maps demand");
    expect(compareHover(skills[2], levels[2], at(8.3))).toContain("not enough data");
  });
});

