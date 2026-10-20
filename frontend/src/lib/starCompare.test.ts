import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { COMFORT_HINT, chanceLabel, gapLabel, levelLabel, pickTarget, starLabel, targetOptions } from "./starCompare";
import { starColor, starGlow, starTextColor } from "./starColors";

const target = (stars: number, pass_chance: number | null, comfort = false): Schemas["CompareTarget"] => ({
  stars,
  comfort,
  skills: [],
  effective: null,
  limiting: null,
  pass_chance,
});

const compare: Schemas["StarCompare"] = {
  comfort: 6.59,
  points_per_star: 10,
  levels: [],
  targets: [target(1, 1), target(6, 0.9), target(6.6, 0.75, true), target(7.6, 0.3), target(13, 0.0001)],
  default_target: 7.6,
};

describe("comparing with other star ratings", () => {
  it("offers the star ratings from the API, none locked, with the clean-pass chance", () => {
    const options = targetOptions(compare);
    expect(options.map((o) => o.label)).toEqual(["1★", "6★", "6.6★", "7.6★", "13★"]);
    expect(options.some((o) => o.disabled)).toBe(false);
    expect(options.find((o) => o.comfort)).toMatchObject({ value: 6.6, title: `${COMFORT_HINT} · clean pass 75%` });
    expect(options.at(-1)?.title).toBe("clean pass <1%");
    expect(targetOptions({ ...compare, targets: [target(5, null)] })[0].title).toBeUndefined();
  });

  it("starts with the default target and keeps a picked one", () => {
    expect(pickTarget(compare, null)?.stars).toBe(7.6);
    expect(pickTarget(compare, 13)?.stars).toBe(13);
    expect(pickTarget(compare, 9.9)?.stars).toBe(7.6); // no longer offered
    expect(pickTarget({ ...compare, targets: [], default_target: null }, null)).toBeNull();
  });

  it("labels stars, gaps, levels and chances", () => {
    expect(starLabel(7.5)).toBe("7.5★");
    expect(starLabel(8)).toBe("8★");
    expect([gapLabel(1.23), gapLabel(-0.4), gapLabel(0.02)]).toEqual(["+1.2★", "−0.4★", "±0★"]);
    expect(levelLabel({ level: 13, bound: "at_least" })).toBe("≥ 13★");
    expect(levelLabel({ level: 6.61, bound: null })).toBe("6.6★");
    expect(levelLabel({ level: null, bound: null })).toBe("–");
    expect([chanceLabel(0.004), chanceLabel(0.236), chanceLabel(0.999), chanceLabel(null)]).toEqual(["<1%", "24%", ">99%", "–"]);
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
