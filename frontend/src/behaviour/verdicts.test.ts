/**
 * Behaviour: what the analysis pages call a weak spot (the red bars and the sentence on top of each chart). A
 * failing test here means the app broke a rule: fix the code, not the test (see "Behaviour tests" in AGENTS.md).
 */
import { describe, expect, it } from "vitest";

import { judge, weakest } from "../lib/verdict";

describe("a weak spot", () => {
  const groups = (rate: number, n: number) => [
    { label: "usual", rate: 0.02, n: 20_000 },
    { label: "this", rate, n },
  ];
  const standing = (rate: number, n: number) => judge(groups(rate, n)).find((g) => g.label === "this")!.standing;

  it("is clearly worse than your own average: at least 1.5× with enough notes that it isn't chance", () => {
    expect(standing(0.06, 2000)).toBe("worse");
    expect(standing(0.028, 2000)).toBe("usual"); // 1.4×: not enough worse
    expect(standing(0.04, 45)).toBe("usual"); // 2× but too few notes to be sure it isn't chance
  });

  it("isn't judged at all on fewer than 40 notes", () => {
    expect(standing(0.5, 39)).toBe("few");
  });

  it("is clearly better at most 0.67× your average", () => {
    expect(standing(0.005, 5000)).toBe("better");
  });

  it("is listed by the misses it costs you, the most first", () => {
    const judged = judge([
      { label: "usual", rate: 0.02, n: 20_000 },
      { label: "small but much worse", rate: 0.2, n: 100 },
      { label: "big and worse", rate: 0.05, n: 5000 },
    ]);
    expect(weakest(judged).map((g) => g.label)).toEqual(["big and worse", "small but much worse"]);
  });
});
