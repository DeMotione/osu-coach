import { useCallback } from "react";

import type { Schemas } from "../api/client";
import { clicksChart } from "../charts/aim";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { int, signed } from "../lib/format";
import { EmptyState } from "./states";

const DRAWN = 4000;

function bands(c: Schemas["Clicks"]): string {
  return (c.summary?.bands ?? [])
    .map((b) =>
      b.label === "outside"
        ? `${((b.share ?? 0) * 100).toFixed(1)}% outside (aim misses)`
        : `${((b.share ?? 0) * 100).toFixed(0)}% ${b.label}`,
    )
    .join(" · ");
}

/** How to read the clicks chart, with the numbers of all clicks. */
function clicksCaption(c: Schemas["Clicks"]): string {
  const s = c.summary;
  if (!s) return "";
  if (c.view === "movement")
    return (
      `Jumps only (${int(c.n)} clicks, ${int(Math.min(c.n, DRAWN))} drawn), turned so every jump goes right: dots right of ` +
      `the centre overshot, left fell short. Average ${signed(s.mean_r[0], 2)} radii along the jump. A constant offset ` +
      `(e.g. always a bit left) cancels out in this view — see On screen for that. Clicks by distance (radii): ${bands(c)}.`
    );
  const [ox, oy] = [s.mean_px[0] ?? 0, s.mean_px[1] ?? 0];
  const r = s.radius ?? 0;
  const where = `${Math.abs(ox).toFixed(1)} px ${ox < 0 ? "left" : "right"} and ${Math.abs(oy).toFixed(1)} px ${oy < 0 ? "above" : "below"}`;
  const drawn =
    c.n <= DRAWN ? `${int(c.n)} clicks` : `${int(DRAWN)} picked at random from ${int(c.n)}, so the share of yellow dots is the real one`;
  return (
    `Each dot is one click (${drawn}). Average of all clicks: ${where} the centre (± ${(s.ci_px ?? 0).toFixed(1)} px), ` +
    `${r ? ((Math.hypot(ox, oy) / r) * 100).toFixed(0) : "–"}% of the circle radius (${r.toFixed(0)} px). Spread: ` +
    `${(s.sd_px[0] ?? 0).toFixed(0)} px sideways, ${(s.sd_px[1] ?? 0).toFixed(0)} px up/down. Clicks by distance from the ` +
    `centre (radii): ${bands(c)}. A hit is always inside the circle, so only aim misses land outside it.`
  );
}

export function ClicksView({ clicks }: { clicks: Schemas["Clicks"] }) {
  const build = useCallback((t: ChartTheme) => clicksChart(clicks, t), [clicks]);
  if (!clicks.enough) return <EmptyState title="Not enough clicks yet" />;
  return (
    <>
      <Chart build={build} square label={clicks.view === "screen" ? "Where your clicks land on screen" : "Where your clicks land along the jump"} />
      <p className="chart__caption">{clicksCaption(clicks)}</p>
    </>
  );
}
