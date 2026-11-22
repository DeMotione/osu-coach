import type { Schemas } from "../api/client";
import { base, categoryAxis, grid, legend, refLine, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, SERIES, type ChartTheme } from "./palette";

type Row = Schemas["PeriodRow"];

/** The periods from the first one with a value on: a chart starts where its data does, not at the first play. */
export function fromFirstValue(rows: Row[], hasValue: (r: Row) => boolean): Row[] {
  const first = rows.findIndex(hasValue);
  return first < 0 ? [] : rows.slice(first);
}

/** Hollow points for periods with few plays (rough numbers). */
const points = (rows: Row[], key: keyof Row) =>
  rows.map((r) => ({ value: r[key] as number | null, symbol: r.few_plays ? "emptyCircle" : "circle" }));

export function starsChart(all: Row[], t: ChartTheme): Option {
  const lines: [keyof Row, string, string, number][] = [
    ["comfort_stars", "comfort", C.accent, 3],
    ["avg_stars", "average played", t.muted, 1.5],
    ["max_stars_passed", "hardest clean pass", C.info, 1.5],
    ["max_stars_fc", "hardest full combo", C.good, 1.5],
  ];
  const rows = fromFirstValue(all, (r) => lines.some(([key]) => r[key] !== null));
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, { trigger: "axis", valueFormatter: (v: number | null) => (v === null || v === undefined ? "–" : `${v.toFixed(2)}★`) }),
    xAxis: categoryAxis(
      t,
      rows.map((r) => r.key),
      { boundaryGap: false },
    ),
    yAxis: valueAxis(t, { name: "star rating ★", nameGap: 40, nameRotate: 90, scale: true }),
    series: lines.map(([key, name, color, width]) => ({
      name,
      type: "line",
      data: points(rows, key),
      connectNulls: true,
      symbolSize: 8,
      lineStyle: { color, width },
      itemStyle: { color },
    })),
  });
}

export function playedChart(rows: Row[], t: ChartTheme): Option {
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, { trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: t.split } } }),
    xAxis: categoryAxis(
      t,
      rows.map((r) => r.key),
    ),
    yAxis: [
      valueAxis(t, { name: "plays / maps", nameGap: 36, nameRotate: 90, min: 0 }),
      valueAxis(t, { name: "minutes", nameGap: 36, nameRotate: -90, position: "right", min: 0, splitLine: { show: false } }),
    ],
    series: [
      { name: "plays", type: "bar", barMaxWidth: 26, data: rows.map((r) => r.plays), itemStyle: { color: C.accent, borderRadius: [3, 3, 0, 0] } },
      { name: "new maps", type: "bar", barMaxWidth: 26, data: rows.map((r) => r.new_maps), itemStyle: { color: C.info, borderRadius: [3, 3, 0, 0] } },
      {
        name: "minutes played",
        type: "line",
        yAxisIndex: 1,
        data: rows.map((r) => (r.minutes === null ? null : Math.round(r.minutes))),
        lineStyle: { color: C.good, width: 2 },
        itemStyle: { color: C.good },
        symbolSize: 7,
      },
    ],
  });
}

export function skillsChart(all: Row[], skills: { key: string; label: string }[], t: ChartTheme): Option {
  const rows = fromFirstValue(all, (r) => skills.some((s) => r.skills[s.key] !== null && r.skills[s.key] !== undefined));
  const shown = skills.filter((s) => rows.some((r) => r.skills[s.key] !== null && r.skills[s.key] !== undefined));
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, { trigger: "axis", valueFormatter: (v: number | null) => (v === null || v === undefined ? "–" : v.toFixed(0)) }),
    xAxis: categoryAxis(
      t,
      rows.map((r) => r.key),
      { boundaryGap: false },
    ),
    yAxis: valueAxis(t, { name: "score", nameGap: 32, nameRotate: 90, min: 0, max: 100 }),
    series: shown.map((s, i) => ({
      name: s.label,
      type: "line",
      data: rows.map((r) => ({ value: r.skills[s.key] ?? null, symbol: r.few_plays ? "emptyCircle" : "circle" })),
      connectNulls: true,
      symbolSize: 8,
      lineStyle: { width: 2, color: SERIES[i % SERIES.length] },
      itemStyle: { color: SERIES[i % SERIES.length] },
    })),
  });
}

/** Star Levels: each skill's star level by period (the star rating it holds up on, fitted to the period's plays); the
 * tooltip gives its 90% range. */
