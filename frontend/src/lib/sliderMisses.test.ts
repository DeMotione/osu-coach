import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import {
  atMost, byLength, bySpeed, judgeSteps, lengthLabel, lengthWords, missed, speedLabel, speedWords, standing, total, worseStretches,
} from "./sliderMisses";

const cell = (length: number, speed: number, n: number, head: number, broke: number) => ({ length, speed, n, head, broke });
const m: Schemas["SliderMisses"] = {
  length_top: 8,
  speed_top: 16,
  cells: [cell(1, 7, 1000, 8, 2), cell(1, 13, 100, 3, 1), cell(5, 13, 60, 4, 2), cell(6, 16, 20, 3, 3), cell(8, 16, 20, 5, 3)],
};

describe("adding up the counts", () => {
  it("per length, for the speeds picked or all of them, every length there even without sliders", () => {
    expect(byLength(m, []).map((s) => s.n)).toEqual([0, 1100, 0, 0, 0, 60, 20, 0, 20]);
    expect(byLength(m, [13]).map((s) => s.n)).toEqual([0, 100, 0, 0, 0, 60, 0, 0, 0]);
    expect(byLength(m, [13, 7])[1]).toEqual({ step: 1, n: 1100, head: 11, broke: 3 });
  });

  it("per speed, over every length, and all together", () => {
    expect(bySpeed(m)).toHaveLength(17);
    expect(bySpeed(m)[13]).toEqual({ step: 13, n: 160, head: 7, broke: 3 });
    expect(missed(total(m, []))).toBe(34);
    expect(total(m, [16]).n).toBe(40);
  });
});

describe("the exact test", () => {
  it("is the binomial distribution", () => {
    expect(atMost(0, 10, 0.1)).toBeCloseTo(0.3487, 4);
    expect(atMost(2, 10, 0.1)).toBeCloseTo(0.9298, 4);
    expect(atMost(-1, 10, 0.1)).toBe(0);
    expect(atMost(10, 10, 0.1)).toBe(1);
  });

  it("goes over to the normal one without a jump", () => {
    expect(atMost(190, 2000, 0.0999)).toBeCloseTo(atMost(190, 2000, 0.1001), 1);
    expect(atMost(250, 2000, 0.125)).toBeCloseTo(0.52, 1);
  });

  it("calls a small group worse when its misses can't be chance, and leaves it open when they can", () => {
    const at = (n: number, misses: number) => standing({ step: 0, n, head: misses, broke: 0 }, 0.013);
    expect(at(16, 6)).toBe("worse");
    expect(at(16, 1)).toBe("few");
    expect(at(68, 5)).toBe("worse");
    expect(at(77, 2)).toBe("usual");
    expect(at(5, 5)).toBe("few"); // too few to call anything
    expect(at(2000, 5)).toBe("better");
    expect(at(0, 0)).toBe("few");
  });
});

describe("what stands out", () => {
  it("takes neighbouring worse steps together, the costliest first", () => {
    const step = (s: number, n: number, head: number) => ({ step: s, n, head, broke: 0 });
    const judged = judgeSteps([step(1, 4000, 40), step(2, 100, 8), step(5, 60, 6), step(6, 25, 5), step(8, 24, 8)], 0.013, lengthLabel(8));
    const s = worseStretches(judged, 0.013);
    expect(s.map((x) => [x.from, x.to, x.n, missed(x)])).toEqual([[5, 6, 85, 11], [8, 8, 24, 8], [2, 2, 100, 8]]);
  });

  it("says lengths and speeds as people would", () => {
    expect([0, 7, 8].map(lengthLabel(8))).toEqual(["0–1", "7–8", "8+"]);
    expect([0, 16].map(speedLabel(16))).toEqual(["0", "16+"]);
    expect(lengthWords(5, 8, 8)).toBe("5 circle widths or longer");
    expect(lengthWords(5, 6, 8)).toBe("5 to 7 circle widths long");
    expect(speedWords([13], 16)).toBe("speed 13");
    expect(speedWords([15, 4, 13, 14], 16)).toBe("speeds 4 and 13–15");
    expect(speedWords([13, 14, 15, 16], 16)).toBe("speeds 13 and up");
  });
});
