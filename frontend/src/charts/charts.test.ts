import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { circle, merge, niceMax, responsive } from "./base";
import { mmss, playTimingChart, rangeStats } from "./check";
import { MISS_SHORT, compareBars, compareHover, missCauses, starLevelHover, starLevels } from "./overview";
import { alpha, chartTheme, faded, heat, scoreColor, C } from "./palette";
import { goalLabelLayout, goalOffsets, goalsChart, skillsChart, starLevelsChart, starsChart } from "./progress";
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

const skill = (key: string, score: number | null, needs: string | null = null, atLeast: number | null = null): Schemas["SkillScore"] => ({
  key,
  label: `${key} label`,
  score,
  score_text: score === null ? "not enough data" : score.toFixed(0),
  low_data: false,
  too_few_misses: score === null,
  n: 100,
  facts: ["100 notes"],
  needs,
  at_least: atLeast,
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

describe("comparison bars", () => {
  const skills = [skill("aim", 67), skill("sliders", 28), skill("stamina", null)];
  const at = (stars: number, rows: [number | null, number | null][], comfort = false): Schemas["CompareTarget"] => ({
    stars,
    comfort,
    locked: false,
    skills: rows.map(([score, change], i) => ({
      key: skills[i].key,
      score,
      change,
      demand: change === null ? null : 1 - change / 100,
      maps: null,
      needs: null,
    })),
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
    const help = { key: "aim", label: "Jumps", summary: "", what: "W <b>", how: "H", practise: "P" };
    const html = compareHover(skills[0], harder, 6.59, help);
    expect(html).toContain("aim label at 7.6★: 61 (−6)");
    expect(html).toContain("demand 6% more of this skill than maps of your 6.6★ comfort level, so 67 drops to 61");
    expect(html).toContain("W &lt;b&gt;");
    expect(compareHover(skills[0], easier, 6.59)).toContain("5% less of this skill");
    expect(compareHover(skills[2], harder, 6.59)).toContain("not enough data");
  });

  it("measures consistency on the maps of the star rating picked: a grey bar and what to play until then", () => {
    const all = [...skills, skill("consistency", 40)];
    const target = (row: Partial<Schemas["CompareSkill"]>) => {
      const t7 = at(7.5, [[61, -6], [19, -9], [null, null]]);
      return { ...t7, skills: [...t7.skills, { key: "consistency", score: null, change: null, demand: null, maps: 3, needs: null, ...row }] };
    };
    const needs = "Play 5 more different 7★ maps (7.00–7.99★ with mods)";
    const missing = target({ needs });
    const o = (compareBars(all, missing, 6.59, t) as { baseOption: AnyOption }).baseOption;
    const bar = (o.series![1].data as { value: number; label: { formatter?: string } }[])[3];
    expect(bar.value).toBe(100);
    expect(bar.label.formatter).toBe("Not enough data");
    expect(values(o, 0)[3]).toBe(0); // no faded comfort-level bar behind it
    expect(compareHover(all[3], missing, 6.59)).toContain(`To get a score: ${needs}`);
    const measured = compareHover(all[3], target({ score: 55, change: 15, maps: 12 }), 6.59);
    expect(measured).toContain("consistency label at 7.5★: 55 (+15 against your comfort level)");
    expect(measured).toContain("Measured on your 12 different maps from 6.5★ to 7.5★");
  });
});


describe("IRT star levels", () => {
  const irt = (key: string, stars: number | null, low: number | null, high: number | null, state: string, extra: Partial<Schemas["SkillScore"]> = {}) => ({
    ...skill(key, stars === null ? null : 60),
    stars,
    stars_low: low,
    stars_high: high,
    state,
    natural: null,
    natural_unit: null,
    ...extra,
  });
  const skills = [
    irt("aim", 6.6, 6.3, 6.9, "measured"),
    irt("speed", 6.6, 6.2, 7.0, "measured", { natural: 221.4, natural_unit: "BPM" }),
    irt("accuracy", 5.4, 5.0, 5.8, "provisional", { natural: 8.04, natural_unit: "OD" }),
    irt("sliders", 7.4, 7.4, null, "untested"),
    irt("reading", null, null, null, "not_enough_data"),
    skill("consistency", 55),
  ];
  const option = () => (starLevels(skills, t) as { baseOption: AnyOption }).baseOption;

  it("draws each skill at the map star rating it holds up on, without consistency", () => {
    const o = option();
    const bars = o.series![0].data as { value: number | null; label?: { show: boolean; formatter?: string } }[];
    expect(bars.map((b) => b.value)).toEqual([6.6, 6.6, 5.4, 7.4, 9]); // the unmeasured one is a full grey bar
    // one bar a skill, no range drawn behind it (the range is in the hover); BPM/OD/AR: hover only
    expect(o.series!.map((x) => x.type)).toEqual(["bar"]);
    expect(bars.map((b) => (b.label?.show ? b.label.formatter : null))).toEqual(["6.6★", "6.6★", "5.4★", "7.4★+ · limit not found yet", "Not enough data"]);
    // one colour: a skill is measured against the maps themselves, not compared with a star rating
    const colours = (o.series![0].data as { itemStyle: { color: string } }[]).slice(0, 4).map((d) => d.itemStyle.color);
    expect(colours).toEqual([C.accent, C.accent, C.accent, C.accent]);
    expect(o.series!.some((x) => "markLine" in x)).toBe(false);
    // the grey bar is an opaque colour: no grid line shows through it
    expect(faded("#ffffff", 0.25, "#000000")).toBe("rgb(64,64,64)");
    expect((o.xAxis as { min: number; max: number }).min).toBe(4);
    expect(JSON.stringify(o)).not.toContain("typical");
    expect(JSON.stringify(o)).not.toContain("against");
  });

  it("explains what holding up means, without comparing with a star rating", () => {
    const html = starLevelHover(skills[0]);
    expect(html).toContain("aim label: holds up on 6.6★ maps");
    expect(html).toContain("fail only about 2 in 100 of its notes on typical 6.6★ maps");
    expect(html).toContain("Likely between 6.3★ and 6.9★");
    expect(html).not.toContain("short");
    const help = { key: "aim", label: "Jumps", summary: "Hitting notes that are far apart.", what: "W", how: "H", practise: "P" };
    expect(starLevelHover(skills[0], help)).toContain("Hitting notes that are far apart.");
    expect(starLevelHover(skills[2])).toContain("90 in 100 of its single notes as 300s");
    expect(starLevelHover(skills[3])).toContain("sliders label: 7.4★+ (limit not found yet)");
  });
});



describe("goalsChart", () => {
  type Dot = { value: [string, number]; symbolOffset: [number, number]; label: { formatter: string } };
  type Series = { name: string; data: unknown[]; yAxisIndex?: number; markLine?: { data: unknown[] } };
  const goal = (id: string, skill: string, label: string, target: number, deadline = "2026-12-20", unit: "score" | "stars" = "score") => ({
    goal_id: id,
    skill,
    label,
    unit,
    points: [{ day: "2026-11-20", score: target - 10 }],
    target: [{ day: "2026-11-20", score: target - 10 }, { day: deadline, score: target }],
  });

  it("puts the plays and a labelled dot for each goal on one timeline, with today between them", () => {
    const history = [
      {
        goal_id: "g1",
        skill: "speed",
        label: "Tapping speed",
        points: [{ day: "2026-10-18", score: 38 }, { day: "2026-10-20", score: null }, { day: "2026-10-23", score: 23 }],
        target: [{ day: "2026-10-24", score: 66 }, { day: "2026-11-07", score: 70 }],
      },
    ] as Schemas["GoalHistory"][];
    const o = goalsChart(history, chartTheme(true), "2026-10-24") as { xAxis: { type: string }; series: Series[] };
    expect(o.xAxis.type).toBe("time");
    const [speed] = o.series;
    // the plays (a day without a score left out), a gap, then the goal at its target and deadline: no path to it
    expect(speed.data.slice(0, 3)).toEqual([["2026-10-18", 38], ["2026-10-23", 23], [null, null]]);
    const dot = speed.data[3] as Dot;
    expect(dot.value).toEqual(["2026-11-07", 70]);
    expect(dot.label.formatter).toBe("Tapping speed goal");
    expect(speed.markLine?.data).toEqual([{ xAxis: "2026-10-24" }]);
  });

  it("draws one line per skill, with a dot for each of its goals", () => {
    const o = goalsChart(
      [goal("a", "aim", "Jumps", 80, "2026-12-01"), goal("b", "aim", "Jumps", 90), goal("c", "stamina", "Stamina", 60)],
      chartTheme(true),
    ) as { series: Series[] };
    expect(o.series.map((s) => s.name)).toEqual(["Jumps", "Stamina"]);
    expect(o.series[0].data.flatMap((d) => ((d as Dot).label ? [(d as Dot).value] : []))).toEqual([
      ["2026-12-01", 80],
      ["2026-12-20", 90],
    ]);
  });

  it("sets goals close together on the same deadline side by side (a 4-week plan)", () => {
    const plan = [goal("a", "aim", "Jumps", 50), goal("b", "speed", "Tapping speed", 52), goal("c", "stamina", "Stamina", 54), goal("d", "sliders", "Sliders", 80)];
    const offsets = goalOffsets(plan, () => 5);
    expect(["a", "b", "c"].map((id) => offsets.get(id)?.offset)).toEqual([-14, 0, 14]);
    expect(offsets.get("a")?.spread).toBe(14);
    expect(offsets.get("d")).toEqual({ offset: 0, spread: 0 }); // far from the others
    const apart = goalOffsets([goal("a", "aim", "Jumps", 50), goal("b", "speed", "Tapping speed", 50, "2026-12-27")], () => 5);
    expect([apart.get("a")?.offset, apart.get("b")?.offset]).toEqual([0, 0]); // other deadlines
    const o = goalsChart(plan, chartTheme(true)) as { series: (Series & { labelLayout: unknown })[] };
    expect(o.series.every((s) => s.labelLayout === goalLabelLayout)).toBe(true);
    expect(goalLabelLayout({ labelRect: { x: 10, y: 20 } })).toMatchObject({ x: 10, y: 20, moveOverlap: "shiftY" });
    const dot = (s: number) => o.series[s].data.at(-1) as Dot & { label: { distance: number } };
    expect(dot(0).symbolOffset).toEqual([-14, 0]);
    // the labels (left of the dots) all start past the row of dots: none covers a dot
    expect([dot(0), dot(1), dot(2)].map((d) => d.label.distance - d.symbolOffset[0])).toEqual([22, 22, 22]);
  });

  it("puts goals in stars on a star axis, beside the scores when there are both (#129)", () => {
    type Axis = { name: string; min?: number; scale?: boolean };
    const stars = goalsChart([goal("s", "speed", "Tapping speed", 7.3, "2026-12-01", "stars")], chartTheme(true)) as { yAxis: Axis };
    expect(stars.yAxis.name).toBe("★");
    expect(stars.yAxis.scale).toBe(true);
    const both = goalsChart([goal("c", "consistency", "Consistency", 44), goal("s", "speed", "Tapping speed", 7.3, "2026-12-01", "stars")], chartTheme(true)) as {
      yAxis: Axis[];
      series: Series[];
    };
    expect(both.yAxis.map((a) => a.name)).toEqual(["★", "score"]);
    expect(both.series.map((s) => s.yAxisIndex)).toEqual([1, 0]);
  });
});

describe("a skill the maps haven't tested to its limit", () => {
  it("shows its lower bound at the comfort level as a light bar, and its hover says what to play", () => {
    const needs = "play maps with longer streams or dense 1/4 sections";
    const stamina = { ...skill("stamina", null, needs, 41), score_text: "at least 41 · your maps haven't tested it to its limit yet" };
    const comfort: Schemas["CompareTarget"] = {
      stars: 4.8,
      comfort: true,
      locked: false,
      skills: [{ key: "stamina", score: null, change: null, demand: null, maps: null, needs: null }],
      weakest: null,
      pass_chance: null,
    };
    const o = (compareBars([stamina], comfort, 4.8, t) as { baseOption: AnyOption }).baseOption;
    const bar = (o.series![1].data as { value: number; itemStyle: { color: string } }[])[0];
    expect(bar.value).toBe(41);
    expect(bar.itemStyle.color).toBe(alpha(scoreColor(41), 0.35));
    const label = (o.series![1].label as { formatter: (p: unknown) => string }).formatter([{ dataIndex: 0 }]);
    expect(label).toBe("≥ 41");
    expect(compareHover(stamina, comfort, 4.8)).toContain(`To see your full score: ${needs}`);
  });
});

describe("progress charts start where their data does", () => {
  const row = (key: string, extra: Partial<Schemas["PeriodRow"]> = {}): Schemas["PeriodRow"] => ({
    key,
    plays: 3,
    maps: 3,
    new_maps: 3,
    minutes: 10,
    comfort_stars: null,
    avg_stars: null,
    max_stars_passed: null,
    max_stars_fc: null,
    accuracy: 0.9,
    misses_per_100: 3,
    ur: null,
    stream_bpm: null,
    few_plays: true,
    skills: { aim: null },
    ...extra,
  });
  // plays saved since 2017, skill scores only from 2021-07 (months with 5+ plays)
  const rows = [row("2017-11"), row("2017-12"), row("2021-07", { skills: { aim: 66 }, comfort_stars: 5.5 }), row("2021-08", { skills: { aim: 67 } })];
  const keys = (o: AnyOption) => (o.xAxis as { data: string[] }).data;

  it("skills by month: from the first month with a skill score", () => {
    expect(keys(skillsChart(rows, [{ key: "aim", label: "Jump aim" }], t) as AnyOption)).toEqual(["2021-07", "2021-08"]);
  });

  it("star rating by month: from the first month with a star rating", () => {
    expect(keys(starsChart(rows, t) as AnyOption)).toEqual(["2021-07", "2021-08"]);
  });

  it("no values at all: an empty chart, not empty months", () => {
    expect(keys(skillsChart([row("2017-11")], [{ key: "aim", label: "Jump aim" }], t) as AnyOption)).toEqual([]);
  });

  it("Star Levels: the star levels by month, their range on hover", () => {
    const levels = [
      row("2021-06"),
      row("2021-07", { star_levels: { aim: { stars: 6.4, low: 6.1, high: 6.7 } } }),
      row("2021-08", { star_levels: { aim: { stars: 6.6, low: 6.3, high: 6.9 } } }),
    ];
    const o = starLevelsChart(levels, [{ key: "aim", label: "Jump aim" }, { key: "speed", label: "Speed" }], t) as AnyOption;
    expect(keys(o)).toEqual(["2021-07", "2021-08"]);
    const series = o.series as { name: string; data: { value: number | null }[] }[];
    expect(series.map((s) => s.name)).toEqual(["Jump aim"]); // no level of speed: no line
    expect(series[0].data.map((d) => d.value)).toEqual([6.4, 6.6]);
    const tip = (o.tooltip as { formatter: (p: unknown[]) => string }).formatter([
      { seriesName: "Jump aim", dataIndex: 1, value: 6.6, marker: "" },
    ]);
    expect(tip).toBe("2021-08<br/>Jump aim: 6.60★ (6.30–6.90)");
  });
});

