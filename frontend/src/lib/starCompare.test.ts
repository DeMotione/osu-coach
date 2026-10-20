import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { COMFORT_HINT, chanceLabel, changeLabel, fromComfort, pickTarget, starLabel, targetOptions } from "./starCompare";
import { starColor, starGlow, starTextColor } from "./starColors";

const target = (stars: number, pass_chance: number | null, extra: Partial<Schemas["CompareTarget"]> = {}): Schemas["CompareTarget"] => ({
  stars,
  comfort: false,
  locked: pass_chance === null,
  skills: [],
  weakest: null,
  pass_chance,
  ...extra,
});

const compare: Schemas["StarCompare"] = {
  comfort: 6.27,
  max_gap: 2,
  targets: [target(4, 0.999), target(4.3, 0.99), target(6.3, 0.75, { comfort: true }), target(7.3, 0.36), target(8.3, 0.0001), target(9, null)],
  default_target: 7.3,
};

describe("comparing with other star ratings", () => {
  it("offers the star ratings from the API, those more than 2★ above locked", () => {
    const options = targetOptions(compare);
    expect(options.map((o) => o.label)).toEqual(["4★", "4.3★", "6.3★", "7.3★", "8.3★", "9★"]);
    expect(options.filter((o) => o.disabled).map((o) => o.value)).toEqual([9]); // easier ones are never locked
    expect(options.at(-1)?.title).toContain("more than 2★ above your comfort level");
    expect(options.find((o) => o.comfort)).toMatchObject({ value: 6.3, title: `${COMFORT_HINT} · clean pass 75%` });
    expect(options.find((o) => o.value === 8.3)?.title).toBe("clean pass <1%");
  });

  it("starts with the default target, keeps a picked one and never picks a locked one", () => {
    expect(pickTarget(compare, null)?.stars).toBe(7.3);
    expect(pickTarget(compare, 8.3)?.stars).toBe(8.3);
    expect(pickTarget(compare, 9)?.stars).toBe(7.3);
    expect(pickTarget(compare, 9.9)?.stars).toBe(7.3); // no longer offered
    expect(pickTarget({ ...compare, targets: [], default_target: null }, null)).toBeNull();
  });

  it("labels stars, changes, chances and the distance from comfort", () => {
    expect(starLabel(7.5)).toBe("7.5★");
    expect(starLabel(8)).toBe("8★");
    expect([changeLabel(3.4), changeLabel(-14.6), changeLabel(0.2)]).toEqual(["+3", "−15", "±0"]);
    expect([chanceLabel(0.004), chanceLabel(0.236), chanceLabel(0.999), chanceLabel(null)]).toEqual(["<1%", "24%", ">99%", "–"]);
    expect(fromComfort(8.3, 6.27)).toBe("2★ above your comfort level");
    expect(fromComfort(5.8, 6.27)).toBe("0.5★ below your comfort level");
    expect(fromComfort(6.3, 6.27)).toBe("your comfort level");
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
