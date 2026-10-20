import { describe, expect, it } from "vitest";

import { COMFORT_HINT, LOCKED_HINT, defaultTarget, feltHarder, outOfReachFrom, scoreAt, starLabel, targetOptions } from "./starCompare";
import { starColor, starGlow, starTextColor } from "./starColors";

const range = (comfort: number) => ({ comfort, ahead: 2, step: 0.5, min: 1, max: 13 });

describe("comparing with other star ratings", () => {
  it("takes the felt difficulty off the comfort score on harder maps", () => {
    expect(feltHarder(5, 6)).toBeCloseTo(0.44);
    expect(scoreAt(67, 6.59, 6.59)).toBe(67);
    expect(scoreAt(60, 5, 6)).toBeCloseTo(60 * 0.56);
    expect(scoreAt(88, 7, 7 * Math.SQRT2)).toBeCloseTo(0);
    expect(scoreAt(88, 7, 11)).toBe(0);
    expect(outOfReachFrom(7)).toBeCloseTo(9.9, 1);
  });

  it("closes the gap to 100 on easier maps", () => {
    expect(scoreAt(60, 6, 3)).toBeCloseTo(100 - 40 * 0.25);
    expect(scoreAt(28, 6.59, 1)).toBeGreaterThan(98);
    expect(scoreAt(null, 6.59, 5)).toBeNull();
  });

  it("is never higher for a harder star rating", () => {
    for (const score of [12, 50, 88]) {
      const values = [1, 3, 5, 6.59, 7, 8, 9, 13].map((t) => scoreAt(score, 6.59, t) as number);
      expect(values).toEqual([...values].sort((a, b) => b - a));
    }
  });

  it("offers every easier star, comfort, two stars above it, and locks the rest up to 13★", () => {
    const options = targetOptions(range(7));
    expect(options.map((o) => o.label)).toEqual(["1★", "2★", "3★", "4★", "5★", "6★", "7★", "7.5★", "8★", "8.5★", "9★", "10★", "11★", "12★", "13★"]);
    expect(options.filter((o) => o.disabled).map((o) => o.value)).toEqual([10, 11, 12, 13]);
    expect(options.find((o) => o.value === 10)?.title).toBe(LOCKED_HINT);
    expect(options.find((o) => o.comfort)).toMatchObject({ value: 7, title: COMFORT_HINT });
  });

  it("keeps comfort levels with decimals and stops at 13★", () => {
    expect(targetOptions(range(6.59)).map((o) => o.label)).toEqual(
      ["1★", "2★", "3★", "4★", "5★", "6★", "6.6★", "7.1★", "7.6★", "8.1★", "8.6★", "9★", "10★", "11★", "12★", "13★"],
    );
    const top = targetOptions(range(12));
    expect(top.at(-1)).toMatchObject({ value: 13, disabled: false });
    expect(top.some((o) => o.disabled)).toBe(false);
  });

  it("starts one star above comfort", () => {
    expect(defaultTarget(range(5))).toBe(6);
    expect(defaultTarget(range(6.59))).toBe(7.6);
    expect(defaultTarget(range(12.5))).toBe(13);
    expect(starLabel(7.5)).toBe("7.5★");
    expect(starLabel(8)).toBe("8★");
  });
});

describe("star colours", () => {
  it("follow osu!'s spectrum", () => {
    expect(starColor(2.0)).toBe("#4fffd5");
    expect(starColor(5.8)).toBe("#c645b8");
    expect(starColor(9)).toBe("#000000");
    expect(starColor(13)).toBe("#000000");
    expect(starTextColor(5)).not.toBe(starTextColor(7));
  });

  it("make the steps from 9★ milestones that glow more and more", () => {
    expect(starGlow(8.5)).toBe(0);
    expect(starGlow(9)).toBeGreaterThan(0);
    expect(starGlow(13)).toBe(1);
    expect(starGlow(11)).toBeLessThan(starGlow(12));
  });
});
