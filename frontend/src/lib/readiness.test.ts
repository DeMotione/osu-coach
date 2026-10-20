import { describe, expect, it } from "vitest";

import { LOCKED_HINT, defaultTarget, feltHarder, outOfReachFrom, readiness, targetOptions } from "./readiness";

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

  it("offers targets up to two stars above comfort and locks the next ones", () => {
    const options = targetOptions(5, 2, 0.5);
    expect(options.map((o) => o.label)).toEqual(["5.5★", "6.0★", "6.5★", "7.0★", "7.5★", "8.0★"]);
    expect(options.map((o) => o.disabled)).toEqual([false, false, false, false, true, true]);
    expect(options[4].title).toBe(LOCKED_HINT);
    expect(options[0].title).toBeUndefined();
  });

  it("starts one star above comfort", () => {
    expect(defaultTarget(5, 2)).toBe(6);
    expect(defaultTarget(6.59, 2)).toBe(7.6);
    expect(targetOptions(6.59, 2, 0.5).map((o) => o.value)).toContain(defaultTarget(6.59, 2));
  });
});
