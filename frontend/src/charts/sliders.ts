import type { Schemas } from "../api/client";
import { base, categoryAxis, grid, legend, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, type ChartTheme } from "./palette";
import { params } from "./types";

const shadow = (t: ChartTheme) => ({ type: "shadow", shadowStyle: { color: t.split } });

export function arMissChart(rows: Schemas["ArMissRow"][], t: ChartTheme): Option {
  return base(t, {
    grid: grid(),
    tooltip: tooltip(t, {
      trigger: "axis",
      axisPointer: shadow(t),
      formatter: (p: unknown) => {
        const r = rows[params(p)[0].dataIndex];
        return `AR ${r.ar}: ${r.miss_rate === null ? "–" : (r.miss_rate * 100).toFixed(2)}% missed · ${Math.round(r.objects)} notes`;
      },
    }),
    xAxis: categoryAxis(
      t,
      rows.map((r) => r.ar),
      { name: "approach rate (AR, with mods)", nameGap: 26 },
    ),
    yAxis: valueAxis(t, { name: "miss rate %", nameGap: 40, nameRotate: 90, min: 0 }),
    series: [
      {
        type: "bar",
        barMaxWidth: 48,
        data: rows.map((r) => (r.miss_rate === null ? null : +(r.miss_rate * 100).toFixed(3))),
        itemStyle: { color: C.info, borderRadius: [5, 5, 0, 0] },
      },
    ],
  });
}

export function sliderRatesChart(r: Schemas["SliderRates"], axisName: string, t: ChartTheme): Option {
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, {
      trigger: "axis",
      axisPointer: shadow(t),
      formatter: (p: unknown) => {
        const b = r.rows[params(p)[0].dataIndex];
        return `<b>${b.bin}</b> · ${b.n} sliders<br>head missed ${b.head.toFixed(1)}%<br>broke later ${b.broke.toFixed(1)}%`;
      },
    }),
    xAxis: categoryAxis(
      t,
      r.rows.map((b) => b.bin),
      { name: axisName, nameGap: 26 },
    ),
    yAxis: valueAxis(t, { name: "% of these sliders", nameGap: 40, nameRotate: 90, min: 0 }),
    series: [
      { name: "head missed", type: "bar", stack: "s", barMaxWidth: 48, data: r.rows.map((b) => +b.head.toFixed(2)), itemStyle: { color: C.missRed } },
      {
        name: "broke later",
        type: "bar",
        stack: "s",
        data: r.rows.map((b) => +b.broke.toFixed(2)),
        itemStyle: { color: C.warn, borderRadius: [5, 5, 0, 0] },
      },
    ],
  });
}

export function hitsByArChart(rows: Schemas["HitsByAr"][], t: ChartTheme): Option {
  const low = Math.max(0, Math.floor(Math.min(...rows.map((r) => r.r300)) - 10));
  const parts = [
    ["300", "r300", C.good],
    ["100", "r100", C.info],
    ["50", "r50", C.yellow],
    ["miss", "miss", C.missRed],
  ] as const;
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, { trigger: "axis", axisPointer: shadow(t), valueFormatter: (v: number) => `${v.toFixed(1)}%` }),
    xAxis: categoryAxis(
      t,
      rows.map((r) => `AR ${r.ar}`),
    ),
    yAxis: valueAxis(t, { name: "% of notes", nameGap: 40, nameRotate: 90, min: low, max: 100 }),
    series: parts.map(([name, key, color], i) => ({
      name,
      type: "bar",
      stack: "r",
      barMaxWidth: 56,
      data: rows.map((r) => +r[key].toFixed(2)),
      itemStyle: { color, borderRadius: i === parts.length - 1 ? [5, 5, 0, 0] : 0 },
    })),
  });
}
