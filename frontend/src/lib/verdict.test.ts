import { describe, expect, it } from "vitest";

import { judge, listed, overall, share, times, weakest } from "./verdict";

describe("judge", () => {
  it("calls a group worse only when it clearly is, with enough notes", () => {
    const groups = [
      { label: "right", rate: 0.06, n: 800 }, // twice the average, many notes: worse
      { label: "left", rate: 0.027, n: 900 }, // about the average: usual
      { label: "up", rate: 0.026, n: 1000 },
      { label: "down", rate: 0.2, n: 10 }, // much worse, but on 10 notes: too few to tell
    ];
    const j = judge(groups);
    expect(j.map((g) => g.standing)).toEqual(["worse", "usual", "usual", "few"]);
    expect(j[0].ratio).toBeGreaterThan(1.6);
    expect(weakest(j).map((g) => g.label)).toEqual(["right"]);
  });

  it("calls a clearly lower group better, and a small difference usual", () => {
    const j = judge([
      { label: "a", rate: 0.005, n: 2000 },
      { label: "b", rate: 0.025, n: 2000 },
      { label: "c", rate: 0.025, n: 2000 },
    ]);
    expect(j[0].standing).toBe("better");
    expect(j[1].standing).toBe("usual");
  });

  it("leaves groups without data out of the comparison", () => {
    const j = judge([{ label: "a", rate: null, n: 0 }, { label: "b", rate: 0.02, n: 500 }]);
    expect(j[0].standing).toBe("few");
    expect(j[1].usual).toBeCloseTo(0.02);
    expect(j[1].standing).toBe("usual");
    expect(overall([{ label: "a", rate: null, n: 0 }, { label: "b", rate: 0.02, n: 500 }])).toBeCloseTo(0.02);
  });

  it("compares with the average of all the notes, as a player would", () => {
    const j = judge([
      { label: "a", rate: 0.012, n: 3000 }, // 0.6× the average, on many notes: better
      { label: "b", rate: 0.028, n: 3000 }, // 1.4×: more, but not clearly worse
    ]);
    expect(j[0].usual).toBeCloseTo(0.02);
    expect(j.map((g) => g.standing)).toEqual(["better", "usual"]);
  });

  it("puts the biggest excess of misses first", () => {
    const j = judge([
      { label: "small but bad", rate: 0.2, n: 60 },
      { label: "big and worse", rate: 0.06, n: 3000 },
      { label: "rest", rate: 0.02, n: 6000 },
    ]);
    expect(weakest(j).map((g) => g.label)).toEqual(["big and worse", "small but bad"]);
  });
});

describe("words", () => {
  it("says shares, ratios and lists as people write them", () => {
    expect(share(0.0412)).toBe("4.1%");
    expect(share(0.25)).toBe("25%");
    expect(share(null)).toBe("–");
    expect(times(2.04)).toBe("2.0×");
    expect(listed(["right"])).toBe("right");
    expect(listed(["right", "left"])).toBe("right and left");
    expect(listed(["a", "b", "c"])).toBe("a, b and c");
  });
});
