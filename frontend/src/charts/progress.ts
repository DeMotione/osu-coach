import type { Schemas } from "../api/client";
import { base, categoryAxis, grid, legend, refLine, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, SERIES, type ChartTheme } from "./palette";

type Row = Schemas["PeriodRow"];

/** Hollow points for periods with few plays (rough numbers). */
const points = (rows: Row[], key: keyof Row) =>
  rows.map((r) => ({ value: r[key] as number | null, symbol: r.few_plays ? "emptyCircle" : "circle" }));

export function starsChart(rows: Row[], t: ChartTheme): Option {
  const lines: [keyof Row, string, string, number][] = [
    ["comfort_stars", "comfort", C.accent, 3],
    ["avg_stars", "average played", t.muted, 1.5],
    ["max_stars_passed", "hardest clean pass", C.info, 1.5],
    ["max_stars_fc", "hardest full combo", C.good, 1.5],
  ];
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
      { name: "plays", type: "bar", barMaxWidth: 26, data: rows.map((r) => r.plays), itemStyle: { color: C.accent, borderRadius: [4, 4, 0, 0] } },
      { name: "new maps", type: "bar", barMaxWidth: 26, data: rows.map((r) => r.new_maps), itemStyle: { color: C.info, borderRadius: [4, 4, 0, 0] } },
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

export function skillsChart(rows: Row[], skills: { key: string; label: string }[], t: ChartTheme): Option {
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
      markLine: i === 0 ? refLine(t, { yAxis: 50 }) : undefined,
    })),
  });
}

export function goalsChart(history: Schemas["GoalHistory"][], t: ChartTheme): Option {
  const days = [...new Set(history.flatMap((h) => [...h.points.map((p) => p.day), ...h.target.map((p) => p.day)]))].sort();
  const at = (pts: Schemas["HistoryPoint"][]) => {
    const m = new Map(pts.map((p) => [p.day, p.score]));
    return days.map((d) => (m.has(d) ? m.get(d)! : null));
  };
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, { trigger: "axis", valueFormatter: (v: number | null) => (v === null || v === undefined ? "–" : v.toFixed(0)) }),
    xAxis: categoryAxis(t, days, { boundaryGap: false }),
    yAxis: valueAxis(t, { name: "score", nameGap: 32, nameRotate: 90, min: 0, max: 100 }),
    series: history.flatMap((h, i) => {
      const color = SERIES[i % SERIES.length];
      return [
        { name: h.label, type: "line", data: at(h.points), connectNulls: true, symbolSize: 7, lineStyle: { color, width: 2 }, itemStyle: { color } },
        {
          name: `${h.label} target`,
          type: "line",
          data: at(h.target),
          connectNulls: true,
          showSymbol: false,
          lineStyle: { color, width: 1, type: "dotted" },
          itemStyle: { color },
        },
      ];
    }),
  });
}