export function starLevelsChart(all: Row[], skills: { key: string; label: string }[], t: ChartTheme): Option {
  const level = (r: Row, key: string) => r.star_levels?.[key]?.stars ?? null;
  const rows = fromFirstValue(all, (r) => skills.some((s) => level(r, s.key) !== null));
  const shown = skills.filter((s) => rows.some((r) => level(r, s.key) !== null));
  const range = (r: Row, key: string) => {
    const l = r.star_levels?.[key];
    return l?.low != null && l.high != null ? ` (${l.low.toFixed(2)}–${l.high.toFixed(2)})` : "";
  };
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, {
      trigger: "axis",
      formatter: (params: { seriesName: string; dataIndex: number; value: number | null; marker: string }[]) => {
        const lines = params.map((p) => {
          const skill = shown.find((s) => s.label === p.seriesName);
          const r = rows[p.dataIndex];
          return `${p.marker}${p.seriesName}: ${p.value === null || p.value === undefined ? "–" : `${p.value.toFixed(2)}★`}${skill && r ? range(r, skill.key) : ""}`;
        });
        return [rows[params[0]?.dataIndex ?? 0]?.key ?? "", ...lines].join("<br/>");
      },
    }),
    xAxis: categoryAxis(
      t,
      rows.map((r) => r.key),
      { boundaryGap: false },
    ),
    yAxis: valueAxis(t, { name: "★", nameGap: 32, nameRotate: 90, scale: true }),
    series: shown.map((s, i) => ({
      name: s.label,
      type: "line",
      data: rows.map((r) => ({ value: level(r, s.key), symbol: r.few_plays ? "emptyCircle" : "circle" })),
      connectNulls: true,
      symbolSize: 8,
      lineStyle: { width: 2, color: SERIES[i % SERIES.length] },
      itemStyle: { color: SERIES[i % SERIES.length] },
    })),
  });
}

type Goal = Schemas["GoalHistory"];

/** Where a goal is to be: its target at its deadline (the end of its path). */
const goalPoint = (h: Goal) => h.target.at(-1);

const DOT_GAP = 14; // px between goal dots side by side

/** Goal labels that would overlap move apart up or down (a line leads to the dot). Pinned where they are first: a label
 * left at its place beside the dot is put back there on the next redraw, losing the move. */
export const goalLabelLayout = (p: { labelRect: { x: number; y: number } }) => ({
  x: p.labelRect.x,
  y: p.labelRect.y,
  align: "left",
  verticalAlign: "top",
  moveOverlap: "shiftY",
});

/** Goal dots that would sit on each other (the same axis and deadline, targets closer than ``near`` in the axis' unit)
 * go side by side: each one's sideways ``offset`` (px) and the ``spread`` of its row each way from the middle. A 4-week
 * plan sets its goals on one day, with targets often a few points apart. */
export function goalOffsets(history: Goal[], near: (unit: string) => number): Map<string, { offset: number; spread: number }> {
  const groups = new Map<string, Goal[]>();
  for (const h of history) {
    const at = goalPoint(h);
    if (at === undefined || at.score === null) continue;
    const key = `${h.unit ?? "score"} ${at.day}`;
    groups.set(key, [...(groups.get(key) ?? []), h]);
  }
  const target = (h: Goal) => goalPoint(h)?.score ?? 0;
  const out = new Map<string, { offset: number; spread: number }>();
  for (const group of groups.values()) {
    group.sort((a, b) => target(a) - target(b));
    let cluster: Goal[] = [];
    const flush = () => {
      const spread = ((cluster.length - 1) / 2) * DOT_GAP;
      cluster.forEach((h, i) => out.set(h.goal_id, { offset: i * DOT_GAP - spread, spread }));
      cluster = [];
    };
    for (const h of group) {
      const last = cluster.at(-1);
      if (last && target(h) - target(last) >= near(h.unit ?? "score")) flush();
      cluster.push(h);
    }
    flush();
  }
  return out;
}

/** The goal skills on a real timeline (a time axis: two weeks are twice as wide as one): one line per skill (the plays
 * so far) and a labelled dot for each goal at its target and deadline, with today marked. Dots that would sit on each
 * other go side by side and labels that would overlap move apart; hovering a skill brings it forward.
 * ``today``: YYYY-MM-DD. */
