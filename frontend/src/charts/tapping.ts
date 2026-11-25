import type { Schemas } from "../api/client";
import { esc } from "../lib/format";
import { base, categoryAxis, grid, legend, refLine, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { MIN_NOTES } from "../lib/verdict";
import { C, faded, RESULT_COLORS, SERIES, type ChartTheme } from "./palette";
import { params } from "./types";

export type TimingScale = "normal" | "zoom" | "log";

const nearest = (values: number[], v: number) =>
  values.reduce((best, x, i) => (Math.abs(x - v) < Math.abs(values[best] - v) ? i : best), 0);

/** How early or late each hit was, stacked by result (300 / 100 / 50); hover shows the three at that ms. */
export function timingChart(h: Schemas["TimingHistogram"], scale: TimingScale, zoomShare: number, t: ChartTheme): Option {
  const cats = h.centers.map((c) => String(c));
  const series = ([
    ["300", h.n300, RESULT_COLORS[300]],
    ["100", h.n100, RESULT_COLORS[100]],
    ["50", h.n50, RESULT_COLORS[50]],
  ] as const).map(([name, data, color]) => ({
    name,
    type: "bar",
    stack: "hits",
    barCategoryGap: 0,
    data: scale === "log" ? data.map((v) => (v > 0 ? v : null)) : data,
    itemStyle: { color },
  }));
  const peak = Math.max(...h.centers.map((_, i) => h.n300[i] + h.n100[i] + h.n50[i]), 1);
  const marks = [{ xAxis: cats[nearest(h.centers, 0)], lineStyle: { color: t.muted, type: "solid" } }];
  if (h.mean !== null) marks.push({ xAxis: cats[nearest(h.centers, h.mean)], lineStyle: { color: C.accent, type: "dashed" } });
  series[0] = { ...series[0], markLine: { silent: true, symbol: "none", label: { show: false }, data: marks } } as (typeof series)[0];
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: t.muted } },
      formatter: (p: unknown) => {
        const ps = params(p);
        const i = ps[0].dataIndex;
        const ms = h.centers[i];
        const rows = [
          ["300", h.n300[i]],
          ["100", h.n100[i]],
          ["50", h.n50[i]],
        ] as const;
        return (
          `<b>${ms > 0 ? "+" : ms < 0 ? "−" : ""}${Math.abs(ms).toFixed(0)} ms</b>` +
          rows
            .map(([n, v]) => `<br>${n}: ${v.toFixed(1)} hits (${h.total ? ((v / h.total) * 100).toFixed(2) : "0"}% of all)`)
            .join("")
        );
      },
    }),
    xAxis: categoryAxis(t, cats, {
      name: "hit error (ms, real time) · early ← → late",
      nameGap: 26,
      // a label at the bins starting on −150, −120, … 0 … 120 ms (bins are 3 ms, centred 1.5 ms in)
      axisLabel: {
        interval: (_: number, v: string) => Math.round(Number(v) - 1.5) % 30 === 0,
        formatter: (v: string) => `${Math.round(Number(v) - 1.5)}`,
      },
    }),
    yAxis:
      scale === "log"
        ? valueAxis(t, { type: "log", name: "hits (log scale)", nameGap: 40, nameRotate: 90, min: 0.1 })
        : valueAxis(t, {
            name: scale === "zoom" ? `hits (up to ${zoomShare}% of the peak)` : "hits (weighted)",
            nameGap: 40,
            nameRotate: 90,
            max: scale === "zoom" ? Math.max(1, Math.ceil((peak * zoomShare) / 100)) : undefined,
          }),
    series,
  });
}

/** Misses (fingers vs cursor) and UR per 10-BPM stream speed, with the clean / breakdown speeds marked. */
/** UR at each stream speed, one bar per 10 BPM: red = a weak spot (UR clearly above what your other speeds lead to
 * expect, the dashed line), faint = too few notes to tell; a green line where your streams are clean up to. Misses
 * and your best play are in the tooltip. */
