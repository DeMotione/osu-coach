import type { Schemas } from "../api/client";
import { base, circle, grid, legend, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, INK, type ChartTheme } from "./palette";

const X_MARK = "path://M2,0L5,3L8,0L10,2L7,5L10,8L8,10L5,7L2,10L0,8L3,5L0,2Z";
const CLICK_RANGE = 2.4;

/** Where clicks land, in circle radii (y down, as on screen); the circle and half its radius drawn in. */
export function clicksChart(c: Schemas["Clicks"], t: ChartTheme): Option {
  const hits: [number, number][] = [];
  const misses: [number, number][] = [];
  c.x.forEach((x, i) => (c.hit[i] ? hits : misses).push([x, c.y[i]]));
  const few = c.drawn <= 300;
  const mean = c.summary?.mean_r ?? [null, null];
  const ticks = [-2, -1, 0, 1, 2];
  const axis = {
    min: -CLICK_RANGE,
    max: CLICK_RANGE,
    splitLine: { show: false },
    axisLine: { onZero: false },
    axisLabel: { customValues: ticks },
    axisTick: { show: true, customValues: ticks },
  };
  const ring = (r: number, dashed: boolean) => ({
    type: "line",
    data: circle(r),
    showSymbol: false,
    silent: true,
    lineStyle: { color: t.muted, width: dashed ? 1 : 2, type: dashed ? "dashed" : "solid" },
    z: 4,
    tooltip: { show: false },
  });
  return base(t, {
    grid: grid({ left: 6, right: 10, top: 10 }, true),
    legend: legend(t, { data: ["hit", "aim miss", "average"] }),
    tooltip: { show: false },
    xAxis: valueAxis(t, {
      ...axis,
      name: c.view === "movement" ? "circle radii · overshoot →" : "circle radii",
      nameGap: 24,
    }),
    yAxis: valueAxis(t, { ...axis, inverse: true }),
    series: [
      {
        name: "hit",
        type: "scatter",
        data: hits,
        symbolSize: few ? 7 : 3,
        itemStyle: { color: C.accent, opacity: few ? 0.75 : 0.35 },
        large: hits.length > 2000,
        silent: true,
      },
      {
        name: "aim miss",
        type: "scatter",
        data: misses,
        symbolSize: few ? 8 : 5,
        itemStyle: { color: C.yellow, opacity: 0.9 },
        silent: true,
      },
      ring(1, false),
      ring(0.5, true),
      {
        name: "average",
        type: "scatter",
        data: mean[0] !== null && mean[1] !== null ? [[mean[0], mean[1]]] : [],
        symbol: X_MARK,
        symbolSize: 14,
        itemStyle: { color: C.info, borderColor: INK, borderWidth: 1 },
        z: 6,
        silent: true,
      },
    ],
  });
}