export function goalsChart(history: Goal[], t: ChartTheme, today = localDay()): Option {
  const pairs = (pts: Schemas["HistoryPoint"][]) => pts.filter((p) => p.score !== null).map((p) => [p.day, p.score]);
  // goals in stars (Star Levels, #129) on a star axis; scores (and consistency there) on the 0–100 one
  const units = [...new Set(history.map((h) => h.unit ?? "score"))].sort((a, b) => (a === "stars" ? -1 : b === "stars" ? 1 : 0));
  const axis = (unit: string, i: number) =>
    unit === "stars"
      ? valueAxis(t, { name: "★", nameGap: 32, nameRotate: 90, scale: true, position: i ? "right" : "left", axisLabel: { formatter: (v: number) => `${v}★` } })
      : valueAxis(t, { name: "score", nameGap: 32, nameRotate: 90, min: 0, max: 100, position: i ? "right" : "left", ...(i ? { splitLine: { show: false } } : {}) });
  const shown = (unit: string) => (v: number | null) => (v === null || v === undefined ? "–" : unit === "stars" ? `${v.toFixed(2)}★` : v.toFixed(0));
  // one line per skill: a reached goal and the next one for the same skill share it
  const bySkill = new Map<string, Goal[]>();
  for (const h of history) bySkill.set(h.skill, [...(bySkill.get(h.skill) ?? []), h]);
  // "close" dots: 5 points on the score axis, 5% of the stars shown on the star axis
  const stars = history.filter((h) => h.unit === "stars").flatMap((h) => [...h.points, ...h.target].flatMap((p) => (p.score === null ? [] : [p.score])));
  const starSpan = stars.length ? Math.max(Math.max(...stars) - Math.min(...stars), 0.5) : 1;
  const offsets = goalOffsets(history, (unit) => (unit === "stars" ? starSpan * 0.05 : 5));
  // a label goes on the side of its dot with more room
  const days = history.flatMap((h) => [...h.points, ...h.target].map((p) => Date.parse(p.day)));
  const middle = days.length ? (Math.min(...days) + Math.max(...days)) / 2 : 0;
  return base(t, {
    grid: grid(units.length > 1 ? { right: 56 } : {}, true),
    legend: legend(t),
    tooltip: tooltip(t, { trigger: "axis" }),
    // a little room before the first day and after the last deadline, for their dots
    xAxis: valueAxis(t, {
      type: "time",
      min: (e: { min: number; max: number }) => e.min - (e.max - e.min) * 0.03,
      max: (e: { min: number; max: number }) => e.max + (e.max - e.min) * 0.03,
      splitLine: { show: false },
      axisLabel: { formatter: "{MMM} {d}", hideOverlap: true },
    }),
    yAxis: units.length > 1 ? units.map(axis) : axis(units[0] ?? "score", 0),
    series: [...bySkill.values()].map((goals, i) => {
      const color = SERIES[i % SERIES.length];
      const unit = goals[0].unit ?? "score";
      const line = pairs(goals[0].points);
      const dots = goals.flatMap((g) => {
        const at = goalPoint(g);
        if (at === undefined || at.score === null) return [];
        const { offset, spread } = offsets.get(g.goal_id) ?? { offset: 0, spread: 0 };
        const right = Date.parse(at.day) < middle;
        // a gap first ([null, null]: on no day, so never in the tooltip), so the line doesn't run on to the dot
        return [
          [null, null],
          {
            value: [at.day, at.score],
            symbol: "diamond",
            symbolSize: 15,
            symbolOffset: [offset, 0],
            itemStyle: { color, borderColor: t.surface, borderWidth: 1.5 },
            label: {
              show: true,
              position: right ? "right" : "left",
              distance: 8 + spread + (right ? -offset : offset), // past the whole row of dots, not over one of them
              formatter: `${g.label} goal`,
              color,
              fontSize: 11.5,
              fontWeight: 600,
              backgroundColor: t.surface,
              padding: [2, 5],
              borderRadius: 4,
            },
          },
        ];
      });
      return {
        name: goals[0].label,
        type: "line",
        data: [...line, ...dots],
        symbolSize: 7,
        lineStyle: { color, width: 2 },
        itemStyle: { color },
        emphasis: { focus: "series" },
        labelLayout: goalLabelLayout,
        labelLine: { show: true, lineStyle: { color, width: 1, opacity: 0.7 } },
        tooltip: { valueFormatter: (v: number | null, index: number) => (index >= line.length ? `goal ${shown(unit)(v)}` : shown(unit)(v)) },
        ...(units.length > 1 ? { yAxisIndex: units.indexOf(unit) } : {}),
        ...(i === 0 ? { markLine: refLine(t, { xAxis: today }, t.muted, { label: { show: true, formatter: "today", color: t.muted } }) } : {}),
      };
    }),
  });
}

function localDay(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
