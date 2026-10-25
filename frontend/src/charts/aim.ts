import type { Schemas } from "../api/client";
import { esc } from "../lib/format";
import { base, categoryAxis, circle, grid, legend, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, INK, type ChartTheme } from "./palette";
import { params } from "./types";

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

/** Miss rate by the direction the cursor moves to reach the note: one wedge per direction. */
export function directionsChart(rows: Schemas["DirectionRow"][], t: ChartTheme): Option {
  const order = [...rows].sort((a, b) => a.angle - b.angle);       // right, up-right, up, … counter-clockwise
  return base(t, {
    polar: { radius: ["0%", "72%"], center: ["50%", "52%"] },
    angleAxis: {
      type: "category",
      data: order.map((r) => r.direction),
      startAngle: -22.5,      // the first wedge ("right") from -22.5° to 22.5°: centred on 0°
      clockwise: false,
      axisLine: { lineStyle: { color: t.line } },
      axisTick: { show: false },
      axisLabel: { color: t.text, fontSize: 12 },
      splitLine: { show: true, lineStyle: { color: t.split } },
    },
    radiusAxis: {
      type: "value",
      axisLabel: { show: false },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: t.split } },
    },
    tooltip: tooltip(t, {
      trigger: "item",
      formatter: (p: unknown) => {
        const r = order[params(p)[0].dataIndex];
        const rate = r.miss_rate === null ? "–" : `${(r.miss_rate * 100).toFixed(1)}%`;
        return `moving ${esc(r.direction)}: ${rate} misses (${Math.round(r.objects)} jumps)`;
      },
    }),
    series: [
      {
        type: "bar",
        coordinateSystem: "polar",
        data: order.map((r) => (r.miss_rate === null ? 0 : +(r.miss_rate * 100).toFixed(2))),
        itemStyle: { color: C.accent, opacity: 0.85 },
        barCategoryGap: "6%",
      },
    ],
  });
}

/** Miss rate by jump distance (bars) and over / undershoot along the jump (line, right axis). */
export function distanceChart(rows: Schemas["DistanceRow"][], t: ChartTheme): Option {
  return base(t, {
    grid: grid({ right: 8 }, true),
    legend: legend(t),
    tooltip: tooltip(t, {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: t.split } },
      formatter: (p: unknown) => {
        const r = rows[params(p)[0].dataIndex];
        const rate = r.miss_rate === null ? "–" : `${(r.miss_rate * 100).toFixed(1)}%`;
        const along = r.along === null ? "–" : `${r.along >= 0 ? "+" : "−"}${Math.abs(r.along).toFixed(2)} radii`;
        return `<b>${esc(r.bin)} circle diameters</b><br>miss rate ${rate} · ${Math.round(r.objects)} notes<br>over(+)/under(−)shoot ${along}`;
      },
    }),
    xAxis: categoryAxis(
      t,
      rows.map((r) => r.bin),
      { name: "distance from the previous note (circle diameters)", nameGap: 26 },
    ),
    yAxis: [
      valueAxis(t, { name: "miss rate %", nameGap: 36, nameRotate: 90 }),
      valueAxis(t, {
        name: "over(+)/under(−)shoot, radii",
        nameGap: 40,
        nameRotate: -90,
        position: "right",
        splitLine: { show: false },
        axisLabel: { formatter: (v: number) => v.toFixed(2) },
      }),
    ],
    series: [
      {
        name: "miss rate",
        type: "bar",
        barMaxWidth: 42,
        data: rows.map((r) => (r.miss_rate === null ? null : +(r.miss_rate * 100).toFixed(2))),
        itemStyle: { color: C.accent, borderRadius: [3, 3, 0, 0] },
      },
      {
        name: "over/undershoot",
        type: "line",
        yAxisIndex: 1,
        data: rows.map((r) => r.along),
        lineStyle: { color: C.info, width: 2.5 },
        itemStyle: { color: C.info },
        symbolSize: 7,
        markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: t.muted, type: "dashed" }, data: [{ yAxis: 0 }] },
      },
    ],
  });
}
