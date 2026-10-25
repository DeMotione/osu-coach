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

/** The goal skills on a real timeline (a time axis: two weeks are twice as wide as one), the plays so far and each
 * goal's path to its deadline, with today marked between them. ``today``: YYYY-MM-DD. */
export function goalsChart(history: Schemas["GoalHistory"][], t: ChartTheme, today = localDay()): Option {
  const pairs = (pts: Schemas["HistoryPoint"][]) => pts.filter((p) => p.score !== null).map((p) => [p.day, p.score]);
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, { trigger: "axis", valueFormatter: (v: number | null) => (v === null || v === undefined ? "–" : v.toFixed(0)) }),
    xAxis: valueAxis(t, { type: "time", splitLine: { show: false }, axisLabel: { formatter: "{MMM} {d}", hideOverlap: true } }),
    yAxis: valueAxis(t, { name: "score", nameGap: 32, nameRotate: 90, min: 0, max: 100 }),
    series: history.flatMap((h, i) => {
      const color = SERIES[i % SERIES.length];
      return [
        {
          name: h.label,
          type: "line",
          data: pairs(h.points),
          symbolSize: 7,
          lineStyle: { color, width: 2 },
          itemStyle: { color },
          ...(i === 0 ? { markLine: refLine(t, { xAxis: today }, t.muted, { label: { show: true, formatter: "today", color: t.muted } }) } : {}),
        },
        {
          name: `${h.label} target`,
          type: "line",
          data: pairs(h.target),
          showSymbol: false,
          lineStyle: { color, width: 1, type: "dotted" },
          itemStyle: { color },
        },
      ];
    }),
  });
}

function localDay(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
