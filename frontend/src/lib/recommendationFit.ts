import type { Schemas } from "../api/client";

type MapRow = Schemas["MapRow"];

/** A ten-point speed gap is roughly a ten-percent tapping-tempo mismatch. */
export function speedFitNotice(maps: MapRow[], targetDemand: number | null | undefined): string | null {
  if (targetDemand == null || maps.length === 0) return null;
  const demands = maps.map((map) => map.skill_demand).filter((value): value is number => value != null);
  if (demands.length === 0 || Math.min(...demands.map((value) => Math.abs(value - targetDemand))) <= 10) return null;
  return `No close tapping-tempo match meets these filters (target demand ${targetDemand.toFixed(1)}). These are the nearest available maps; try a lower relevance threshold.`;
}
