import type { Schemas } from "../api/client";
import { esc } from "../lib/format";
import { base, categoryAxis, grid, legend, refLine, tooltip, valueAxis } from "./base";
import type { Option } from "./echarts";
import { C, RESULT_COLORS, SERIES, type ChartTheme } from "./palette";
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

export type StreamMetric = "miss_rate" | "ur";

export function streamsChart(
  s: Schemas["StreamsOverTime"],
  metric: StreamMetric,
  along: "map" | "session",
  keys: string[],
  t: ChartTheme,
): Option {
  const part = s[along];
  const lines = part.lines.filter((l) => keys.includes(l.key));
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, {
      trigger: "item",
      formatter: (p: unknown) => {
        const q = params(p)[0];
        const line = lines[q.seriesIndex ?? 0];
        const pt = line.points[q.dataIndex];
        const v = pt[metric];
        return `${esc(q.seriesName ?? "")}: ${v === null ? "–" : v.toFixed(1)}${metric === "miss_rate" ? "%" : ""} · ${pt.n} notes`;
      },
    }),
    xAxis: valueAxis(t, {
      name: along === "map" ? "minute in the map" : "minutes into the session",
      nameGap: 26,
      min: 0,
      splitLine: { show: false },
    }),
    yAxis: valueAxis(t, { name: metric === "miss_rate" ? "miss rate %" : "UR", nameGap: 40, nameRotate: 90, min: 0 }),
    series: lines.map((l, i) => ({
      name: l.key === "overall" ? "Overall" : `${l.key}–${Number(l.key) + s.band_width - 1} BPM`,
      type: "line",
      data: l.points.map((p) => [p.x + part.step / 2, p[metric]]),
      connectNulls: true,
      symbolSize: 6,
      lineStyle: { width: l.key === "overall" ? 3 : 2 },
      itemStyle: { color: l.key === "overall" ? C.accent : SERIES[(i % (SERIES.length - 1)) + 1] },
    })),
  });
}

/** Misses (fingers vs cursor) and UR per 10-BPM stream speed, with the clean / breakdown speeds marked. */
export function streamSpeedChart(sp: Schemas["StreamSpeed"], t: ChartTheme): Option {
  const cats = sp.rows.map((r) => String(r.bpm));
  const mark = (bpm: number | null, color: string) =>
    bpm !== null && cats.includes(String(Math.round(bpm))) ? [{ xAxis: String(Math.round(bpm)), lineStyle: { color, type: "dashed" } }] : [];
  return base(t, {
    grid: grid({}, true),
    legend: legend(t),
    tooltip: tooltip(t, {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: t.split } },
      formatter: (p: unknown) => {
        const r = sp.rows[params(p)[0].dataIndex];
        const f = (v: number | null, k = 100, d = 1) => (v === null ? "–" : (v * k).toFixed(d));
        return (
          `<b>${r.bpm}–${r.bpm + 9} BPM</b> · ${Math.round(r.objects)} notes (weighted)` +
          `<br>tapping misses ${f(r.tap_miss_rate)}% · speed-aim misses ${f(r.speed_aim_rate)}%` +
          `<br>UR ${f(r.ur, 1, 0)} ${r.ur_plays ? `(median of ${r.ur_plays} plays)` : "(all hits together)"}` +
          (r.ur_best !== null ? ` · best play ${f(r.ur_best, 1, 0)}` : "") +
          (r.weak ? "<br><b>weak spot</b>: UR clearly above the trend" : "")
        );
      },
    }),
    xAxis: categoryAxis(t, cats, { name: "stream speed (BPM, 1/4 notes)", nameGap: 26 }),
    yAxis: [
      valueAxis(t, { name: "miss rate %", nameGap: 36, nameRotate: 90, min: 0 }),
      valueAxis(t, { name: "UR", nameGap: 36, nameRotate: -90, position: "right", splitLine: { show: false }, min: 0 }),
    ],
    series: [
      {
        name: "tapping misses",
        type: "bar",
        stack: "miss",
        data: sp.rows.map((r) => (r.tap_miss_rate === null ? null : +(r.tap_miss_rate * 100).toFixed(2))),
        itemStyle: { color: C.accent },
        markLine: {
          silent: true,
          symbol: "none",
          label: { show: false },
          data: [...mark(sp.comfort_bpm, C.good), ...mark(sp.limit_bpm, C.bad)],
        },
      },
      {
        name: "speed-aim misses",
        type: "bar",
        stack: "miss",
        data: sp.rows.map((r) => (r.speed_aim_rate === null ? null : +(r.speed_aim_rate * 100).toFixed(2))),
        itemStyle: { color: C.yellow, borderRadius: [4, 4, 0, 0] },
      },
      {
        name: "UR (typical play)",
        type: "line",
        yAxisIndex: 1,
        data: sp.rows.map((r) => ({
          value: r.ur,
          symbolSize: r.weak ? 13 : 7,
          itemStyle: { color: r.weak ? C.bad : C.info },
        })),
        lineStyle: { color: C.info, width: 2.5 },
        itemStyle: { color: C.info },
      },
      {
        name: "UR (best play)",
        type: "scatter",
        yAxisIndex: 1,
        symbol: "triangle",
        symbolRotate: 180,
        symbolSize: 9,
        data: sp.rows.map((r) => r.ur_best),
        itemStyle: { color: C.info, opacity: 0.6 },
      },
      {
        name: "UR trend",
        type: "line",
        yAxisIndex: 1,
        showSymbol: false,
        data: sp.rows.map((r) => r.ur_trend),
        lineStyle: { color: t.muted, type: "dashed" },
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

export function keysChart(shares: Schemas["KeyShare"][], t: ChartTheme): Option {
  return base(t, {
    grid: grid(),
    tooltip: tooltip(t, { trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: t.split } }, valueFormatter: (v: number) => `${v.toFixed(1)}%` }),
    xAxis: categoryAxis(
      t,
      shares.map((s) => s.key),
      { axisLabel: { color: t.text, fontSize: 13, fontWeight: 600 } },
    ),
    yAxis: valueAxis(t, { name: "% of presses", nameGap: 36, nameRotate: 90, min: 0 }),
    series: [
      {
        type: "bar",
        barMaxWidth: 70,
        data: shares.map((s) => +(s.share * 100).toFixed(2)),
        itemStyle: { color: C.accent, borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: "top", color: t.text, formatter: (p: unknown) => `${Number(params(p)[0].value).toFixed(0)}%` },
      },
    ],
  });
}
