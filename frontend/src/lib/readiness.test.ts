import { describe, expect, it } from "vitest";

import { COMFORT_HINT, LOCKED_HINT, defaultTarget, feltHarder, outOfReachFrom, readiness, starLabel, targetOptions } from "./readiness";
import { starColor, starGlow, starTextColor } from "./starColors";

const range = (comfort: number) => ({ comfort, ahead: 2, step: 0.5, min: 1, max: 13 });

describe("readiness", () => {
  it("follows the square of the star ratio", () => {
    expect(readiness(7, 7)).toBe(1);
    expect(readiness(5, 6)).toBeCloseTo(0.56);
    expect(feltHarder(5, 6)).toBeCloseTo(0.44);
    expect(readiness(7, 10)).toBe(0);
    expect(readiness(8, 7)).toBe(1);
    expect(readiness(null, 8)).toBeNull();
    expect(outOfReachFrom(7)).toBeCloseTo(9.9, 1);
  });

  it("is never higher for a harder target", () => {
    for (const level of [3.2, 6.57, 11]) {
      const values = [1, 3, 5, 7, 7.5, 8, 9, 13].map((t) => readiness(level, t) as number);
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
