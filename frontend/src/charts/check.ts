import type { Schemas } from "../api/client";
import { esc } from "../lib/format";
import { base, grid, legend, niceMax, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, RESULT_COLORS, type ChartTheme } from "./palette";
import { params } from "./types";

const X_MARK = "path://M2,0L5,3L8,0L10,2L7,5L10,8L8,10L5,7L2,10L0,8L3,5L0,2Z";

/** mm:ss of a map time in ms. */
export function mmss(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Timing through the map: every hit by result, the running average, the 300 window, misses / breaks on top. */
export function playTimingChart(tm: Schemas["PlayTiming"], t: ChartTheme): Option {
  const byResult = (res: number) => tm.time.flatMap((x, i) => (tm.result[i] === res ? [[x, tm.error[i]]] : []));
  const top = tm.top;
  const misses = tm.marks.filter((m) => m.what === "miss");
  const breaks = tm.marks.filter((m) => m.what !== "miss");
  const windowLines =
    tm.window_300 !== null
      ? {
          silent: true,
          symbol: "none",
          label: { show: false },
          lineStyle: { color: t.muted, type: "dotted" },
          data: [{ yAxis: tm.window_300 }, { yAxis: -tm.window_300 }],
        }
      : undefined;
  return base(t, {
    grid: grid({ bottom: 78 }),
    legend: legend(t, { bottom: 0 }),
    tooltip: tooltip(t, {
      trigger: "item",
      formatter: (p: unknown) => {
        const q = params(p)[0];
        if (q.seriesName === "misses") return esc(misses[q.dataIndex].label);
        if (q.seriesName === "combo breaks") return esc(breaks[q.dataIndex].label);
        const v = q.value as [number, number];
        return `${mmss(v[0])} · ${v[1] >= 0 ? "+" : "−"}${Math.abs(v[1]).toFixed(1)} ms (${esc(q.seriesName ?? "")})`;
      },
    }),
    dataZoom: [
      { type: "inside", xAxisIndex: 0, filterMode: "none" },
      {
        type: "slider",
        xAxisIndex: 0,
        filterMode: "none",
        height: 22,
        bottom: 30,
        borderColor: t.line,
        fillerColor: "rgba(255,102,170,0.15)",
        handleStyle: { color: C.accent },
        textStyle: { color: t.muted },
        labelFormatter: (v: number) => mmss(v),
        dataBackground: { lineStyle: { color: t.muted }, areaStyle: { color: t.split } },
      },
    ],
    xAxis: valueAxis(t, {
      min: 0,
      max: Math.ceil(tm.length_ms / 1000) * 1000,
      axisLabel: { formatter: (v: number) => mmss(v) },
      splitLine: { show: false },
    }),
    yAxis: valueAxis(t, {
      name: "hit error, ms (− early, + late)",
      nameGap: 40,
      nameRotate: 90,
      min: -niceMax(top, 10, 1.08),
      max: niceMax(top, 10, 1.08),
    }),
    series: [
      ...[300, 100, 50].map((res, i) => ({
        name: String(res),
        type: "scatter",
        data: byResult(res),
        symbolSize: 4,
        itemStyle: { color: RESULT_COLORS[res], opacity: 0.65 },
        markLine: i === 0 ? windowLines : undefined,
        large: true,
      })),
      {
        name: "running average",
        type: "line",
        data: tm.time.map((x, i) => [x, tm.trend[i]]),
        showSymbol: false,
        connectNulls: true,
        lineStyle: { color: C.accent, width: 2.5 },
        itemStyle: { color: C.accent },
        silent: true,
        z: 4,
      },
      {
        name: "misses",
        type: "scatter",
        data: misses.map((m) => [m.time, top]),
        symbol: X_MARK,
        symbolSize: 11,
        itemStyle: { color: C.missRed },
        z: 5,
      },
      {
        name: "combo breaks",
        type: "scatter",
        data: breaks.map((m) => [m.time, top]),
        symbol: "triangle",
        symbolRotate: 180,
        symbolSize: 9,
        itemStyle: { color: C.warn },
        z: 5,
      },
    ],
  });
}

/** Hits, average error, UR and misses / breaks between two map times (the zoomed part). */
export function rangeStats(tm: Schemas["PlayTiming"], from: number, to: number) {
  const errs = tm.error.filter((_, i) => tm.time[i] >= from && tm.time[i] <= to);
  const n = errs.length;
  const mean = n ? errs.reduce((a, b) => a + b, 0) / n : null;
  const sd = n > 1 && mean !== null ? Math.sqrt(errs.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1)) : null;
  const marks = tm.marks.filter((m) => m.time >= from && m.time <= to).length;
  return { n, mean, ur: sd === null ? null : sd * 10, marks };
}
