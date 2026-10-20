import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { circle, merge, niceMax, responsive } from "./base";
import { mmss, playTimingChart, rangeStats } from "./check";
import { MISS_SHORT, compareBars, compareHover, missCauses, skillBars, skillHover } from "./overview";
import { alpha, chartTheme, heat, scoreColor, C } from "./palette";
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

const skill = (key: string, score: number | null, needs: string | null = null): Schemas["SkillScore"] => ({
  key,
  label: `${key} label`,
  score,
  score_text: score === null ? "not enough data" : score.toFixed(0),
  low_data: false,
  too_few_misses: score === null,
  n: 100,
  facts: ["100 notes"],
  needs,
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

  it("shows a skill that needs more plays as a full grey bar saying so, its hover what to play", () => {
    const needs = "Play 3 more different maps between 4.0★ and 6.0★";
    const o = (skillBars([skill("aim", 61), skill("consistency", null, needs)], [], t) as { baseOption: AnyOption }).baseOption;
    const bar = (o.series![0].data as { value: number; label?: { formatter: string } }[])[1];
    expect(bar.value).toBe(100);
    expect(bar.label?.formatter).toBe("Not enough data");
    expect(skillHover(skill("consistency", null, needs))).toContain(`To get a score: ${needs}`);
    expect(skillHover(skill("aim", 61))).not.toContain("To get a score");
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
  const at = (stars: number, rows: [number | null, number | null][], comfort = false): Schemas["CompareTarget"] => ({
    stars,
    comfort,
    locked: false,
    skills: rows.map(([score, change], i) => ({ key: skills[i].key, score, change, demand: change === null ? null : 1 - change / 100 })),
    weakest: "sliders",
    pass_chance: 0.36,
  });
  const harder = at(7.6, [[61, -6], [19, -9], [null, null]]);
  const easier = at(5.6, [[72, 5], [33, 5], [null, null]]);
  const option = (target: Schemas["CompareTarget"]) => (compareBars(skills, target, 6.59, t) as { baseOption: AnyOption }).baseOption;
  const values = (o: AnyOption, i: number) => (o.series![i].data as { value: number }[]).map((d) => d.value);
  const labels = (o: AnyOption) =>
    [0, 1, 2].map((i) => {
      const shown = [0, 1].find((k) => (o.series![k].data as { label: { show: boolean } }[])[i].label.show) as number;
      return (o.series![shown] as { label: { formatter: (p: unknown) => string } }).label.formatter({ dataIndex: i });
    });

  it("shows the comfort-level scores faded behind the scores at the picked star rating", () => {
    const o = option(harder);
    expect(values(o, 0)).toEqual([67, 28, 0]);
    expect(values(o, 1)).toEqual([61, 19, 0]);
    expect(values(option(at(6.6, [[67, 0], [28, 0], [null, null]], true)), 0)).toEqual([0, 0, 0]); // no faded bars at comfort
    const faded = (o.series![0].data as { itemStyle: { color: string } }[])[0].itemStyle.color;
    expect(faded).toBe(alpha(C.good, 0.3)); // a faded colour, not opacity: that would fade the label too
    expect(alpha("#ff66aa", 0.5)).toBe("rgba(255,102,170,0.5)");
  });

  it("labels each score with its change after the longer bar", () => {
    expect(labels(option(harder))).toEqual(["61 (−6)", "19 (−9)", "–"]);
    expect(labels(option(easier))).toEqual(["72 (+5)", "33 (+5)", "–"]);
    expect(labels(option(at(6.6, [[67, 0], [28, 0], [null, null]], true)))).toEqual(["67", "28", "–"]);
  });

  it("explains where the number comes from", () => {
    const help = { key: "aim", label: "Jump aim", what: "W <b>", how: "H", practise: "P" };
    const html = compareHover(skills[0], harder, 6.59, help);
    expect(html).toContain("aim label at 7.6★: 61 (−6)");
    expect(html).toContain("demand 6% more of this skill than maps of your 6.6★ comfort level, so 67 drops to 61");
    expect(html).toContain("W &lt;b&gt;");
    expect(compareHover(skills[0], easier, 6.59)).toContain("5% less of this skill");
    expect(compareHover(skills[2], harder, 6.59)).toContain("not enough data");
  });
});