export function streamSpeedChart(sp: Schemas["StreamSpeed"], t: ChartTheme): Option {
  const cats = sp.rows.map((r) => String(r.bpm));
  const few = (r: Schemas["StreamSpeedRow"]) => r.objects < MIN_NOTES;
  const at = (bpm: number | null) => {
    if (bpm === null) return null;
    const bin = sp.rows.find((r) => bpm >= r.bpm && bpm < r.bpm + 10) ?? sp.rows.find((r) => Math.round(bpm) === r.bpm);
    return bin ? String(bin.bpm) : null;
  };
  const clean = at(sp.comfort_bpm);
  return base(t, {
    grid: grid({ right: 14, bottom: 8 }),
    tooltip: tooltip(t, {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: t.split } },
      formatter: (p: unknown) => {
        const r = sp.rows[params(p)[0].dataIndex];
        const f = (v: number | null, k = 100, d = 1) => (v === null ? "–" : (v * k).toFixed(d));
        return (
          `<b>${r.bpm}–${r.bpm + 9} BPM</b> · ${Math.round(r.objects)} notes${few(r) ? " (too few to tell)" : ""}` +
          `<br>UR ${f(r.ur, 1, 0)}${r.ur_trend !== null ? ` · expected ${f(r.ur_trend, 1, 0)}` : ""}` +
          (r.ur_best !== null ? ` · your best play ${f(r.ur_best, 1, 0)}` : "") +
          `<br>missed: ${f(r.tap_miss_rate)}% by tapping, ${f(r.speed_aim_rate)}% by the cursor falling behind` +
          (r.weak ? "<br><b>weak spot</b>: your timing spreads clearly more here" : "")
        );
      },
    }),
    xAxis: categoryAxis(t, cats, { name: "stream speed (BPM, 1/4 notes)", nameGap: 26, axisLabel: { color: t.text } }),
    yAxis: valueAxis(t, { name: "UR (timing spread)", nameGap: 36, nameRotate: 90, min: 0 }),
    series: [
      {
        name: "UR",
        type: "bar",
        barMaxWidth: 34,
        data: sp.rows.map((r) => ({
          value: r.ur,
          itemStyle: {
            color: r.weak && !few(r) ? C.bad : faded(t.dark ? "#ffffff" : "#000000", few(r) ? 0.14 : 0.38, t.surface),
            borderRadius: [3, 3, 0, 0],
          },
        })),
        label: {
          show: true,
          position: "top",
          fontSize: 11,
          color: t.muted,
          formatter: (p: unknown) => {
            const r = sp.rows[params(p)[0].dataIndex];
            return r.ur === null ? "" : `${Math.round(r.ur)}${few(r) ? "?" : ""}`;
          },
        },
        markLine: clean
          ? {
              silent: true,
              symbol: "none",
              lineStyle: { color: C.good, type: "solid", width: 1.5 },
              label: { show: true, formatter: "clean up to here", color: C.good, fontSize: 11, position: "end" },
              data: [{ xAxis: clean }],
            }
          : undefined,
      },
      {
        name: "expected",
        type: "line",
        showSymbol: false,
        data: sp.rows.map((r) => r.ur_trend),
        lineStyle: { color: t.muted, type: "dashed", width: 1.5 },
        itemStyle: { color: t.muted },
      },
    ],
  });
}

const LENGTH_COLORS: Record<string, string> = { "16–31 notes": C.good, "32–63 notes": C.info, "64+ notes": C.accent };

/** Precision through long streams: average error per 4 notes, one line per stream length. */
export function fallBehindChart(fb: Schemas["FallBehind"], t: ChartTheme): Option {
  const groups = [...new Set(fb.curves.map((p) => p.group))];
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, {
      trigger: "item",
      formatter: (p: unknown) => {
        const q = params(p)[0];
        const pt = fb.curves.filter((c) => c.group === q.seriesName)[q.dataIndex];
        const f = (v: number | null, d = 1) => (v === null ? "–" : v.toFixed(d));
        return `${esc(pt.group)}, notes ${pt.pos}–${pt.pos + 3}: ${f(pt.abs_err)} ms off on average (${f(pt.err)} ms early/late), ${f(pt.miss_rate === null ? null : pt.miss_rate * 100)}% missed, ${pt.n} hits`;
      },
    }),
    xAxis: valueAxis(t, { name: "note number inside the stream", nameGap: 26, min: 0, splitLine: { show: false } }),
    yAxis: valueAxis(t, { name: "average error (ms, early or late)", nameGap: 40, nameRotate: 90, min: 0 }),
    series: groups.map((g, i) => ({
      name: g,
      type: "line",
      data: fb.curves.filter((c) => c.group === g).map((c) => [c.pos, c.abs_err]),
      symbolSize: 6,
      lineStyle: { width: 2.5 },
      itemStyle: { color: LENGTH_COLORS[g] ?? SERIES[i % SERIES.length] },
      markLine: i === 0 && fb.start_note ? refLine(t, { xAxis: fb.start_note }, C.bad) : undefined,
    })),
  });
}

/** The same per 30-BPM speed, as a share of the time between notes (fair across speeds). */
export function fallBehindSpeedChart(fb: Schemas["FallBehind"], t: ChartTheme): Option {
  const groups = [...new Set(fb.by_speed.map((p) => p.group))].sort();
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, {
      trigger: "item",
      formatter: (p: unknown) => {
        const q = params(p)[0];
        const pt = fb.by_speed.filter((c) => c.group === q.seriesName)[q.dataIndex];
        const f = (v: number | null, d = 1) => (v === null ? "–" : v.toFixed(d));
        return `${esc(pt.group)}, notes ${pt.pos}–${pt.pos + 3}: ${f(pt.rel_err, 0)}% of the note gap (${f(pt.abs_err)} ms), ${f(pt.miss_rate === null ? null : pt.miss_rate * 100)}% missed, ${pt.n} hits`;
      },
    }),
    xAxis: valueAxis(t, { name: "note number inside the stream", nameGap: 26, min: 0, splitLine: { show: false } }),
    yAxis: valueAxis(t, { name: "error, % of the time between notes", nameGap: 40, nameRotate: 90, min: 0 }),
    series: groups.map((g, i) => ({
      name: g,
      type: "line",
      data: fb.by_speed.filter((c) => c.group === g).map((c) => [c.pos, c.rel_err]),
      symbolSize: 6,
      lineStyle: { width: 2.5 },
      itemStyle: { color: SERIES[i % SERIES.length] },
    })),
  });
}

