import { useEffect, useRef } from "react";

import { useTheme } from "../lib/theme";
import { echarts, type Option } from "./echarts";
import { chartTheme, type ChartTheme } from "./palette";

type Handler = (params: unknown, chart: echarts.ECharts) => void;

interface Props {
  /** The chart, built for the current theme. */
  build: (theme: ChartTheme) => Option;
  /** Minimum height (px); the chart also grows to fill its card. */
  height?: number;
  square?: boolean;
  label: string;
  events?: Record<string, Handler>;
}

/**
 * An ECharts chart that fills its container: it follows the card's size (ResizeObserver) and the light /
 * dark theme. Zooming by dragging is off unless an option asks for it (data zoom), like the old app.
 */
export function Chart({ build, height = 320, square = false, label, events }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const { dark } = useTheme();

  useEffect(() => {
    const node = el.current;
    if (!node) return;
    const c = echarts.init(node, undefined, { renderer: "canvas" });
    chart.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(node);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption(build(chartTheme(dark)), { notMerge: true, lazyUpdate: true });
  }, [build, dark]);

  useEffect(() => {
    const c = chart.current;
    if (!c || !events) return;
    const bound = Object.entries(events).map(([name, fn]) => {
      const h = (p: unknown) => fn(p, c);
      c.on(name, h);
      return [name, h] as const;
    });
    return () => bound.forEach(([name, h]) => c.off(name, h));
  }, [events]);

  return (
    <div
      ref={el}
      className={square ? "chart chart--square" : "chart"}
      style={{ ["--chart-h" as string]: `${height}px` }}
      role="img"
      aria-label={label}
    />
  );
}
