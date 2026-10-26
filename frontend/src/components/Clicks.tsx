import { useCallback } from "react";

import type { Schemas } from "../api/client";
import { clicksChart } from "../charts/aim";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { EmptyState } from "./states";

/** The clicks chart; how to read it (``clicksCaption``) goes in its card's "?" hint. */
export function ClicksView({ clicks, empty = "Not enough clicks yet" }: { clicks: Schemas["Clicks"]; empty?: string }) {
  const build = useCallback((t: ChartTheme) => clicksChart(clicks, t), [clicks]);
  if (!clicks.enough) return <EmptyState title={empty} />;
  return <Chart build={build} square label={clicks.view === "screen" ? "Where your clicks land on screen" : "Where your clicks land along the jump"} />;
}
