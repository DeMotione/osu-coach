/** Shared pieces of chart options, styled for the theme. */
import type { ChartTheme } from "./palette";

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** Deep merge of plain objects (arrays and other values in ``b`` replace those in ``a``). */
export function merge<T extends Obj>(a: T, b: Obj = {}): T {
  const out: Obj = { ...a };
  for (const [k, v] of Object.entries(b)) {
    out[k] = isObj(v) && isObj(out[k]) ? merge(out[k] as Obj, v) : v;
  }
  return out as T;
}

export const FONT = '"Inter Variable", Inter, system-ui, sans-serif';

export function base(t: ChartTheme, extra: Obj = {}): Obj {
  return merge(
    {
      backgroundColor: "transparent",
      textStyle: { fontFamily: FONT, color: t.text, fontSize: 12 },
      animationDuration: 350,
      animationDurationUpdate: 250,
      tooltip: tooltip(t),
    },
    extra,
  );
}

export function tooltip(t: ChartTheme, extra: Obj = {}): Obj {
  return merge(
    {
      confine: true,
      backgroundColor: t.tooltipBg,
      borderColor: t.tooltipBorder,
      borderWidth: 1,
      padding: [8, 11],
      textStyle: { color: t.text, fontSize: 12.5, fontFamily: FONT },
      extraCssText: "border-radius:9px;box-shadow:0 8px 24px rgba(0,0,0,.22);max-width:440px;white-space:normal;",
    },
    extra,
  );
}

export function legend(t: ChartTheme, extra: Obj = {}): Obj {
  return merge(
    {
      type: "scroll",
      bottom: 0,
      left: "center",
      icon: "roundRect",
      itemWidth: 12,
      itemHeight: 8,
      itemGap: 14,
      textStyle: { color: t.muted, fontSize: 12 },
      inactiveColor: t.split,
    },
    extra,
  );
}

/** The plot area; axis labels and names stay inside it. ``legend`` leaves room below for a legend. */
export function grid(extra: Obj = {}, withLegend = false): Obj {
  return merge(
    {
      left: 6,
      right: 14,
      top: 18,
      bottom: withLegend ? 34 : 6,
      outerBoundsMode: "same",
      outerBoundsContain: "all",
    },
    extra,
  );
}

function axisStyle(t: ChartTheme): Obj {
  return {
    axisLine: { lineStyle: { color: t.line } },
    axisTick: { show: false },
    axisLabel: { color: t.muted, fontSize: 11 },
    splitLine: { lineStyle: { color: t.split } },
    nameTextStyle: { color: t.muted, fontSize: 11 },
    nameLocation: "middle",
  };
}

export function valueAxis(t: ChartTheme, extra: Obj = {}): Obj {
  return merge({ type: "value", ...axisStyle(t) }, extra);
}

export function categoryAxis(t: ChartTheme, data: (string | number)[], extra: Obj = {}): Obj {
  return merge({ type: "category", data, ...axisStyle(t), splitLine: { show: false } }, extra);
}

/** A dotted reference line (markLine) at x or y. */
export function refLine(t: ChartTheme, at: { xAxis?: number | string; yAxis?: number | string }, color?: string, extra: Obj = {}): Obj {
  return merge(
    {
      silent: true,
      symbol: "none",
      label: { show: false },
      lineStyle: { color: color ?? t.muted, type: "dashed", width: 1 },
      data: [at],
    },
    extra,
  );
}

/** A circle as a closed polyline (for line series drawn on a value grid). */
export function circle(r: number, steps = 96): [number, number][] {
  return Array.from({ length: steps + 1 }, (_, i) => {
    const a = (i / steps) * 2 * Math.PI;
    return [r * Math.cos(a), r * Math.sin(a)];
  });
}

/** Charts narrower than this get the ``narrow`` overrides of {@link responsive}. */
export const NARROW = 520;

/** An option with overrides for narrow charts (ECharts media queries on the chart's own width). */
export function responsive(option: Obj, narrow: Obj): Obj {
  return { baseOption: option, media: [{ query: { maxWidth: NARROW }, option: narrow }] };
}

/** A round axis maximum a bit above ``max`` (steps of ``step``), at most ``cap``. */
export function niceMax(max: number, step = 10, headroom = 1.18, cap = Infinity): number {
  return Math.min(cap, Math.max(step, Math.ceil((max * headroom) / step) * step));
}
