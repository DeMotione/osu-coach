import { describe, expect, it } from "vitest";

import { breakdownLines } from "./breakdown";

const breakdown = {
  terms: { stars: -0.029047779530329935, skill: -0.10287767482426052, bottlenecks: -0.04, history: 0 },
  target_stars: 5.56,
  reachable_demand: 64.2,
  history_source: "Neutral assumption",
  bottlenecks: [
    { skill: "speed", overload: 4.4 },
    { skill: "reading", overload: 0 },
  ],
};

describe("breakdownLines", () => {
  it("turns the F(m) terms into readable lines", () => {
    expect(breakdownLines(breakdown, 5.47, 61.8, (s) => s.toUpperCase())).toEqual([
      { label: "Stars", detail: "5.47★ vs 5.56★", value: "−0.03" },
      { label: "Skill demand", detail: "62 vs 64", value: "−0.10" },
      { label: "Over your level", detail: "SPEED +4", value: "−0.04" },
      { label: "History", detail: "neutral assumption", value: "±0.00" },
    ]);
  });

  it("is empty without terms and tolerates missing inputs", () => {
    expect(breakdownLines(null, 5, 50)).toEqual([]);
    expect(breakdownLines({ id: "x" }, 5, 50)).toEqual([]);
    const lines = breakdownLines({ terms: { stars: 0 } }, null, null);
    expect(lines.map((l) => l.detail)).toEqual(["– vs –", "– vs –", "none", "–"]);
  });
});
